"""Eval harness: baseline agent vs HydraContext agent on the same tasks.

Metrics per task and mode:
- context_round_trips: graph round-trips to assemble working context
- tool_calls:          simulated MCP tool executions
- prompt_tokens:       sum of LLM input tokens (proxy for context window)
- wall_seconds

Correctness: a task lists required tools and required canonical entities.
Hydra mode must surface them in the context pack; both modes must use the
required tools. Writing results to data/eval_results.json.

Run:  python -m hydracontext.eval.harness [--modes hydra baseline]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..agent.agent import run as run_agent
from ..config import CONFIG
from ..store import HydraContextStore

# task, required skill hints, required tools, required canonical entities
TASKS = [
    {
        "task": "why is checkout failing in prod",
        "required_tools": ["get_ci_status"],
        "required_entities": ["checkout-api", "prod-us"],
    },
    {
        "task": "is orders lagging? check replication and slow queries",
        "required_tools": ["get_replication_lag", "get_slow_queries"],
        "required_entities": ["orders-db"],
    },
    {
        "task": "page the oncall for payments and open a ticket for the outage",
        "required_tools": ["get_oncall", "create_issue"],
        "required_entities": ["payments-api"],
    },
    {
        "task": "auth-service looks slow in prod, pull error metrics and recent commits",
        "required_tools": ["get_metric_series", "list_recent_commits"],
        "required_entities": ["auth-service", "prod-us"],
    },
    {
        "task": "scale search down to 2 replicas in staging and check pod status",
        "required_tools": ["scale_deployment", "get_pod_status"],
        "required_entities": ["search-api", "staging"],
    },
]

RESULTS_PATH = Path(__file__).resolve().parents[2] / "data" / "eval_results.json"


def score(task_def: dict, result: dict, pack_entities: dict | None) -> dict:
    used = set(result["used_tools"])
    required = set(task_def["required_tools"])
    tools_ok = required <= used
    if pack_entities is not None:
        # pack_entities maps mention -> canonical name
        entities_ok = all(name in set(pack_entities.values()) for name in task_def["required_entities"])
    else:
        # baseline resolves through the lookup_entity tool: check tool usage
        entities_ok = "lookup_entity" in used
    return {"tools_ok": tools_ok, "entities_ok": entities_ok, "correct": tools_ok and entities_ok}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", default=["hydra", "baseline"])
    args = parser.parse_args()

    store = HydraContextStore()
    store.verify()
    results: dict[str, list] = {mode: [] for mode in args.modes}

    for task_def in TASKS:
        for mode in args.modes:
            print(f"\n=== {mode}: {task_def['task']!r}")
            pack_entities = None
            if mode == "hydra":
                pack = store.plan(task_def["task"])
                pack_entities = {m: e["name"] for m, e in pack.entities.items()}
                missing = [e for e in task_def["required_entities"] if e not in pack_entities.values()]
                print(f"  pack: skills={[s['name'] for s in pack.skills]} "
                      f"tools={pack.tool_names} entities={pack_entities} "
                      f"round_trips={pack.round_trips()}")
                if missing:
                    print(f"  WARNING: pack missed entities {missing}")
            try:
                result = run_agent(store, task_def["task"], mode=mode)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR: {exc}")
                result = {
                    "mode": mode, "task": task_def["task"], "final": f"ERROR: {exc}",
                    "used_tools": [], "metrics": {},
                }
            result["score"] = score(task_def, result, pack_entities)
            results[mode].append(result)
            m = result["metrics"]
            print(f"  metrics: round_trips={m.get('context_round_trips')} "
                  f"tool_calls={m.get('tool_calls')} "
                  f"prompt_tokens={m.get('prompt_tokens')} "
                  f"wall={m.get('wall_seconds')}s")
            print(f"  tools used: {result['used_tools']}")
            print(f"  final: {result['final'][:200]}")

            # write-back: the graph learns what was used and resolved
            if mode == "hydra" and not result["final"].startswith("ERROR"):
                store.record_session(
                    task_def["task"], result["used_tools"], dict(pack_entities or {})
                )

    summary = {}
    for mode, rows in results.items():
        if not rows:
            continue
        def total(key: str) -> float:
            return sum(r["metrics"].get(key) or 0 for r in rows)
        summary[mode] = {
            "tasks": len(rows),
            "correct": sum(1 for r in rows if r["score"]["correct"]),
            "context_round_trips": total("context_round_trips"),
            "tool_calls": total("tool_calls"),
            "prompt_tokens": total("prompt_tokens"),
            "wall_seconds": total("wall_seconds"),
        }
    print("\n" + "=" * 70)
    print(f"{'mode':<10}{'correct':>8}{'trips':>8}{'toolcalls':>11}{'prompt_tok':>12}{'wall_s':>8}")
    for mode, s in summary.items():
        print(f"{mode:<10}{s['correct']:>8}{s['context_round_trips']:>8.0f}"
              f"{s['tool_calls']:>11.0f}{s['prompt_tokens']:>12.0f}{s['wall_seconds']:>8.1f}")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(
        {"results": results, "summary": summary,
         "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        indent=2,
    ))
    print(f"\nfull results -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
