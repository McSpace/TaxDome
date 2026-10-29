#!/usr/bin/env bash
# Build and start the normal stack (persistent volume), waiting until every API is ready.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build --wait
docker compose ps
echo "Service ready at http://localhost:${HTTP_PORT:-8080}"
