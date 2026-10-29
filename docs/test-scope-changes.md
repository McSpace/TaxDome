# Test scope decisions

Revision 2 applies the explicit scope decision made on 29 October 2026. Excluded scenarios are historical material only and MUST NOT become implementation tasks. PAY001-PAY016 and CFG001-CFG003 cover the agreed payment-level conditional idempotency and static mode verification. Retained concurrency cases use descriptions to distinguish independent payments; no identity inputs are added.

| Removed ID | Original title | Reason |
| --- | --- | --- |
| AMT022 | Values around language and driver precision limits | Alternate BIGINT schema is out of scope. |
| REQ017 | Deeply nested unexpected values | Parser stress and nesting stress are outside the bounded request contract. |
| FRM009 | Duplicate UUID rows in a legacy fixture | Legacy corrupt-schema fixtures are outside the seeded database contract. |
| FRM010 | Missing or null UUID in stored data | Legacy corrupt-schema fixtures are outside the seeded database contract. |
| FRM011 | Firm rename between requests | Firm maintenance APIs are out of scope. |
| FRM012 | Firm removal and recreation | Firm deletion/recreation is out of scope. |
| SEQ003 | Repeated payload with independent identities | Request identity inputs do not exist. |
| SEQ009 | External balance adjustment between calls | Administrative balance mutation is out of scope. |
| CON012 | Payment races with an administrative adjustment | Concurrent administrative writes are prohibited during service traffic. |
| CON013 | Payer deletion during request processing | Concurrent firm deletion is out of scope. |
| CON014 | Recipient deletion during request processing | Concurrent firm deletion is out of scope. |
| CON015 | UUID remapping during request processing | Concurrent UUID maintenance is out of scope. |
| FLT009 | Commit rejected by the database | Deferred commit-fault infrastructure is not required for this submission. |
| FLT011 | Request cancellation during database work | Framework cancellation fault harness is beyond the required test scope. |
| FLT012 | Application process exits during a transaction | Worker termination/restart fault infrastructure is not required. |
| FLT015 | Database selects the request as a deadlock victim | Deliberately introducing a nonconforming writer to force deadlock is not required. |
| FLT016 | Serialization conflict | Serializable isolation is not the selected strategy. |
| FLT018 | Repeated transient faults during internal retries | Automatic internal retries are not part of the selected design. |
| NET001 | Connection fails before the server receives the body | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET002 | Body transmission stops partway through | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET003 | Proxy sends a duplicate | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET006 | Response body is truncated | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET007 | Database commit acknowledgment is lost | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET009 | Several retries with backoff | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET011 | Attempts arrive in a different order from transmission | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| NET012 | Client disconnects at several processing stages | A dedicated transport/proxy chaos harness is outside this submission; core retry semantics remain covered. |
| IDM001 | No idempotency identity supplied | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM002 | Same key and same bytes in sequence | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM003 | Same key and same bytes concurrently | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM004 | Same payload with different keys | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM005 | Same key with a changed amount | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM006 | Same key with a changed recipient | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM007 | Same key with a changed payer | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM008 | Same key with a changed description | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM009 | Same key with an entry added or removed | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM010 | Same key with the payment array reordered | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM011 | Same key with equivalent amount strings | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM012 | Same key with equivalent JSON encoding | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM013 | Same key with changed entry multiplicity | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM014 | Boundary forms of the key input | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM015 | Same key under different callers or scopes | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM016 | Worker stops after identity acquisition | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM017 | Failure at the identity and payment persistence boundary | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM018 | Old request repeated with a different current balance | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM019 | Old request repeated after firm data changes | Replaced by payment-key cases PAY; no request identity store or API. |
| IDM020 | Identity expiration and cleanup race | Replaced by payment-key cases PAY; no request identity store or API. |
| REU001 | Two batches share one payment | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU002 | A later batch is a strict subset | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU003 | A later batch is a strict superset | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU004 | The same payment set has a new batch identity | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU005 | The same payment identity carries a changed amount | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU006 | The same payment identity carries other changed fields | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU007 | One payment identity occurs twice within one batch | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU008 | Shared payments in concurrently created batches | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU009 | The same payment label is used by different payers | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU010 | Equal values represent separate obligations | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU011 | Different payments share one recipient | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| REU012 | A reused payment belongs to an unfinished earlier batch | Replaced by payment-key cases PAY; no batch/payment identity inputs. |
| MOD001 | Disabled mode followed by enabled mode | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD002 | Enabled mode followed by disabled mode | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD003 | Mode changes while a request waits | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD004 | Instances temporarily use different modes | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD005 | Enabled mode after a service restart | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD006 | Disabled mode after a service restart | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD007 | Application rollback with existing identity metadata | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| MOD008 | Different modes for different scopes | Live mode transitions, mixed-mode operation and scope-specific modes are out of scope. |
| DBS001 | Direct writes with missing monetary data | Direct table writes are not a supported runtime path. |
| DBS002 | Direct writes with nonpositive amounts or negative balances | Direct table writes are not a supported runtime path. |
| DBS003 | Direct writes with nonexistent firm references | Direct table writes are not a supported runtime path. |
| DBS004 | Concurrent creation of the same public UUID | Concurrent firm creation is out of scope. |
| DBS005 | Generated IDs near exhaustion | ID exhaustion lifecycle is outside this challenge submission. |
| DBS006 | Preexisting inconsistent monetary data | Repairing a corrupt legacy ledger is out of scope. |
| DBS008 | Firm deletion with existing payment references | Firm deletion is out of scope. |
| DBS009 | Another writer changes balances | Concurrent alternative writers are out of scope. |
| OPS005 | Very large arrays with one recipient | Large-scale capacity stress is not required. |
| OPS006 | Large result and identity response records | Request-identity records do not exist. |
| OPS007 | Sustained traffic for one payer | Sustained-load benchmarking is not required. |
| OPS008 | Independent large batches in parallel | Large-scale capacity benchmarking is not required. |
| OPS009 | Database connection pool exhaustion | Pool saturation/load infrastructure is not required. |
| OPS012 | Operational records under concurrency and retries | A separate concurrency telemetry test system is not required. |
| SEC001 | Missing or invalid credentials | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC002 | Caller references another payer | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC003 | Recipient crosses an access boundary | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC004 | Another caller repeats a known identity | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC005 | Injection shaped identifier and text input | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC006 | Client supplies internal balance or ownership fields | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC007 | Signed request data is modified | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |
| SEC008 | Diagnostic exposure during failures | Authorization, caller scopes, signatures and a security-test subsystem are out of scope; ordinary input safety remains covered by TXT/REQ. |

Original: 220 cases. Removed: 88. Retained: 132. Added: 19. Active: 151.
