<p align="center">
  <img src="brand/contextmesh_lockup.svg" alt="ContextMesh — agent memory, as a graph" width="420">
</p>

<h1 align="center">ContextMesh</h1>

<p align="center">
  A self-hosted context API that gives agents the skills, tools, and entities
  their task needs — backed by a HydraDB graph.
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/API-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/graph-HydraDB-6f42c1.svg" alt="HydraDB">
  <img src="https://img.shields.io/badge/status-hackathon%20demo-orange.svg" alt="Hackathon demo">
</p>

ContextMesh plans a compact context pack before an agent calls its model:
matched skills, only the required tool schemas, their MCP servers, and
canonical entities resolved from the task. After the agent runs, it can record
tool usage and newly learned aliases back to the graph.

The project has two entry points:

- **HTTP API:** `POST /v1/plan` → bind the returned tools → run the agent →
  `POST /v1/session`.
- **Python store:** use `HydraContextStore` directly for in-process planning
  and write-back.

This repository is a hackathon/demo build, not a hosted service or production
SLA.

## Contents

- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [HTTP API](#http-api)
- [Configuration and security](#configuration-and-security)
- [Evaluation and load evidence](#evaluation-and-load-evidence)
- [Repository map](#repository-map)
- [License](#license)

## How it works

```text
Task
  └─ plan ─► HydraDB graph
               ├─ keywords → Skill → NEEDS → Tool → SERVED_BY → MCPServer
               └─ mentions → Alias → RESOLVES_TO → Entity
                    ↓
              task-specific context pack
                    ↓
              agent binds tools and runs
                    ↓
              session write-back updates usage and aliases
```

The graph stores skills, tools, MCP servers, entities, aliases, sessions, and
usage counters. [HydraDB](https://github.com/hydra-db/hydradb) persists graph
data in object storage; this demo talks to its HTTP/OpenCypher API. Planning
uses two graph round-trips on the seeded graph. Reads can run concurrently;
writes are serialized per service process to respect HydraDB's
single-writer-per-cell model.

## Quickstart

Prerequisites: Python 3.10+, Docker, and a running HydraDB node. The included
script starts a local demo node using local filesystem storage.

```bash
# Start HydraDB (HTTP :8443, Bolt :7687, admin :9090)
scripts/run_node.sh

# Install dependencies and seed the example context graph
pip install -r requirements.txt
python -m hydracontext.seed

# Inspect a context pack without an LLM
python -m hydracontext.demo "why is checkout failing in prod"

# Start the API and product site
uvicorn hydracontext.service:app --host 127.0.0.1 --port 8000
```

The node script recreates the local `hydradb-node` container and keeps its
demo data under the ignored `.runtime/` directory.

Open [http://localhost:8000/](http://localhost:8000/) for the site and live
demo, [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger UI,
or [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
for the OpenAPI schema.

For a different HydraDB instance or to configure the API, copy
`.env.example` to `.env` and set the values for your environment. The included
HydraDB script is for a local demo; use persistent object storage and
appropriate network controls for a deployment.

## HTTP API

The service's self-hosted default base URL is `http://localhost:8000`. Replace
it with the URL of your deployment when calling the API remotely.

```bash
curl -sS http://localhost:8000/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"task":"why is checkout failing in prod","top_k":3}'
```

`POST /v1/plan` returns `skills`, task-relevant `tools` (including
`schema_json`), their `mcp_servers`, `resolved_entities`, and timing fields.
Use those tools in your agent, then write back the result:

```bash
curl -sS http://localhost:8000/v1/session \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "why is checkout failing in prod",
    "used_tools": ["get_pod_status", "get_events"],
    "resolutions": {"checkout": "checkout-api", "prod": "prod-us"}
  }'
```

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/plan` | Plan a task-specific context pack. `top_k` defaults to 3 and is capped at 10. |
| `POST` | `/v1/session` | Record used tools and entity resolutions. |
| `GET` | `/v1/stats` | Return graph counts by label. |
| `GET` | `/health` | Liveness and graph reachability. |
| `GET` | `/ready` | Readiness check; returns 503 when HydraDB is unreachable. |
| `POST` | `/v1/pilot` | Save a website pilot request to `.runtime/pilots.jsonl`. |

The website's API section has copy-ready JavaScript `fetch` and Python
`requests` examples for the full plan/use/record loop.

### Errors and request IDs

Every response carries an `X-Request-ID` header. API errors use a consistent
shape:

```json
{
  "error": {
    "code": "graph_unavailable",
    "message": "Graph backend unavailable.",
    "request_id": "9f2c1a7b4e01"
  }
}
```

Invalid input returns `422 invalid_request`; unavailable graph operations
return `503 graph_unavailable`; unexpected failures return
`500 internal_error`. `/ready` uses its health response body to report
readiness.

## Configuration and security

- **Authentication is optional and disabled by default.** Set
  `CONTEXTSMESH_API_KEY` to require `X-API-Key` or `Authorization: Bearer` on
  `/v1/plan`, `/v1/session`, and `/v1/stats`.
- **CORS** defaults to `*` for the local demo. Set
  `CONTEXTSMESH_CORS_ORIGINS` to a comma-separated list of allowed origins for
  a deployed browser client.
- `/health`, `/ready`, and `/v1/pilot` are public. The pilot endpoint appends
  requests to a local JSONL file; it does not send email or notify an operator.
- The token in the local node script is a demo credential. Do not expose the
  demo configuration publicly; use a gateway with TLS and authentication for
  deployments.

## Evaluation and load evidence

These are observed demo results, not performance or quality guarantees.

| Measurement | Hydra context | Baseline |
|---|---:|---:|
| Prompt tokens across five ops tasks | 8,195 | 15,276 |
| Correct tasks in the recorded run | 4/5 | 0/5 |

The recorded run used `qwen2.5:1.5b` on CPU. Run the evaluation yourself with
an LLM configured in `.env`:

```bash
python -m hydracontext.eval.harness
```

The load harness exercises concurrent reads and serialized session writes
against a running node:

```bash
python -m bench.load --workers 16 --tasks-per-worker 8
```

The recorded 16-worker run handled 128 sessions with no errors; plan p50/p95
were 7.8/23.5 ms. Write latency rises with queue depth because writes are
serialized per process.

## HydraDB implementation notes

These are constraints verified by the store implementation and useful when
changing graph queries:

- Vertex `id` values must be non-negative integers; named seed objects use
  deterministic integer ID blocks.
- The store uses HydraDB's HTTP API because Bolt does not accept composite
  list/map parameters. HTTP result values arrive in typed wrappers.
- Query parameters cannot contain `null`; optional properties are omitted or
  represented as empty strings.
- Batched writes are chunked to 512 rows (below the 1,024-item API limit).
  Node upserts use `UNWIND`/`MERGE`; edge writes use `UNWIND`/`CREATE`.
- `WHERE IN` is not relied on; membership checks use generated equality
  predicates.

## Repository map

| Path | Contents |
|---|---|
| `hydracontext/store.py` | HydraDB-backed `HydraContextStore`, planning, and session write-back |
| `hydracontext/seed_data.py` | Example skills, tools, MCP servers, entities, and aliases |
| `hydracontext/service.py` | FastAPI service, OpenAPI, and website hosting |
| `hydracontext/agent/` | LangGraph demo agents: Hydra and baseline modes |
| `hydracontext/eval/` | Evaluation tasks and scoring |
| `bench/load.py` | Concurrent planning and session-write load harness |
| `site/` | Product website, API reference, and live demo |
| `brand/` | ContextMesh brand assets |
| `PITCH.md` | Product positioning and proposed pricing |

## License

This project is licensed under the [MIT License](./LICENSE).
