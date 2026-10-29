#!/usr/bin/env bash
# Show firms, payments and the installed idempotency mode of a Compose project's database.
# Usage: scripts/db-state.sh [compose project name]   (default: taxdome)
set -euo pipefail
cd "$(dirname "$0")/.."
project="${1:-taxdome}"
docker compose -p "$project" exec -T postgres psql -U postgres -d taxdome -P pager=off <<'SQL'
SELECT id, name, balance_cents, to_char(balance_cents / 100.0, 'FM999,999,990.00') AS balance_usd, uuid
  FROM app.firms ORDER BY id;
SELECT id, payer_firm_id, payee_firm_id, amount_cents, description FROM app.payments ORDER BY id;
SELECT sum(balance_cents) AS total_balance_cents FROM app.firms;
SELECT cfg AS function_mode FROM pg_proc p, unnest(p.proconfig) cfg
 WHERE p.oid = 'app.process_payment_batch(text,jsonb)'::regprocedure AND cfg LIKE 'app.%';
SQL
