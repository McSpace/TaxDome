#!/usr/bin/env bash
# Run the integration suite in disposable Compose projects: one per idempotency mode.
# Usage: scripts/test.sh [on|off|all] [extra pytest args...]
set -euo pipefail
cd "$(dirname "$0")/.."

target="${1:-all}"
shift || true
case "$target" in
  on) modes=(on) ;;
  off) modes=(off) ;;
  all) modes=(on off) ;;
  *) echo "usage: $0 [on|off|all] [pytest args...]" >&2; exit 64 ;;
esac

export HOST_UID="$(id -u)" HOST_GID="$(id -g)"

run_mode() {
  local mode="$1"; shift
  local project="taxdome-test-${mode}"
  local compose=(docker compose -p "$project" -f compose.yaml -f compose.test.yaml --profile test)
  local status=0

  # ON runs with the variable unset to prove the default; OFF is set explicitly.
  if [[ "$mode" == "on" ]]; then
    unset PAYMENT_IDEMPOTENCY_MODE
  else
    export PAYMENT_IDEMPOTENCY_MODE="$mode"
  fi

  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  echo "=== [$mode] building and starting $project"
  "${compose[@]}" build --quiet
  EXPECTED_IDEMPOTENCY_MODE="$mode" "${compose[@]}" run --rm test-runner \
    pytest tests -p no:cacheprovider -o junit_suite_name="taxdome-${mode}" \
    --junitxml="/srv/results/junit-${mode}.xml" "$@" || status=$?

  echo "=== [$mode] removing $project"
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  return "$status"
}

overall=0
for mode in "${modes[@]}"; do
  if ! run_mode "$mode" "$@"; then
    echo "=== [$mode] FAILED" >&2
    overall=1
  fi
done
exit "$overall"
