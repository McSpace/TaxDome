#!/usr/bin/env bash
# Stop the normal stack. The database volume is kept, so balances and payments survive.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
