# ContextMesh — pitch (go-to-market)

**Product in one line:** the context layer for production agent fleets — skills, tool/MCP
definitions, and entity resolutions as a queryable graph, so agents pull only what the task
needs instead of carrying every tool in every window.

## Who feels this pain (ICP, in order)

1. **AI platform / agent-infra teams** at companies running many internal agents
   (SRE copilots, support agents, finance-ops agents). They already feel:
   - prompt-token burn from N agents × M tools × every step;
   - resolution drift — two agents resolve "checkout" to different services;
   - no shared memory across agents, sessions, or frameworks.

2. **Vendor of an agent framework / MCP gateway** who wants a memory tier to bundle.

3. **Agent-heavy SaaS** (observability, incident-response, CRM automation) that bills by
   usage and needs their agent cost per task to drop.

## Why they buy it

| They have today | ContextMesh gives them |
|---|---|
| Every tool schema in every prompt | 2–9 task-relevant tools bound; **~50% fewer prompt tokens** (measured) |
| Per-agent entity resolvers (or vibes) | one shared, **guaranteed** resolution layer; mention → canonical id before the first LLM call |
| Memory lost on restart | durable in object storage (HydraDB/SlateDB); **agent fleet restarts don't lose memory** |
| Static prompt config | the graph **learns per session** — usage counters and alias edges — agents get sharper the more they're used |
| Homegrown JSON stores | a real graph: skills→tools→servers→entities traversals, batched multi-source lookups |

## The wedge

Start with the **entity resolution layer**: the demo-able, measurable piece
("your agents currently resolve mentions with extra LLM calls — replace that with one graph
lookup"). Then sell the full context packs (skills + tools + servers) as the platform tier.

## Pricing shape (usage-aligned, like the agents it serves)

- **Resolved-entity calls**: the unit of value. Free tier 1k/mo → $/1k resolutions after.
- **Context packs**: per-agent seat for skills/tool-graph curation (team tier).
- **Enterprise**: self-hosted (it already is — one Docker image) + multi-tenant namespaces,
  which HydraDB's tenant/subtenant scopes support natively.

## Why this is defensible

The value compounds: every session writes back usage and learned aliases, so switching costs
grow with use — an agent fleet's resolution graph is training data nobody else has.
The storage substrate (HydraDB: object-store-native, snapshot-consistent, single-writer-per-cell)
makes the tier cheap to run and safe to scale out; reads scale horizontally, writes are
intentionally serialized per cell.

## Proof points already built in this repo

- Baseline vs graph eval: **4/5 vs 0/5 correctness, −46% prompt tokens** (5 ops tasks, same local model)
- Load: **128 concurrent sessions, 0 errors, plan p50 7.8 ms / p95 23.5 ms** at 16-way concurrency
- Durability: container killed → graph intact from object storage (demonstrated across a reboot)
- Everything speaks one graph DB: HydraDB (OpenCypher over HTTP; Bolt-compatible for Neo4j clients)
