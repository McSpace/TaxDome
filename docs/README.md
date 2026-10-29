# TaxDome specification package

Start with **[PRD.md](PRD.md)**. It is the final English implementation contract for a coding agent. This folder contains the specifications and source material the service was built from; the implementation, run instructions and results are described in the [repository README](../README.md). The implementation plan is in [superpowers/plans](superpowers/plans/2026-10-29-bulk-firm-payments.md).

## Active implementation documents

| File | Purpose |
| --- | --- |
| [PRD.md](PRD.md) | Product scope, API, validation, database algorithm, deployment, test expectations, acceptance criteria and implementation sequence. |
| [architecture.md](architecture.md) | Concise architecture and rationale. |
| [architecture.excalidraw](architecture.excalidraw) | Editable native component diagram. |
| [architecture.png](architecture.png) | PNG diagram for viewing and sharing. |
| [database-algorithm.md](database-algorithm.md) | Consolidated English algorithm note, derived from the final decisions. |
| [Firm_Payments_Test_Scenarios.md](Firm_Payments_Test_Scenarios.md) | Active revision 2: 151 in-scope scenarios, with stable case IDs. Expected behavior is defined by the PRD. |
| [test-scope-changes.md](test-scope-changes.md) | All 88 removed IDs and reasons; 19 new payment-key/configuration cases are listed in the active catalogue. |

The active test catalogue excludes authorization, signatures, tenancy, live mode transitions, external request/batch identity systems, administrative firm operations, alternative concurrent writers, and dedicated capacity/chaos frameworks. Standard validation, concurrency, targeted failure rollback and both static deployment modes remain in scope. The archived revision does not authorize extra features or tests.

## Gathered source material

| File | Origin / status |
| --- | --- |
| [TA Firm Payments.pdf](sources/TA%20Firm%20Payments.pdf) | Original five-page challenge attachment, copied without modification from the available project file. |
| [challenge.txt](sources/challenge.txt) | Text extracted from the original PDF for agent access. |
| [challenge-review.ru.md](challenge-review.ru.md) | Available Russian translation/review answer from the challenge discussion, retained as retrieved (including historical citation placeholders). |
| [Original scenario catalogue](sources/Firm_Payments_Test_Scenarios.original.md) | Unmodified 220-case Markdown artifact recovered from the earlier chat's available file. Historical revision only. |
| [Challenge discussion snapshot](sources/conversations/challenge-review.json) | Available history returned for “Разбор задания и перевод”. |
| [PostgreSQL discussion snapshot](sources/conversations/postgres-locking.json) | Available history returned for “Блокировки балансов Postgres”. |
| [Architecture discussion snapshot](sources/conversations/architecture-discussion.json) | Available history returned for “Проектирование архитектуры системы”. |

## Source limitations and precedence

The earlier catalogue was also delivered as `Firm_Payments_Test_Scenarios.docx`. The original Word binary is not available in the connected local file/history surface; its complete Markdown counterpart is included. No substitute Word file has been presented as that original.

Some assistant answers in the locking and architecture histories are available only as reference placeholders. User decisions are available. The consolidated database note and PRD use those decisions plus the architecture established in the current chat; they are newly authored specifications, not verbatim recovered answers.

The JSON files are unmodified tool-returned history snapshots, not certified complete exports. They do not satisfy the challenge's requirement for complete unedited AI conversation logs by themselves. Preserve genuine exports when available before final submission. Do not fill unavailable source content with invented quotations.

Precedence: explicit current user scope decisions and PRD, then architecture/algorithm notes, then active test catalogue as scenario inputs. The challenge remains the baseline; additional PRD choices are labeled. Original discussions and archived scenarios provide provenance only. This package itself was written before implementation; see the repository README for what was built.
