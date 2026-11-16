"""HydraDB-backed live context store for agents.

Everything here speaks the HydraDB OpenCypher dialect, which is a strict
subset of Neo4j's. The shapes used, and why, are documented in the repo's
cypher-compat.md / USING-HYDRADB.md:

- The `id` property is the vertex identity and must be a non-negative
  integer ("UNWIND row 0 field id must be a non-negative integer"). We map
  every named object to a deterministic integer id at seed time and look
  nodes up by `name` / `text` property predicates instead.
- Node upserts go through the batch MERGE shape, the only way to create an
  edgeless node or write properties in bulk:
      UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Label, n.p = row.p
  The label must come first; properties may follow in the same SET.
- Edge writes go through the batch CREATE shape, which is idempotent on
  (src, dst, type) and does not clobber labels/properties on existing ids:
      UNWIND $rows AS row CREATE (a {id: row.src})-[:TYPE]->(b {id: row.dst})
- Batches are capped at 1024 items; we chunk to 512 to stay well inside.
- WHERE supports comparisons and boolean combinations; IN is not listed as
  supported, so membership tests become client-built OR chains.
- RETURN has no arithmetic and no bare bindings; project properties only.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field

import httpx

from .config import CONFIG, HydraConfig

BATCH_CHUNK = 512

# deterministic integer-id blocks (stable across reseeds because seeds sort)
AGENT_ID = 1
ID_BLOCKS = {
    "Skill": 101,
    "Tool": 201,
    "MCPServer": 301,
    "Entity": 401,
    "Alias": 501,
}
# runtime-allocated ids start here (watermarks live on the Agent node)
SESSION_BASE = 601
ENTITY_BASE = 701
ALIAS_BASE = 801


@dataclass
class ContextPack:
    """Everything the agent needs for one task, pulled in a few round-trips."""

    skills: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)      # includes schema_json + server
    mcp_servers: list[dict] = field(default_factory=list)
    entities: dict[str, dict] = field(default_factory=dict)  # mention -> entity
    queries: list[tuple[str, float]] = field(default_factory=list)  # (label, ms) for the demo

    @property
    def tool_names(self) -> list[str]:
        return sorted({t["tool"] for t in self.tools})

    def round_trips(self) -> int:
        return len(self.queries)

    def to_dict(self) -> dict:
        return {
            "skills": self.skills,
            "tools": self.tools,
            "mcp_servers": self.mcp_servers,
            "entities": self.entities,
            "queries": [(q, ms) for q, ms in self.queries],
        }


def _unwrap(value):
    """HTTP rows carry typed wrappers like {"type":"integer","value":6} or
    {"type":"null"} for absent properties."""
    if isinstance(value, dict) and "type" in value and len(value) <= 2:
        if value["type"] == "null" or "value" not in value:
            return None
        return value["value"]
    return value


class HydraContextStore:
    def __init__(self, config: HydraConfig | None = None):
        self.config = config or CONFIG
        # HTTP query API: parameters arrive as JSON, so batch (list-of-map)
        # parameters work here; the Bolt adapter accepts scalars only.
        self.http = httpx.Client(timeout=60)

    def close(self) -> None:
        self.http.close()

    def verify(self) -> None:
        rows = self._run("MATCH (a:Agent {id: $aid}) RETURN a.id AS id", "verify", aid=1)
        if not rows:
            self.bootstrap()

    def ping(self, timeout: float = 2.0) -> bool:
        """Cheap graph reachability check with a short timeout (for /ready)."""
        try:
            self._run(
                "MATCH (n:Agent) RETURN count(*) AS n",
                "health",
                timeout=timeout,
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    def _run(
        self,
        cypher: str,
        label: str,
        pack: "ContextPack | None" = None,
        *,
        timeout: float | None = None,
        **params,
    ):
        started = time.perf_counter()
        request = {
            "headers": {
                "Authorization": f"Bearer {self.config.token}",
                "X-Graph-Namespace": self.config.namespace,
            },
            "json": {
                "cell_id": self.config.cell_id,
                "query": cypher,
                "parameters": params,
            },
        }
        if timeout is not None:
            request["timeout"] = timeout
        response = self.http.post(self.config.query_url, **request)
        if response.status_code != 200:
            raise RuntimeError(
                f"hydra query failed ({label}): HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        data = response.json()
        if data.get("next_cursor"):
            raise RuntimeError(
                f"hydra query result page truncated ({label}): pagination not "
                "implemented in demo store; narrow the query"
            )
        columns = data.get("columns", [])
        records = [dict(zip(columns, (_unwrap(v) for v in row))) for row in data.get("rows", [])]
        if pack is not None:
            pack.queries.append((label, round((time.perf_counter() - started) * 1000, 1)))
        return records

    @staticmethod
    def _or_chain(var: str, prop: str, values: list) -> str:
        """Client-built OR chain of equality predicates (WHERE IN is unverified)."""
        return " OR ".join(f"{var}.{prop} = ${prop}_{i}" for i in range(len(values)))

    @staticmethod
    def _or_params(prop: str, values: list) -> dict:
        return {f"{prop}_{i}": v for i, v in enumerate(values)}

    @staticmethod
    def _chunks(rows: list[dict], size: int = BATCH_CHUNK):
        for i in range(0, len(rows), size):
            yield rows[i : i + size]

    # ------------------------------------------------------------- write side

    def upsert_nodes(self, label: str, rows: list[dict], props: list[str]) -> None:
        """Batch node upsert: MERGE by integer id, then SET :Label and props.

        This is the only shape that creates edgeless nodes or batch-writes
        properties. The label assignment must come first in the SET.
        """
        if not rows:
            return
        prop_list = ", ".join(f"n.{p} = row.{p}" for p in props)
        cypher = f"UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{label}, {prop_list}"
        for chunk in self._chunks(rows):
            self._run(cypher, f"upsert:{label}", rows=chunk)

    def upsert_edges(self, rel_type: str, rows: list[dict]) -> None:
        """Batch edge create; idempotent per (src, dst, rel_type)."""
        if not rows:
            return
        cypher = (
            "UNWIND $rows AS row "
            f"CREATE (a {{id: row.src}})-[:{rel_type}]->(b {{id: row.dst}})"
        )
        for chunk in self._chunks(rows):
            self._run(cypher, f"upsert_edge:{rel_type}", rows=chunk)

    def _watermark(self, prop: str, default: int) -> int:
        rows = self._run(
            f"MATCH (a:Agent {{id: $aid}}) RETURN a.{prop} AS next",
            f"watermark:{prop}",
            aid=AGENT_ID,
        )
        nxt = rows[0]["next"] if rows else None
        return nxt if nxt is not None else default

    def bootstrap(self) -> None:
        self.upsert_nodes(
            "Agent", [{"id": AGENT_ID, "name": "hydra-demo-agent"}], ["name"]
        )

    def seed(self, skills, tools, servers, entities, aliases, membership) -> None:
        """Write the whole seed graph in a handful of batched requests.

        Rows already carry deterministic integer ids (see seed_data.build_seed).
        """
        self.bootstrap()
        self.upsert_nodes("Skill", skills, ["name", "keywords", "uses"])
        self.upsert_nodes("Tool", tools, ["name", "kind", "schema_json", "endpoint", "uses"])
        self.upsert_nodes("MCPServer", servers, ["name", "command", "url"])
        self.upsert_nodes("Entity", entities, ["canonical_name", "kind"])
        self.upsert_nodes("Alias", aliases, ["text"])
        self.upsert_edges("HAS_SKILL", membership["HAS_SKILL"])
        self.upsert_edges("NEEDS", membership["NEEDS"])
        self.upsert_edges("SERVED_BY", membership["SERVED_BY"])
        self.upsert_edges("RESOLVES_TO", membership["RESOLVES_TO"])

    # -------------------------------------------------------------- read side

    def list_skills(self) -> list[dict]:
        return self._run(
            "MATCH (s:Skill) RETURN s.id AS id, s.name AS name, s.keywords AS keywords",
            "scan_skills",
        )

    def pack_for_skills(self, skill_ids: list[int], pack: ContextPack) -> None:
        """One query: skills -> needed tools -> serving MCP servers."""
        if not skill_ids:
            return
        where = " OR ".join(f"s.id = $s{i}" for i in range(len(skill_ids)))
        params = {f"s{i}": sid for i, sid in enumerate(skill_ids)}
        rows = self._run(
            "MATCH (s:Skill)-[:NEEDS]->(t:Tool)-[:SERVED_BY]->(m:MCPServer) "
            f"WHERE {where} "
            "RETURN s.id AS skill_id, s.name AS skill, t.id AS tool_id, "
            "t.name AS tool, t.kind AS kind, t.schema_json AS schema_json, "
            "m.id AS server_id, m.name AS server, m.command AS command",
            "pack_skills+tools+servers",
            pack,
            **params,
        )
        seen_tools: set[str] = set()
        seen_servers: set[str] = set()
        seen_skills: set[int] = {s["id"] for s in pack.skills}
        for r in rows:
            if r["skill_id"] not in seen_skills:
                seen_skills.add(r["skill_id"])
                pack.skills.append({"id": r["skill_id"], "name": r["skill"]})
            if r["tool"] not in seen_tools:
                seen_tools.add(r["tool"])
                pack.tools.append(
                    {
                        "id": r["tool_id"],
                        "tool": r["tool"],
                        "kind": r["kind"],
                        "schema_json": r["schema_json"],
                        "server": r["server"],
                        "server_id": r["server_id"],
                    }
                )
            if r["server"] not in seen_servers:
                seen_servers.add(r["server"])
                pack.mcp_servers.append(
                    {"id": r["server_id"], "name": r["server"], "command": r["command"]}
                )

    def resolve_mentions(self, mentions: list[str], pack: ContextPack) -> None:
        """Batched entity resolution against alias edges and canonical names.

        Two UNIONed label-anchored lookups with client-built OR chains on
        equality — one round-trip resolves every mention in the task.
        """
        if not mentions:
            return
        uniq = list(dict.fromkeys(mentions))[:24]
        alias_where = self._or_chain("a", "text", uniq)
        ent_where = self._or_chain("e", "canonical_name", uniq)
        params = {**self._or_params("text", uniq), **self._or_params("canonical_name", uniq)}
        rows = self._run(
            "MATCH (a:Alias)-[:RESOLVES_TO]->(e:Entity) "
            f"WHERE {alias_where} "
            "RETURN a.text AS mention, e.id AS entity_id, "
            "e.canonical_name AS name, e.kind AS kind "
            "UNION "
            "MATCH (e:Entity) "
            f"WHERE {ent_where} "
            "RETURN e.canonical_name AS mention, e.id AS entity_id, "
            "e.canonical_name AS name, e.kind AS kind",
            "resolve_entities",
            pack,
            **params,
        )
        for r in rows:
            if r["entity_id"]:
                pack.entities[r["mention"]] = {
                    "entity_id": r["entity_id"],
                    "name": r["name"],
                    "kind": r["kind"],
                }

    # -------------------------------------------------------------- the pitch

    def plan(self, task: str, top_k: int = 3) -> ContextPack:
        """Pull exactly the context a task needs: 3-4 graph round-trips total."""
        pack = ContextPack()
        skills = self.list_skills()
        chosen = match_skills(task, skills, top_k=top_k)
        pack.skills = chosen
        self.pack_for_skills([s["id"] for s in chosen], pack)
        # candidate mentions: capitalized words, hyphenated slugs, and bare tokens
        mentions = extract_mentions(task) + tokenize(task)
        self.resolve_mentions(mentions, pack)
        return pack

    # ------------------------------------------------------- session writeback

    def record_session(
        self,
        task: str,
        used_tools: list[str],
        resolutions: dict[str, str] | None = None,
    ) -> str:
        """Persist one session and its usage. The graph accumulates what the
        agent actually used and resolved — the substrate for usage-driven
        ranking and for answering the next task with fewer lookups."""
        session_id = self._watermark("next_session", SESSION_BASE)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.upsert_nodes(
            "Session",
            [{"id": session_id, "task": task, "started_at": now}],
            ["task", "started_at"],
        )

        tool_rows: list[dict] = []
        if used_tools:
            where = " OR ".join(f"t.name = $t{i}" for i in range(len(used_tools)))
            tool_rows = self._run(
                f"MATCH (t:Tool) WHERE {where} RETURN t.id AS id, t.name AS name",
                "lookup_used_tools",
                **{f"t{i}": name for i, name in enumerate(used_tools)},
            )

        self.upsert_edges(
            "INVOLVED",
            [{"src": session_id, "dst": AGENT_ID}]
            + [{"src": session_id, "dst": r["id"]} for r in tool_rows],
        )

        # usage counters, computed client-side (no arithmetic in RETURN)
        if tool_rows:
            counts = {
                r["id"]: r["uses"] or 0
                for r in self._run(
                    "MATCH (t:Tool) WHERE t.id = $t0"
                    + "".join(f" OR t.id = $t{i}" for i in range(1, len(tool_rows)))
                    + " RETURN t.id AS id, t.uses AS uses",
                    "read_usage",
                    **{f"t{i}": r["id"] for i, r in enumerate(tool_rows)},
                )
            }
            self.upsert_nodes(
                "Tool",
                [{"id": r["id"], "uses": counts.get(r["id"], 0) + 1} for r in tool_rows],
                ["uses"],
            )

        # resolutions learned this session become alias edges for next time
        new_aliases = resolutions or {}
        if new_aliases:
            base_e = self._watermark("next_entity", ENTITY_BASE)
            base_a = self._watermark("next_alias", ALIAS_BASE)
            ent_ids = list(dict.fromkeys(new_aliases.values()))
            existing = {
                r["canonical_name"]: r["id"]
                for r in self._run(
                    "MATCH (e:Entity) WHERE e.canonical_name = $c0"
                    + "".join(
                        f" OR e.canonical_name = $c{i}"
                        for i in range(1, len(ent_ids))
                    )
                    + " RETURN e.id AS id, e.canonical_name AS canonical_name",
                    "lookup_entities",
                    **{f"c{i}": c for i, c in enumerate(ent_ids)},
                )
            }
            fresh_entities = [c for c in ent_ids if c not in existing]
            allocated: dict[str, int] = dict(existing)
            for i, cname in enumerate(fresh_entities):
                allocated[cname] = base_e + i

            # dedupe aliases: reuse an existing Alias by text; create only new ones
            mention_texts = list(new_aliases)
            existing_alias = {
                r["text"]: r["id"]
                for r in self._run(
                    "MATCH (a:Alias) WHERE a.text = $t0"
                    + "".join(f" OR a.text = $t{i}" for i in range(1, len(mention_texts)))
                    + " RETURN a.id AS id, a.text AS text",
                    "lookup_aliases",
                    **{f"t{i}": t for i, t in enumerate(mention_texts)},
                )
            }
            fresh_mentions = [t for t in mention_texts if t not in existing_alias]
            alias_id_of = dict(existing_alias)
            new_alias_rows = [
                {"id": base_a + i, "text": t} for i, t in enumerate(fresh_mentions)
            ]
            for i, t in enumerate(fresh_mentions):
                alias_id_of[t] = base_a + i

            # one mention resolves to exactly one entity: never add a second
            # RESOLVES_TO edge when the alias already points elsewhere
            already: dict[int, set[str]] = {}
            if existing_alias:
                ids = list(dict.fromkeys(existing_alias.values()))
                where = " OR ".join(f"a.id = $r{i}" for i in range(len(ids)))
                for r in self._run(
                    f"MATCH (a:Alias)-[:RESOLVES_TO]->(e:Entity) WHERE {where} "
                    "RETURN a.id AS aid, e.canonical_name AS name",
                    "lookup_alias_targets",
                    **{f"r{i}": v for i, v in enumerate(ids)},
                ):
                    already.setdefault(r["aid"], set()).add(r["name"])
            kept = {
                m: c
                for m, c in new_aliases.items()
                if not already.get(alias_id_of[m]) or c in already[alias_id_of[m]]
            }

            # only genuinely new entities get a node (existing kinds stay intact)
            self.upsert_nodes(
                "Entity",
                [
                    {"id": allocated[c], "canonical_name": c, "kind": "resolved"}
                    for c in fresh_entities
                ],
                ["canonical_name", "kind"],
            )
            self.upsert_nodes("Alias", new_alias_rows, ["text"])
            self.upsert_edges(
                "RESOLVES_TO",
                [
                    {"src": alias_id_of[m], "dst": allocated[cname]}
                    for m, cname in kept.items()
                ],
            )
            self.upsert_nodes(
                "Agent",
                [{
                    "id": AGENT_ID,
                    "next_entity": base_e + len(fresh_entities),
                    "next_alias": base_a + len(new_alias_rows),
                }],
                ["next_entity", "next_alias"],
            )

        self.upsert_nodes(
            "Agent", [{"id": AGENT_ID, "next_session": session_id + 1}], ["next_session"]
        )
        return f"session:{session_id}"

    def stats(self) -> dict:
        nodes = {}
        for label in ("Skill", "Tool", "MCPServer", "Entity", "Alias", "Session"):
            rows = self._run(f"MATCH (n:{label}) RETURN count(*) AS n", f"count_{label}")
            nodes[label] = rows[0]["n"] if rows else 0
        return nodes


STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "is", "are",
    "please", "check", "why", "what", "how", "does", "do", "me", "my", "our",
    "get", "show", "give", "tell", "about", "with", "from", "that", "this",
    "it", "be", "was", "were", "can", "you", "we", "us", "if", "then", "now",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9_\-]+", text.lower()) if t not in STOPWORDS]


def match_skills(task: str, skills: list[dict], top_k: int = 3) -> list[dict]:
    """Client-side keyword scoring against each skill's keyword list."""
    tokens = set(tokenize(task))
    scored = []
    for s in skills:
        kws = s.get("keywords") or []
        if isinstance(kws, str):
            try:
                kws = json.loads(kws)
            except (TypeError, json.JSONDecodeError):
                kws = [kws]
        overlap = tokens & {k.lower() for k in kws}
        name_hits = tokens & set(tokenize(s.get("name", "")))
        score = len(overlap) * 2 + len(name_hits)
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [s for _, s in scored[:top_k]]


def extract_mentions(task: str) -> list[str]:
    """Candidate entity mentions: capitalized words and hyphenated slugs."""
    candidates = set()
    for word in re.findall(r"\b[A-Z][A-Za-z0-9_\-]*\b", task):
        candidates.add(word)
    for slug in re.findall(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b", task.lower()):
        candidates.add(slug)
    candidates.difference_update({"I", "The", "Why", "What", "How", "Check", "Please"})
    return sorted(candidates)
