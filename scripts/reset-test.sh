#!/usr/bin/env bash
# Remove every disposable test project (containers, networks and volumes).
# Only projects named taxdome-test-* are touched; the normal "taxdome" stack is left alone.
set -euo pipefail
cd "$(dirname "$0")/.."
for project in $(docker compose ls -a --format json | python3 -c \
    'import json,sys; print(" ".join(p["Name"] for p in json.load(sys.stdin) if p["Name"].startswith("taxdome-test-")))'); do
  echo "removing $project"
  docker compose -p "$project" -f compose.yaml -f compose.test.yaml --profile test down -v --remove-orphans
done
