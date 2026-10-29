#!/usr/bin/env bash
# Prove that a restart and a repeated initialization keep mode, payments and balances.
# Runs in its own disposable project; never touches the normal stack's volume.
set -euo pipefail
cd "$(dirname "$0")/.."

project="taxdome-test-restart"
compose=(docker compose -p "$project" -f compose.yaml -f compose.test.yaml)
trap '"${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

state() {
  "${compose[@]}" exec -T postgres psql -U postgres -d taxdome -Atc \
    "SELECT string_agg(id || ':' || balance_cents, ',' ORDER BY id) FROM app.firms;
     SELECT count(*) || ' payments' FROM app.payments;
     SELECT cfg FROM pg_proc p, unnest(p.proconfig) cfg
      WHERE p.oid = 'app.process_payment_batch(text,jsonb)'::regprocedure AND cfg LIKE 'app.%';"
}

post_sample() {
  "${compose[@]}" exec -T api-1 python -c '
import sys, urllib.request
request = urllib.request.Request("http://nginx:8080/payments/batch", data=sys.stdin.buffer.read(),
                                 headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(request).status)' < examples/sample.json
}

"${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
echo "=== [restart] starting fresh stack"
"${compose[@]}" up -d --build --wait --quiet-pull >/dev/null
status="$(post_sample)"
[[ "$status" == "201" ]] || { echo "sample returned $status" >&2; exit 1; }
before="$(state)"
echo "$before"

echo "=== [restart] stopping and starting again (volume kept, db-init re-runs)"
"${compose[@]}" down >/dev/null
"${compose[@]}" up -d --wait >/dev/null
after="$(state)"

if [[ "$before" != "$after" ]]; then
  echo "=== [restart] FAILED: state changed across restart" >&2
  echo "$after" >&2
  exit 1
fi
expected="1:3674875,2:170075,3:1405050"
[[ "$(head -n1 <<<"$after")" == "$expected" ]] || { echo "unexpected balances" >&2; exit 1; }
echo "=== [restart] OK: balances, payments and mode preserved"
