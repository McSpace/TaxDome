# TaxDome payment service architecture

This is the agreed design for the challenge submission; it is implemented in this repository (see the [README](../README.md)). See [the editable component diagram](architecture.excalidraw). The five-page **TA Firm Payments.pdf**, the architecture discussion, and the PostgreSQL locking discussion were reviewed. Conditional idempotency and self-payment semantics below are explicit project assumptions beyond the challenge's basic contract.

## Docker Compose stack

| Service | Responsibility |
| --- | --- |
| `nginx` | Public HTTP entry point; round-robin routing to `api-1`, `api-2`, and `api-3`. Fail over to another instance only when one cannot be reached; never resend a payment POST that any instance received, especially in OFF mode. |
| `api-1..3` | Three identical, stateless Python/FastAPI instances. Validate JSON, convert decimal USD strings exactly to integer cents, call the stored function through an asynchronous PostgreSQL connection pool (for example, psycopg), and map results to HTTP. No ORM or process-local correctness locks. |
| `postgres` | Shared source of truth: existing `firms` and `payments` tables, balances, payment history, and the payment stored function. Keep the supplied columns/types; add no application tables. |
| `test-runner` | Independent, one-shot Pytest service, enabled through a Compose test profile. Sends HTTP traffic through Nginx, verifies each API instance directly on the private network, and uses a separate database connection for fixtures and assertions. Exits nonzero on failure. |

Only Nginx needs a host-facing port. PostgreSQL and APIs communicate on the private Compose network; PostgreSQL uses a persistent volume. Initialize schema, function, configuration, and sample data before API readiness; start tests only after all three APIs and Nginx are ready. Tests use an isolated disposable database/volume and must never reset a live environment.

## Atomic SQL execution and locking

Each batch has exactly one payer and runs in one explicit database transaction at `READ COMMITTED`. The stored function implements the entire business algorithm; the API commits before returning success. A function does not commit independently.

1. Validate the complete batch, resolve public UUIDs to internal firm IDs, and reject unknown firms or invalid input. Require positive amounts with at most two decimal places; never use floating point. Reject an empty batch as a project assumption.
2. Lock every distinct participating firm row using `SELECT ... ORDER BY id FOR UPDATE`, acquiring locks in ascending internal ID order everywhere, including reciprocal transfers. Self-payments lock one row once. Hold locks through commit/rollback.
3. **After acquiring locks**, read payment history in a subsequent SQL statement and classify duplicates according to the effective mode. The function must be `VOLATILE`, so the post-wait read sees payments committed by a preceding transaction at this isolation level. The locked payer serializes every batch for that payer, including concurrent attempts to insert a previously absent key; no uniqueness constraint on payments is required.
4. Calculate gross outgoing cents for the payments that will actually be inserted, including self-payments. Require the locked payer's starting balance to cover that entire sum. Do not subtract self-payment credits or use any incoming payment from this batch to fund outgoing payments. Already committed external credits visible after locking may be used.
5. Insert the accepted payment rows and apply aggregated per-firm balance deltas in the same transaction. A self-payment creates a payment row but has zero net balance delta. Calculate sums in a wider numeric type and reject values or final balances outside the supplied `INTEGER` range.
6. Commit all payment rows and balance changes together. Any conflict, insufficient funds, validation failure, or database exception rolls back the entire batch. Return 201 after success (including an all-duplicate no-op), 422 for insufficient funds; use 409 for an amount conflict as a project convention. Return inserted/skipped counts explicitly.

All payment and balance mutations must follow this function's locking protocol; restrict the runtime database role to function execution and necessary reads. Keep initialization/admin writes outside serving traffic. Balance deltas preserve seeded opening balances; recomputing balances from payment history alone would erase those opening funds. A database failure must not become a partial success. Retry only transactions known to have rolled back; an unknown commit outcome is unsafe to retry automatically in OFF mode.

## Conditional payment-level idempotency

Both modes are supported; **ON is the default**. The key is `(payer_firm_id, payee_firm_id, description)`, using exact description equality without trimming or case folding. Amount is compared in cents and is not part of the key.

- **ON:** an existing key with the same amount is skipped. A differing amount rejects the entire batch, including otherwise new payments. Apply the same rule within the submitted batch: equal repeats produce one new row; unequal repeats reject everything. A mixture of new payments and equal repeats is accepted; only new payments affect balances and the funds check.
- **OFF:** insert every valid submitted payment, including identical keys and amounts. All submitted amounts contribute to gross outgoing funds required.

This is a domain assumption, not a batch identity or proof of a network retry: two intentional payments with the same key cannot be distinguished in ON mode. Repeated payees with different descriptions remain separate payments, as in the challenge example.

## One effective mode and drift prevention

Independent API environment flags can silently produce inconsistent financial behavior. Make the stored function authoritative: deploy it with a function-local PostgreSQL setting, e.g. `SET app.payment_idempotency = 'on'`. The function reads and validates that setting; its function-local value overrides caller/session settings. Only the migration owner may change the function; API request parameters and API environment variables cannot select the mode. A read-only diagnostic endpoint on each API reports instance identity and the effective mode from that function's database configuration, rather than a cached local flag.

The test runner has an expected mode, default ON. Before running payment tests, it checks the database configuration, all three APIs directly, and the Nginx-facing diagnostic endpoint; any mismatch or missing/invalid value aborts the run. Direct checks are essential: repeated load-balanced requests do not prove every instance was checked. Run the full suite separately for ON and OFF against fresh seeded databases. Change mode only while payment traffic is stopped, then recheck readiness and test expectations. Do not reinterpret OFF-mode duplicate history by switching to ON on a populated database.

Verify the challenge's three-payment sample and exact resulting balances, insufficient-funds rollback, concurrent overspending, concurrent credits, reciprocal transfers, self-payments, duplicate races, mixed batches, amount conflicts, and failure rollback. Assert balances, payment rows, and total-money conservation through the independent database connection.

The eventual repository must also include runnable Compose/configuration files, README startup/verification instructions and assumptions, commit history, unedited AI conversation logs, and the challenge's time-spent and satisfaction answers. These two architecture artifacts do not replace those submission requirements.
