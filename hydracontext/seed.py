"""Bootstrap + seed the HydraDB context graph, then print stats.

Run:  python -m hydracontext.seed          (seed if empty)
      python -m hydracontext.seed --reset  (wipe known ids and reseed)
"""
from __future__ import annotations

import argparse
import sys

from .config import CONFIG
from .seed_data import build_seed
from .store import AGENT_ID, BATCH_CHUNK, HydraContextStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete seed ids first")
    args = parser.parse_args()

    store = HydraContextStore()
    try:
        store.verify()
        print(f"connected to {CONFIG.http_uri} (namespace={CONFIG.namespace})")
    except Exception as exc:  # noqa: BLE001
        print(f"cannot reach HydraDB: {exc}", file=sys.stderr)
        print("start a node first:  scripts/run_node.sh", file=sys.stderr)
        return 1

    if args.reset:
        seed = build_seed()
        ids = [AGENT_ID] + [
            row["id"]
            for group in ("servers", "tools", "skills", "entities", "aliases")
            for row in seed[group]
        ]
        # batched delete, chunked well under the 1024 cap
        from .store import BATCH_CHUNK

        cypher = "UNWIND $rows AS row MATCH (n {id: row.id}) DETACH DELETE n"
        for i in range(0, len(ids), BATCH_CHUNK):
            store._run(cypher, "reset", rows=[{"id": x} for x in ids[i : i + BATCH_CHUNK]])
        print(f"deleted {len(ids)} known ids")

    seed = build_seed()
    store.seed(**seed)
    stats = store.stats()
    print("graph stats:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
