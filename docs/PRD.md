# Product requirements: TaxDome bulk firm payments

Version 1.0 | 29 October 2026 | Ready for implementation

## 1. Purpose and authority

Build a reproducible backend service that transfers USD funds from one firm's platform balance to one or more firms in a single HTTP request. Accounting firms use it to settle outsourcing and referral obligations in bulk. The submission must demonstrate correct behavior when requests run concurrently on three application instances sharing PostgreSQL.

This PRD is the implementation contract. Read it together with [architecture.md](architecture.md) and the [active test catalogue](Firm_Payments_Test_Scenarios.md). The original [challenge PDF](sources/TA%20Firm%20Payments.pdf) defines the baseline. Later explicit project decisions add conditional payment-level idempotency, self-payment rules, and a concrete deployment. This PRD resolves previously unspecified interface details as implementation defaults; those defaults are listed in section 15. Historical source documents and the archived test catalogue are evidence, not extra feature requirements. Follow this PRD when they differ; do not implement hypothetical extensions from historical scenarios.

Deliver a runnable repository, not a UI or a production banking platform. The developer and reviewer are the direct users. A reviewer must be able to clone, start the stack, send the sample request, run both mode suites and inspect persistent results without installing Python or PostgreSQL locally.

## 2. Scope

Required: a JSON payment API, exact monetary validation, one PostgreSQL business function, atomic balance and payment writes, concurrency safety, two static idempotency modes, three identical FastAPI instances behind Nginx, independent Pytest runner, sample seed, diagnostics, documentation and submission evidence.

Excluded from implementation and tests: authentication/authorization, tenants, signatures, request or batch identity keys, idempotency metadata tables, expiry/cleanup jobs, runtime mode changes, mixed-mode serving instances, firm CRUD or administrative balance APIs, concurrent alternative writers, ledger repair, payment cancellation/refunds, external payment processors, multiple currencies, queues, caches, Kubernetes, high availability, capacity benchmarks and dedicated chaos-testing infrastructure. Targeted rollback, lock-timeout and duplicate-delivery tests remain required. No web frontend is needed; generated API documentation is sufficient.

## 3. Runtime components

Use Docker Compose with `postgres`, `nginx`, `api-1`, `api-2`, `api-3`, and a one-shot `test-runner` under a test profile. Use Python, FastAPI, Pydantic, psycopg's asynchronous driver/pool, Pytest and an HTTP test client such as HTTPX. Use PostgreSQL 18 and compatible pinned Python dependencies; choose and record exact image/dependency versions during implementation. Use SQL/PLpgSQL directly, with no ORM. All API containers run the same image and differ only in instance identity.

Expose Nginx at `http://localhost:8080`. Nginx distributes requests using round-robin across all three APIs; prohibit upstream replay of payment POST requests. APIs and PostgreSQL have no host ports in the standard configuration. All services share a private network; PostgreSQL has a persistent volume. Test fixtures live only in a separately named disposable Compose project/volume. The runner reaches APIs directly for diagnostics and controlled concurrency, and Nginx for normal integration traffic. Tests never run inside API processes.

Initialization installs schema, functions, privileges, static mode and sample seed before APIs become ready. Dependencies use real health/readiness checks and bounded waiting, rather than fixed startup sleeps. Initialization/seed must not rerun destructively on restart. Repeated startup preserves payments and balances. An explicit, documented reset command operates only on the disposable project.

## 4. HTTP contract

### Create a batch

`POST /payments/batch` with `Content-Type: application/json` (an optional UTF-8 charset is accepted). No identity header, payer header, mode override or query parameters are part of this contract. Reject unknown JSON attributes at every object level.

```json
{
  "payer_firm_uuid": "3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41",
  "payments": [
    {
      "amount": "1200.75",
      "payee_firm_uuid": "8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10",
      "description": "Bookkeeping cleanup, 3 clients"
    }
  ]
}
```

The top level must be an object with one payer UUID and a nonempty payments array. Entries contain exactly `amount`, `payee_firm_uuid`, and `description`. No implicit string/number/boolean coercion. Validate the entire input before accepting any payment. Different entries may target the same payee.

Input policies:

| Input | Rule |
| --- | --- |
| UUID | String in the hyphenated 8-4-4-4-12 hexadecimal form; accept letter case and normalize to lowercase for lookup. Reject whitespace, braces, URNs and internal numeric IDs. Seeded UUIDs use lowercase. |
| Amount | ASCII string matching `[0-9]+(?:\.[0-9]{1,2})?` over its entire length, at most 32 characters; exact parsed cents must be positive and no greater than 2147483647. Leading zeros are accepted. |
| Description | Required string, 0 to 1024 Unicode code points inclusive; empty and whitespace-only strings are accepted and preserved. Reject U+0000. No trimming, case folding or Unicode normalization. |
| Batch size | 1 to 1000 entries inclusive, before duplicate filtering. |
| Body | At most 1 MiB (1048576 bytes). Enforce the same bound at Nginx and direct API entry. |
| Encoding | UTF-8 without a byte-order mark. Reject invalid UTF-8 and duplicate JSON member names. |

Parse money using decimal/integer arithmetic only: `"6250"` becomes 625000 cents; `"5800.5"` becomes 580050; `"25"`, `"25.0"` and `"25.00"` have equal amounts. Reject signs, spaces, exponent notation, commas, currency symbols, non-ASCII digits, incomplete decimals, zero, negatives and more than two fractional digits. Do not round invalid input.

Successful requests return HTTP 201 only after commit:

```json
{
  "inserted_count": 1,
  "skipped_count": 0,
  "gross_outgoing_cents": 120075,
  "idempotency_mode": "on"
}
```

`inserted_count + skipped_count` equals input entry count. Gross outgoing is the sum of newly inserted entries, including self-payments; it is not the net balance delta. In OFF mode skipped count is always zero. An all-duplicate ON batch returns 201 with zero inserted, zero gross outgoing and every entry skipped, even if the payer now has zero funds. Do not return a synthetic batch ID, durable request receipt, or claim to replay the original response. No balance/history retrieval API is required.

### Errors and precedence

Use a consistent JSON envelope for application errors:

```json
{"error":{"code":"insufficient_funds","message":"Payer balance cannot cover new outgoing payments."}}
```

An optional `details` array may identify zero-based entry indexes and field paths. Do not expose SQL, credentials or stack traces. A request that fails has no new payment rows and no changed balances. PostgreSQL sequence gaps after rollback are allowed.

| HTTP | Code / condition |
| --- | --- |
| 400 | `invalid_json`: malformed JSON, duplicate members, invalid encoding or empty body |
| 413 | `request_too_large`: body exceeds 1 MiB |
| 415 | `unsupported_media_type`: absent or unsupported Content-Type |
| 422 | `validation_error`: shape, type, limits, UUID or amount format errors |
| 422 | `unknown_firm`: syntactically valid payer/payee UUID is absent |
| 422 | `insufficient_funds`: locked payer balance is below gross new outgoing |
| 422 | `numeric_overflow`: stored amount or resulting balance is outside allowed range |
| 409 | `payment_amount_conflict`: an ON-mode key has unequal amounts |
| 503 | `temporarily_unavailable`: connection/pool acquisition failure, lock/statement timeout or known rolled-back transient database failure |
| 503 | `commit_outcome_unknown`: connection fails while commit outcome cannot be determined; do not assert rollback |
| 500 | `internal_error`: unexpected application/database failure; rollback when possible |

Nginx may generate 502/503/504 when no API can answer; document these transport-level outcomes rather than promising an application envelope in that situation. Configure its 413 response as JSON. Unsupported methods return 405 and unknown routes 404.

Precedence: byte/media/JSON checks, full field validation, firm existence, ON-mode amount conflicts, funds, final balance range, writes, commit. Input amount bounds belong to field validation. If several field errors exist, report a deterministic order by input index/path or aggregate them. Do not treat a database failure as a business 422. An uncertain commit may already have persisted; see section 10.

### Diagnostics

- `GET /health/live`: 200 if the process can respond; no database dependency.
- `GET /health/ready`: 200 with `instance_id` and `idempotency_mode` only when DB connectivity, required function/schema, privileges and valid function mode are confirmed; otherwise 503.
- `GET /diagnostics`: 200 with `instance_id` (`api-1`, `api-2` or `api-3`) and the effective database-derived `idempotency_mode` (`on`/`off`); 503 for missing/invalid configuration or unavailable DB.
- Generate OpenAPI for the payment and diagnostic contracts.

## 5. Data contract

Keep exactly the supplied application tables and column names/types:

| Table | Columns |
| --- | --- |
| `firms` | `id INTEGER`, `name TEXT`, `balance_cents INTEGER`, `uuid TEXT` |
| `payments` | `id INTEGER`, `payer_firm_id INTEGER`, `payee_firm_id INTEGER`, `amount_cents INTEGER`, `description TEXT` |

No extra columns, application tables, persisted batch identities or mode table. Use PostgreSQL functions and roles for behavior/configuration. IDs are internal; UUIDs are public. Firm UUID-to-ID mappings are immutable during serving traffic. Firms are seeded; there is no runtime creation/deletion path.

Schema setup may define primary keys, sequence-backed defaults for payment IDs, nonnull constraints, unique firm UUIDs, foreign keys, positive payment amounts and nonnegative balances using these columns. These integrity constraints/indexes do not change the supplied column contract. Do not add a unique payment-key constraint: OFF must permit repeated keys. A nonunique lookup index on payer/payee/description may be added. Configure description comparisons with deterministic exact equality (e.g. `COLLATE "C"` for the relevant expression/index); visually equal Unicode strings are distinct unless their decoded strings match exactly.

Keep stored monetary values within 0..2147483647 for balances and 1..2147483647 for payments. Use wider arithmetic for sums and candidate balance calculations before casting. Initial balances are opening funds not represented by rows in `payments`. Preserve them; never rebuild current balances by summing this payment table alone.

## 6. Business rules and conditional idempotency

Every batch has exactly one payer. It may pay any existing firm, including itself. In a fresh self-payment, store one payment row and apply a zero net balance delta. Require sufficient funds for the full gross self-payment amount before crediting it back. Example: balance 10000 cents, self-payment 10000 and external payment 10000 requires 20000 cents and fails as a whole. Payment ordering cannot change this result.

Compute funds from the locked starting balance and accepted new entries only. Do not use credits originating in this batch as funding. A credit committed by another transaction before this batch obtains its row locks may be used. An incoming request that has not committed cannot be assumed to provide funds.

Support two equally maintained deployment modes; default is ON:

| Situation | ON | OFF |
| --- | --- | --- |
| No historical matching key | Insert a new payment | Insert a new payment |
| Same historical key and equal cents | Skip the entry | Insert another payment |
| Same historical key and unequal cents | Reject entire batch with 409 | Insert another payment |
| Equal same-key entries in one new batch | Insert first occurrence; skip subsequent equal entries | Insert every entry |
| Unequal same-key entries in one batch | Reject entire batch with 409 | Insert every entry |
| Mixture of new and historical equal entries | Insert new, skip equal repeats | Insert every entry |
| Funds check | Gross sum of entries actually inserted | Gross sum of every submitted entry |

The key is `(payer_firm_id, payee_firm_id, exact description)`. Amount is not part of it. No batch-level deduplication, retention window, request fingerprint or externally supplied payment identity exists. Different descriptions and different payer/payee pairs are different keys. In ON, equal-looking intentional obligations with the same key/amount are skipped; clients must choose a different description to express another obligation. Describe this limitation prominently in README. Batch permutations do not change the final monetary result.

All submitted entries must pass validation and reference existing firms even if they would otherwise be duplicates. Detect every amount conflict before funds/writes. On clean ON deployments each key has at most one historical row. Do not support changing OFF history into ON history; if nonconforming historical rows are discovered, fail safely rather than arbitrarily selecting one amount.

## 7. Stored-function transaction algorithm

Implement a `VOLATILE`, `PARALLEL UNSAFE` PL/pgSQL function, for example `app.process_payment_batch(payer_uuid text, entries jsonb) RETURNS jsonb`. Entries passed by the API contain payee UUID, exact description and integer amount cents. This internal form must also be validated inside the function; restricted direct callers cannot bypass monetary or batch rules. The function, not the API, decides duplicates, checks funds and performs business mutations.

The API acquires a pooled connection and opens one explicit `READ COMMITTED` transaction. One batch equals one function invocation and one commit. Do not commit per payment. The function executes:

1. Read and validate its authoritative function-local mode. Validate internal batch types, count, positive integral cents, description limits and payer/payee resolution. No writes yet.
2. Build the distinct set of participating firm IDs. Acquire `FOR UPDATE` row locks in ascending `firms.id` order for every participant, including recipients, before inserting payments or changing balances. The payer is not automatically locked first: use global ID order. Lock self once. A sorted loop that locks one row per statement is acceptable and makes order explicit.
3. Verify all resolved rows still exist and read locked balances. Runtime firm mapping mutation is unsupported. All conforming writers use this same protocol.
4. In a subsequent SQL statement after all locks have been acquired, read relevant payment history and classify ON-mode entries, including within-input repeats. Do not combine the lock and history read into a single pre-wait snapshot. `READ COMMITTED` and a `VOLATILE` function are required for the post-wait statement to see preceding commits. Serializing on the payer protects even keys that have no existing payment row; locking only existing payment rows would not do so.
5. Reject any unequal-amount conflict. Compute new entries and gross sum with wide arithmetic. Require payer balance >= gross sum, including self entries. A zero-new-entry batch succeeds with no mutation.
6. Aggregate net deltas by firm: subtract gross new outgoing from the payer and add accepted incoming to each payee. A firm can have both terms. Precompute final balances and validate ranges before writing.
7. Insert each accepted original payment as a distinct row (except skipped ON repeats) and apply the per-firm deltas. Balance changes must derive from exactly the inserted set. Keep rows locked until transaction end. Return counts, gross sum and mode to the API.
8. API commits, then sends 201. Any exception before successful commit rolls back the whole transaction. Release/clean up connections on every path; discard unusable connections. Never return 201 on an unconfirmed commit.

The all-row ordering prevents cycles between conforming payment transactions. Shared recipients serialize updates without lost credits. Disjoint firm sets can proceed independently. No application mutex, table-wide payment lock or distributed lock is required. PostgreSQL still controls timeouts and error handling; correct ordering does not justify infinite waits.

The function runs with controlled privileges (e.g. `SECURITY DEFINER` owned by a dedicated non-login owner). Revoke default PUBLIC execute, grant only the intended API role, schema-qualify objects, and pin a trusted search path. The API role cannot mutate tables, change function definition/mode, or create objects in the trusted schema. Test fixture credentials are separate and not supplied to APIs.

## 8. Static mode and consistency

Use one Compose deployment input `PAYMENT_IDEMPOTENCY_MODE`, accepting exactly `on` or `off`, default `on`. An initialization/migration action embeds it in the stored function's configuration as `SET app.payment_idempotency = 'on'` or `'off'`. Only the owner can change that definition. Function-local configuration is the effective mode for every call and overrides caller session settings; code inside the function must not replace it with caller input. Do not copy an environment flag into independent API business branches.

Diagnostics read the setting from metadata for the exact schema-qualified function signature (not an arbitrary overload or the API session's `current_setting`). Compare the configured mode inside function execution as part of integration tests. Fail readiness on missing/invalid configuration. On reuse of an existing volume, compare requested deployment mode against installed function mode and fail startup if they differ; do not silently relabel existing data.

The runner input `EXPECTED_IDEMPOTENCY_MODE` defaults to `on`. Before any payment test, compare its expectation with database function metadata, each of the three direct diagnostics endpoints, and Nginx diagnostics. Check instance identities as well as modes and abort on a mismatch. This is startup verification, not support for mixed-mode operations. Never infer coverage of all instances from repeated round-robin calls alone.

Run ON and OFF in separate fresh Compose projects/databases. A mode change requires stopping traffic and recreating a disposable database for this submission; there is no mode-switch API, live transition test or migration of duplicate history.

## 9. Timeouts, logging and operational behavior

Use bounded configurable resource waits with documented defaults: pool acquisition 5 seconds, database lock timeout 5 seconds, statement timeout 15 seconds; choose an Nginx upstream response timeout longer than the database statement timeout (30 seconds). Roll back known failed transactions. Do not add automatic transaction retries in this version. Test lock/statement timeout using isolated fixtures and temporary test overrides.

Record structured request completion logs with request correlation ID, instance, outcome/error code, elapsed time, effective mode and counts when available. Correlation IDs are observability only, not deduplication identities. Do not log credentials or entire descriptions/bodies by default. No dashboard/metrics system is required. Keep test-only synchronization/failure hooks disabled in the standard app and unreachable through public production routes; temporary SQL fault fixtures may be used in the isolated test database.

## 10. Retry semantics and unknown outcomes

Client retries submit the same ordinary body. In ON, committed equal entries are skipped across instances, while altered amounts conflict. In OFF, each successful delivery creates all requested rows again if funds permit. A committed request whose HTTP response was lost may have changed balances even though the client saw failure. A lost database commit acknowledgment is also ambiguous. Never promise exactly-once delivery or claim that every 503 implies no changes. Do not automatically retry unknown outcomes at the application or proxy layer.

Test duplicate-delivery semantics by discarding a received response and retrying, and by releasing concurrent identical requests to separate APIs. A dedicated broken-network proxy or process-killing test framework is not required. Controlled errors before commit must still prove rollback of both balances and inserted payment rows.

## 11. Official seed and walkthrough

Seed the following rows with empty payment history:

| ID | Name | UUID | Balance cents |
| --- | --- | --- | ---: |
| 1 | Pinecrest CPA Group | 3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41 | 5000000 |
| 2 | Lopez Bookkeeping | 8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10 | 50000 |
| 3 | Nair Tax Services | e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25 | 200000 |

Save a runnable sample JSON paying, from Pinecrest: `"6250"` to Nair with `"Overflow returns, August 2026"`; `"5800.5"` to Nair with `"Amended returns, August 2026"`; and `"1200.75"` to Lopez with `"Bookkeeping cleanup, 3 clients"`.

In either mode on a fresh seed: HTTP 201, inserted 3, skipped 0, gross 1325125 cents. Final balances are Pinecrest 3674875, Lopez 170075 and Nair 1405050 cents. Total balance stays 5250000 cents. The two Nair payments remain two rows. Keep this separate from the introductory two-payment example in the PDF.

## 12. Verification and acceptance criteria

Use [the active 151-case catalogue](Firm_Payments_Test_Scenarios.md) as input coverage. Preserve its IDs in tests/reports. Parameterize equivalent inputs; do not create a separate test function for every textual variant. All active cases must be mapped to an automated test or a documented equivalent parametrized test. The archived 220-case revision is not a test implementation backlog.

The runner uses real PostgreSQL, real HTTP and all three API processes; mocks do not demonstrate concurrency correctness. Use deterministic barriers/isolated SQL fixtures for meaningful overlap, bounded waits and cleanup. Use different descriptions for unrelated outgoing operations in ON mode. Capture a consistent database snapshot after participants finish or use a read-only repeatable-read transaction when observing an in-flight operation.

| ID | Acceptance |
| --- | --- |
| AC01 | Official sample returns the exact counts, rows and balances above through Nginx in each mode. |
| AC02 | Exact balance succeeds; gross amount one cent over balance returns 422 with unchanged rows/balances. |
| AC03 | With balance 10000 cents and two concurrent distinct 8000-cent requests, exactly one commits; final balance 2000. |
| AC04 | Multiple payers crediting one recipient retain every accepted credit; simultaneous reciprocal/cyclic transfers finish within bounded waits with conserved money. |
| AC05 | Reversed input/UUID orders do not change internal ID lock ordering; unrelated locked firms do not block disjoint payments. |
| AC06 | Self-payment at the balance succeeds with a row and zero net delta; self-payment above balance fails; self plus external must cover gross sum. |
| AC07 | In ON, same key/equal cents is skipped sequentially and concurrently; different cents rejects the entire batch with 409. In OFF, every valid occurrence is inserted if funded. |
| AC08 | In ON, new-plus-repeat inserts only new entries, new-plus-conflict inserts nothing, identical within-batch entries create one row, unequal amounts under one key reject all. |
| AC09 | All-duplicate ON request succeeds after funds are exhausted; mixed batch requires only the new gross sum. |
| AC10 | Input failures, unknown firms, range failures and targeted errors after inserts/balance statements/before commit leave no partial business mutations. Sequence gaps are allowed. |
| AC11 | Equivalent amount spellings produce equal cents; exact description differences remain distinct keys. Every specified input boundary has coverage. |
| AC12 | A failed transaction does not poison its pooled connection; a later valid request succeeds. Timeouts are bounded and never return 201. |
| AC13 | All diagnostics match the authoritative mode; a mismatched runner aborts before payment cases. Default startup is ON; explicit OFF works on a fresh deployment. |
| AC14 | Discarded-response retry produces documented ON/OFF outcomes across different instances; proxy configuration does not replay POST automatically. |
| AC15 | Restart preserves mode, rows and balances; explicit initialization is non-destructive; sample and tests are reproducible from a clean checkout. |

For each committed batch verify: no negative balances, correct per-firm deltas, inserted rows match accepted inputs, skipped entries have no delta, and sum of all balances is conserved. Across a fixture, verify each current balance equals its fixture opening balance plus committed incoming minus outgoing. An aborted batch leaves these values unchanged. Never count a sequence increment as an inserted payment.

Emit readable console results and machine-readable JUnit XML, with case IDs and mode. A nonzero runner exit fails the test command. Provide one documented command/script to run both modes in separate fresh projects, propagate failures and clean up test resources without deleting the normal stack volume.

## 13. Repository deliverables and definition of done

Provide an English README, dependency lock/pins, Dockerfiles, Compose and Nginx configuration, SQL schema/function/privilege/seed initialization, application code, sample JSON, tests, and mode-specific test commands. Suggested organization: `app/`, `db/`, `nginx/`, `tests/`, `scripts/`, `examples/`, `docs/`, `evidence/`. Keep architectural Markdown, editable Excalidraw and PNG available in repository docs. An agent may choose equivalent file organization but must keep startup and test commands stable and documented.

README must explain design, concurrency argument, limitations of conditional idempotency, exact endpoints/errors, prerequisites, start/stop/reset, sample command, checking database state, both modes, test commands/results, assumptions, problems encountered and possible improvements. Include actual commit history and unedited AI interaction evidence with tool names and how they were used. Do not present bounded/sanitized history snapshots as a complete unedited export. Obtain a genuine export before final submission if available history is incomplete. Do not fabricate time spent, satisfaction, test results or source provenance; leave owner-supplied completion answers explicitly pending until provided.

Done means the stack builds from a clean checkout, diagnostics show all three APIs ready, all acceptance criteria and mapped in-scope tests pass in ON and OFF, sample balances match exactly, restart preservation is verified, documentation matches implementation, and no excluded features or extra application tables/columns were introduced. Publish/create a remote repository or submit a link only when separately authorized; this document requests implementation specifications, not publication.

## 14. Implementation sequence for a coding agent

1. Read this PRD, architecture and active catalogue; inspect existing workspace instructions. Record selected dependency/image versions and build the scaffold.
2. Implement schema, roles, seed, authoritative mode, and the stored function. Verify single-batch behavior, exact money, duplicate rules and rollback against real PostgreSQL.
3. Implement strict HTTP parsing/validation, transaction ownership, error mapping and diagnostics; generate OpenAPI.
4. Assemble three APIs, Nginx and health-gated Compose startup. Verify shared mode and non-destructive restart.
5. Build the isolated runner and trace active IDs to parametrized cases; add deterministic concurrency/rollback coverage, then execute both fresh-mode suites.
6. Correct any failures, produce actual reports, update README and preserve evidence/commit history. Reconcile docs with shipped behavior before declaring done.

Routine internal choices that do not alter this contract are left to the agent. Do not replace row locking with a different isolation design, introduce request keys, alter monetary storage, or silently relax the acceptance criteria. If a genuine requirement conflict prevents implementation, report it explicitly with the smallest proposed resolution.

## 15. Decisions made explicit in this PRD

Previously agreed: PostgreSQL stored business function; 3 FastAPI instances; Nginx round-robin; independent runner; unchanged application columns/tables; ON by default; payment key payer/payee/description; equal amount skipped, unequal amount rejects entire batch; OFF inserts all; one payer; self-payments permitted with gross funds required; no in-batch funding; central effective mode verified by the runner. The user's final scope decision excludes authorization, live mode transitions and other beyond-challenge tests.

Implementation defaults finalized here: endpoint names, error envelope and status mapping beyond the challenge's 201/insufficient-funds 422, strict unknown/duplicate member handling, lowercase UUID lookup, empty description acceptance, concrete input/resource limits, no automatic retries, diagnostic fields, test report format, schema integrity constraints using supplied columns, and controlled owner-function privileges. These are explicit product choices, not claims about requirements stated in the PDF.

## 16. Supporting technical references

The locking and transaction design is grounded in PostgreSQL's [transaction isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html), [explicit locking documentation](https://www.postgresql.org/docs/18/explicit-locking.html), and [CREATE FUNCTION documentation](https://www.postgresql.org/docs/18/sql-createfunction.html). Use these to verify snapshot behavior, function configuration, and definer privileges during implementation. These references explain the chosen mechanics; the product rules above remain project decisions.
