# Your agent doesn't need 16 tools. It needs the right 5.

**ContextMesh** is the context layer for agent fleets: skills, tool and MCP
definitions, and entity resolutions as one durable graph — so agents pull
exactly what a task needs instead of carrying every tool into every prompt.

Built for the HydraDB hackathon (Track 2), on HydraDB.

---

## The pitch in one paragraph

Every production agent today pays a tax on every step: 16 tool schemas in the
window, an extra LLM call to figure out that "checkout" means `checkout-api`,
and the same names re-resolved forever — differently by every agent in the
fleet. ContextMesh replaces that with a graph. The task arrives, the agent
traverses, and the model sees only what matters: one skill, five tools, two
entities already mapped to canonical ids. After the task, the session writes
back what it used and what it learned, so the graph gets sharper with every
turn. Same model, same tasks: **46% fewer prompt tokens and 4/5 correct
instead of 0/5.**

## Who wants this

- **AI platform teams running agent fleets** — SRE copilots, support agents,
  finance-ops agents. They feel the token burn, the resolution drift, and the
  memory that vanishes on restart.
- **Agent frameworks and MCP gateways** — a memory tier to bundle instead of
  build.
- **Usage-billed agent SaaS** — every point of cost per task is margin.

## Why it has to be a graph

Agent context *is* a graph: skill → tool → MCP server, alias → canonical
entity. The graph is what makes "pull only what's needed" a two-lookup
operation instead of a prompt-stuffing exercise.

HydraDB made that practical: OpenCypher over HTTPS, storage on object storage
with disposable query caches, and an honest single-writer-per-cell model that
matched the per-session write-back instead of fighting it. Mid-hack, the
machine rebooted — the graph came back with no restore step. That's the
durability pitch, demonstrated, not promised.

## The wedge

**Entity resolution first.** "Your agents currently resolve mentions with extra
LLM calls — replace that with one graph lookup." It's measurable, demo-able,
and it's the part every agent team hates maintaining. Then expand to full
context packs: skills, tool graphs, MCP server configs, per-fleet curation.

Pricing follows usage: per resolved entity on a free tier, per-agent seats for
curated context packs, self-hosted enterprise (it's already one Docker image)
with multi-tenant namespaces.

## Proof — this isn't a slide deck

| Claim | Evidence |
|---|---|
| Fewer tokens | 8,195 vs 15,276 prompt tokens on the same 5 tasks, same model (−46%) |
| Correct instead of lost | 4/5 vs 0/5 on tool choice + entity resolution |
| Holds under load | 128 concurrent sessions, 0 errors, plan p50 7.8 ms / p95 23.5 ms |
| Durable | container killed and recreated → graph intact from object storage |
| Cheap to learn from | every session writes back usage + new aliases, deduped |

## What made it hard (and why that's a moat)

The graph substrate has sharp edges — integer vertex ids only, no `WHERE IN`,
composite parameters rejected over Bolt, batch caps, no null parameters, and a
strict single-writer model. Each one forced a design decision that now lives in
the code: deterministic id blocks, client-built OR chains, batched upserts with
idempotent edges, serialized write-back behind a lock with fully concurrent
reads.

The load test then earned its keep: it exposed duplicate alias nodes created by
concurrent sessions (444 aliases from ~200 sessions), which we fixed with a
batched text lookup before allocation. Ten sessions now add one alias, not ten.
That's the thing a competitor copying the demo won't copy — the failure modes
are already paid for.

## The takeaway

Prompts don't need more tools. They need better memory.

ContextMesh is that memory: a graph that answers "what does this task need?"
before the first token is generated — and gets sharper every time it's asked.

Built on **@hydra_db**. Code: `hydra-agent-context/`.
