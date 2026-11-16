#!/usr/bin/env bash
# Start a local graph-node in Docker backed by a local directory store.
# Usage: scripts/run_node.sh   (idempotent; restarts the container)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$ROOT/.runtime"
mkdir -p "$RUNTIME/store" "$RUNTIME/cache"

# LocalFileSystem does not implement conditional puts (PutMode::Update), so a
# writer lease left by a previous container run cannot be CAS-taken-over and
# every mutation fails with `internal query execution error`. Dropping the
# stale leases lets the fresh node acquire them with Create mode.
find "$RUNTIME/store" -path '*_writer_leases*' -type f -delete 2>/dev/null || true

# Auth token must be at least 32 characters.
printf '%s\n' 'hydra-hackathon-local-dev-token-32ch' > "$RUNTIME/auth-token"
chmod 644 "$RUNTIME/auth-token"

docker rm -f hydradb-node 2>/dev/null || true

docker run -d --name hydradb-node \
  -p 7687:7687 -p 8443:8443 -p 9090:9090 \
  -v "$RUNTIME/store":/data/store \
  -v "$RUNTIME/cache":/var/cache/slatedb \
  -v "$RUNTIME/auth-token":/run/auth-token:ro \
  -e CLOUD_PROVIDER=local \
  -e LOCAL_PATH=/data/store \
  -e GRAPH_NAMESPACE=agent \
  -e GRAPH_ID=default \
  -e GRAPH_CELL_ID=cell-0 \
  -e GRAPH_CELLS=cell-0 \
  -e GRAPH_NODE_ID=node-0 \
  -e GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687 \
  -e GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687 \
  -e GRAPH_BOLT_ADDR=0.0.0.0:7687 \
  -e GRAPH_HTTP_ADDR=0.0.0.0:8443 \
  -e GRAPH_ADMIN_ADDR=0.0.0.0:9090 \
  -e GRAPH_DATA_CACHE_DIR=/var/cache/slatedb \
  -e GRAPH_AUTH_TOKEN_FILE=/run/auth-token \
  -e GRAPH_ALLOW_PLAINTEXT=true \
  -e RUST_MIN_STACK=33554432 \
  -e RUST_LOG=info \
  ghcr.io/hydra-db/hydradb:latest

echo "waiting for readiness on :9090 ..."
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:9090/readyz >/dev/null 2>&1; then
    echo "hydradb-node READY  (bolt :7687, http :8443, admin :9090)"
    exit 0
  fi
  if ! docker inspect -f '{{.State.Running}}' hydradb-node 2>/dev/null | grep -q true; then
    echo "container exited; last logs:" >&2
    docker logs --tail 30 hydradb-node >&2
    exit 1
  fi
  sleep 1
done
echo "not ready after 60s; logs:" >&2
docker logs --tail 30 hydradb-node >&2
exit 1
