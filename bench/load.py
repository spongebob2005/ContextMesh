"""Concurrency load harness for the context layer.

What it proves for the "holds up under load" criterion:
- Reads (plan) scale concurrently against HydraDB's HTTP API.
- Writes (record_session) are funneled through one writer lock — matching
  HydraDB's own single-writer-per-cell model — while reads never wait.

Run:  python -m bench.load [--workers 8] [--tasks-per-worker 6]
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hydracontext.store import ContextPack, HydraContextStore

TASKS = [
    ("why is checkout failing in prod", ["get_ci_status"], {"checkout": "checkout-api", "prod": "prod-us"}),
    ("is orders lagging? check replication", ["get_replication_lag"], {"orders": "orders-db"}),
    ("page the oncall for payments", ["get_oncall"], {"payments": "payments-api"}),
    ("auth-service slow in prod, pull metrics", ["get_metric_series"], {"prod": "prod-us"}),
    ("scale search in staging", ["scale_deployment"], {"search": "search-api", "staging": "staging"}),
]

RESULTS_PATH = Path(__file__).resolve().parents[1] / "data" / "load_results.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--tasks-per-worker", type=int, default=6)
    args = parser.parse_args()

    store = HydraContextStore()
    store.verify()

    write_lock = threading.Lock()  # one writer per cell, by design
    timings: list[tuple[str, float]] = []
    errors: list[str] = []
    sessions = 0
    tlock = threading.Lock()

    def one_session(worker: int, i: int) -> None:
        nonlocal sessions
        task, tools, resolutions = TASKS[(worker + i) % len(TASKS)]
        try:
            t0 = time.perf_counter()
            pack: ContextPack = store.plan(f"{task} from worker{worker}")
            t1 = time.perf_counter()
            with write_lock:  # HydraDB: one writer per cell
                store.record_session(
                    f"{task} (w{worker})", tools,
                    {m: c for m, c in resolutions.items()},
                )
            t2 = time.perf_counter()
            with tlock:
                timings.append(("plan", t1 - t0))
                timings.append(("record", t2 - t1))
                sessions += 1
        except Exception as exc:  # noqa: BLE001
            with tlock:
                errors.append(f"{type(exc).__name__}: {exc}")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(one_session, w, i)
            for w in range(args.workers)
            for i in range(args.tasks_per_worker)
        ]
        for f in futures:
            f.result()
    wall = time.perf_counter() - started

    def pct(name: str, p: float) -> float:
        vals = sorted(d for op, d in timings if op == name)
        if not vals:
            return 0.0
        return round(vals[min(len(vals) - 1, int(len(vals) * p / 100))] * 1000, 1)

    ops = len(timings)
    summary = {
        "workers": args.workers,
        "sessions": sessions,
        "errors": len(errors),
        "wall_seconds": round(wall, 2),
        "throughput_sessions_per_sec": round(sessions / wall, 2),
        "plan_p50_ms": pct("plan", 50),
        "plan_p95_ms": pct("plan", 95),
        "plan_max_ms": pct("plan", 100),
        "record_p50_ms": pct("record", 50),
        "record_p95_ms": pct("record", 95),
        "total_graph_queries": ops,
    }
    print(json.dumps(summary, indent=2))
    if errors:
        print("sample errors:", errors[:3])
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"\nsaved -> {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
