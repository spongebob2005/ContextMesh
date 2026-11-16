"""Demo: plan context for a task, no LLM needed.

Run:  python -m hydracontext.plan "why is checkout failing in prod"
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import CONFIG
from .store import HydraContextStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", help="the task text")
    args = parser.parse_args()

    store = HydraContextStore()
    try:
        store.verify()
    except Exception as exc:  # noqa: BLE001
        print(f"cannot reach HydraDB: {exc}", file=sys.stderr)
        return 1

    pack = store.plan(args.task)
    print(json.dumps(pack.to_dict(), indent=2))
    print(
        f"\nround-trips: {pack.round_trips()}   "
        f"skills: {[s['name'] for s in pack.skills]}   "
        f"tools: {pack.tool_names}   "
        f"entities resolved: {pack.entities}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
