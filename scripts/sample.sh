#!/usr/bin/env bash
# Send the official three-payment sample (or another JSON file) to the running stack.
# Usage: scripts/sample.sh [path/to/body.json]
set -euo pipefail
cd "$(dirname "$0")/.."
body="${1:-examples/sample.json}"
curl -sS -i -X POST "http://localhost:${HTTP_PORT:-8080}/payments/batch" \
  -H 'Content-Type: application/json' --data-binary @"$body"
echo
