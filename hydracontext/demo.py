"""Dry-run demo (no LLM): show the context pack a task would load.

Run:  python -m hydracontext.demo "why is checkout failing in prod"
"""
from __future__ import annotations

import argparse
import json

from .config import CONFIG
from .store import HydraContextStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", nargs="?", default="why is checkout failing in prod")
    args = parser.parse_args()

    store = HydraContextStore()
    store.verify()
    pack = store.plan(args.task)

    print(json.dumps(pack.to_dict(), indent=2))
    print()
    print(f"task:              {args.task}")
    print(f"graph round-trips: {pack.round_trips()}")
    print(f"skills loaded:     {[s['name'] for s in pack.skills]}")
    print(f"tools bound:       {len(pack.tools)} of ~{len(pack.tool_names)} needed")
    print(f"entities resolved: { {m: e['name'] for m, e in pack.entities.items()} }")
    print(f"total context ms:  {sum(ms for _, ms in pack.queries):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
