# Firm Payments Test Scenario Catalogue

Revision 2 - 29 October 2026 - implementation scope

151 in-scope scenarios. This is the active catalogue for implementation. [PRD.md](PRD.md) defines expected results and the product contract. This catalogue lists inputs and actions; it does not broaden the PRD. Run applicable cases separately in ON and OFF mode on fresh fixtures. Do not switch a serving database between modes.

The unmodified 220-case catalogue is preserved in [sources/Firm_Payments_Test_Scenarios.original.md](sources/Firm_Payments_Test_Scenarios.original.md). Removed case IDs and reasons are recorded in [test-scope-changes.md](test-scope-changes.md). Retained IDs remain stable; PAY and CFG cases replace speculative request-identity and live-transition cases.

There are no request keys, batch IDs, caller scopes, signatures, identity metadata tables, expiry jobs or firm-maintenance APIs. Different intended payments in concurrency tests must use different descriptions unless the case deliberately tests duplicate keys. Named labels identify test operations only. In ON mode the sole conditional identity is payer + payee + exact description.

Use PostgreSQL INTEGER with maximum M = 2147483647 cents. Limits are the concrete values in the PRD. Use real PostgreSQL connections and all three API instances for concurrency. Coordinate overlap with test-only barriers; do not use arbitrary sleeps as evidence. Failure injection is limited to targeted rollback, timeout and retry-semantics checks, with no dedicated network-chaos system. Test hooks must never be enabled in the ordinary service configuration.

Record case ID, effective mode, starting fixture, input, relevant transaction schedule, responses and final rows. Use a consistent database snapshot for invariants. Sequence gaps are not payment rows.

## Scenario index

| Prefix | Cases |
| --- | ---: |
| BAS | 16 |
| AMT | 21 |
| REQ | 17 |
| FRM | 8 |
| TXT | 8 |
| BAT | 12 |
| SEQ | 8 |
| CON | 18 |
| FLT | 12 |
| NET | 4 |
| DBS | 2 |
| OPS | 6 |
| PAY | 16 |
| CFG | 3 |

## Reference fixtures

All money in fixture tables is in integer USD cents. Amount strings in requests are in USD. Unless a case overrides it, start with the base fixture and an empty payments table. Use a short ASCII description for entries that do not specify one. Use distinct descriptions for separate intended payments so ON mode does not collapse unrelated test inputs.

### Base fixture

| Alias | Internal ID | Public UUID | Starting cents |
| --- | --- | --- | --- |
| A | 30 | aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa | 10000 |
| B | 10 | bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb | 2000 |
| C | 20 | cccccccc-cccc-4ccc-8ccc-cccccccccccc | 0 |
| D | 40 | dddddddd-dddd-4ddd-8ddd-dddddddddddd | 5000 |
| X | Absent | ffffffff-ffff-4fff-8fff-ffffffffffff | Absent |

The mismatched order of aliases, internal IDs and UUIDs is deliberate. X is a syntactically valid UUID that is absent from the database.

### Official sample fixture

| Firm | ID | Starting cents | Public UUID |
| --- | --- | --- | --- |
| Pinecrest CPA Group | 1 | 5000000 | 3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41 |
| Lopez Bookkeeping | 2 | 50000 | 8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10 |
| Nair Tax Services | 3 | 200000 | e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25 |

For BAS005, use Pinecrest as payer and the following three entries in this order.

| Recipient | Amount string | Description |
| --- | --- | --- |
| Nair Tax Services | "6250" | Overflow returns, August 2026 |
| Nair Tax Services | "5800.5" | Amended returns, August 2026 |
| Lopez Bookkeeping | "1200.75" | Bookkeeping cleanup, 3 clients |


## BAS scenarios

### BAS001 One payment to one recipient

**Setup:** Use the base fixture. A sends B USD 25.00 with a short description.

**Exercise:** Submit the request once through the public HTTP endpoint.

### BAS002 Several different recipients

**Setup:** Use the base fixture. A sends B USD 10.00, C USD 15.25 and D USD 20.50.

**Exercise:** Submit all three entries as one request.

### BAS003 Several entries for one recipient

**Setup:** Use the base fixture. A sends B USD 10.00 and B USD 15.00 with different descriptions.

**Exercise:** Submit both entries in one array.

### BAS004 Identical entries inside one request

**Setup:** Use the base fixture. Include two entries from A to B, each USD 10.00 with exactly the same description.

**Exercise:** Submit the array without adding payment identifiers.

### BAS005 Official challenge sample

**Setup:** Use the official sample fixture and the three payment entries listed in the reference section.

**Exercise:** Submit the original sample as one request.

### BAS006 Payment equal to the payer balance

**Setup:** Set A to 10000 cents. Prepare one payment of USD 100.00 to B.

**Exercise:** Submit the request once.

### BAS007 Payment one cent below the payer balance

**Setup:** Set A to 10000 cents. Prepare one payment of USD 99.99 to B.

**Exercise:** Submit the request once.

### BAS008 Payment one cent above the payer balance

**Setup:** Set A to 10000 cents. Prepare one payment of USD 100.01 to B.

**Exercise:** Submit the request once.

### BAS009 Positive payment from a zero balance

**Setup:** Set A to zero. Prepare one payment of USD 0.01 to B.

**Exercise:** Submit the request once.

### BAS010 Smallest positive cent amount

**Setup:** Use the base fixture. A sends B USD 0.01.

**Exercise:** Submit the request once using the amount string "0.01".

### BAS011 Recipient with a zero balance

**Setup:** Use the base fixture. A sends C USD 25.00.

**Exercise:** Submit the request and include C in the observation snapshot.

### BAS012 Recipient with an existing balance

**Setup:** Use the base fixture. A sends B USD 25.00.

**Exercise:** Submit the request and include B in the observation snapshot.

### BAS013 An arbitrary firm acts as payer

**Setup:** Use the base fixture. D sends C USD 10.00.

**Exercise:** Submit a request whose payer differs from the payer in the official sample.

### BAS014 Equal firm names with different UUIDs

**Setup:** Give B and C the same name while preserving their separate IDs and UUIDs.

**Exercise:** A sends each firm a separate USD 10.00 payment in one request.

### BAS015 Unrelated firms in the same database

**Setup:** Add ten firms that do not appear in the request. A sends B USD 25.00.

**Exercise:** Submit the request while capturing all firm rows before and after.

### BAS016 The introductory two payment example

**Setup:** Use the official sample balances. Prepare USD 1200.75 to Lopez and USD 300 to Nair with the introductory descriptions.

**Exercise:** Submit this example separately from the three payment sample.

## AMT scenarios

### AMT001 Whole dollar strings

**Setup:** Use separate copies of the base fixture and amounts "1", "300" and "6250"; increase A where needed.

**Exercise:** Submit one request for each amount representation.

### AMT002 One fractional digit

**Setup:** Prepare amounts "1.2", "0.1" and "5800.5"; provide sufficient fixture balances.

**Exercise:** Submit each representation separately.

### AMT003 Two fractional digits

**Setup:** Prepare amounts "1.20", "0.10", "1200.75" and "0.01".

**Exercise:** Submit each representation separately with suitable balances.

### AMT004 Decimal values sensitive to binary floating point

**Setup:** Prepare "0.29", "0.57", "1.01" and "16.15".

**Exercise:** Send each alone and then together as one batch.

### AMT005 Repeated fractional additions

**Setup:** Set A to 100 cents. Prepare ten payments of "0.10" to B.

**Exercise:** Submit the ten entries together, then repeat with "0.01" entered one hundred times.

### AMT006 Zero representations

**Setup:** Prepare "0", "0.0", "0.00" and "000.00".

**Exercise:** Submit one request per representation.

### AMT007 Negative values

**Setup:** Prepare "-1", "-0.01" and "-0.00".

**Exercise:** Submit one request per string.

### AMT008 More than two fractional digits

**Setup:** Prepare "1.001", "1.999", "0.0001" and "1.2300".

**Exercise:** Submit each string without preprocessing it on the client.

### AMT009 Exponent notation

**Setup:** Prepare "1e2", "1E+2" and "1e-2".

**Exercise:** Send each as an amount string.

### AMT010 Locale separators and currency symbols

**Setup:** Prepare "1,25", "1,000.00", "1 000.00", "$1.00" and "€1.00".

**Exercise:** Submit each string as received from a client.

### AMT011 Signs and surrounding whitespace

**Setup:** Prepare "+1.00", " 1.00", "1.00 ", "\t1.00" and "1.00\n".

**Exercise:** Submit each without trimming or normalizing it in the test client.

### AMT012 Incomplete decimal forms

**Setup:** Prepare ".50", "1.", ".", an empty string and a string containing only spaces.

**Exercise:** Submit each as the amount field.

### AMT013 Leading zeros

**Setup:** Prepare "0001", "0001.20", "00.01" and "000".

**Exercise:** Submit each representation separately.

### AMT014 Unicode numeric characters

**Setup:** Prepare Arabic Indic digits, fullwidth digits and a Unicode minus sign in otherwise similar amount strings.

**Exercise:** Submit each with the original Unicode code points.

### AMT015 Nonfinite and nonnumeric strings

**Setup:** Prepare "NaN", "Infinity", "-Infinity", "null" and "one".

**Exercise:** Submit each as a JSON string.

### AMT016 Amount values with other JSON types

**Setup:** Supply amount as 1, 1.25, true, null, an array and an object.

**Exercise:** Submit one request for each JSON type.

### AMT017 Largest stored integer amount

**Setup:** Let M be the selected database maximum for amount_cents. Set A to M and recipients to zero.

**Exercise:** Submit a string representing exactly M cents.

### AMT018 One cent beyond the stored amount range

**Setup:** Use the same storage configuration as AMT017.

**Exercise:** Submit a string representing M plus one cents, including a variant with many more digits.

### AMT019 Batch total beyond the balance storage range

**Setup:** Set A to M and B and C to zero. Prepare two individually representable amounts whose combined cents equal M plus one.

**Exercise:** Submit both payments in one request.

### AMT020 Recipient balance at the storage boundary

**Setup:** Set B to M minus one and provide A with enough funds.

**Exercise:** Send B one cent, then use a fresh fixture to send B two cents.

### AMT021 Repeated recipient aggregate near the boundary

**Setup:** Set B to M minus two. Prepare three separate one cent entries to B.

**Exercise:** Submit all three entries together.

## REQ scenarios

### REQ001 An empty HTTP body

**Setup:** Use an otherwise normal request URL and headers.

**Exercise:** Send a request with zero body bytes, then one containing only whitespace.

### REQ002 Malformed JSON

**Setup:** Prepare truncated objects, a trailing comma, an unquoted key and an unterminated string.

**Exercise:** Send each body directly as bytes.

### REQ003 Comments inside JSON

**Setup:** Put line comments and block comments into copies of a payment request.

**Exercise:** Send the bodies without a client library removing the comments.

### REQ004 Other top level JSON values

**Setup:** Prepare null, an array, a string, a number and a boolean as the top level value.

**Exercise:** Submit each value as the entire body.

### REQ005 Missing payer field

**Setup:** Prepare a request containing payments but no payer_firm_uuid.

**Exercise:** Submit it with the base fixture available.

### REQ006 Missing payments field

**Setup:** Prepare a request containing only payer_firm_uuid.

**Exercise:** Submit it once.

### REQ007 Payments field with other types

**Setup:** Set payments to null, an object, a string, a number and a boolean.

**Exercise:** Submit one request per variant.

### REQ008 An empty payments array

**Setup:** Use a known payer and payments set to an empty array.

**Exercise:** Submit the request in both modes.

### REQ009 Nonobject array entries

**Setup:** Insert null, strings, arrays, numbers and booleans into the payments array.

**Exercise:** Test each alone and between ordinary payment objects.

### REQ010 Missing fields inside one payment

**Setup:** Remove amount, payee_firm_uuid or description from one otherwise complete entry.

**Exercise:** Submit one request per omitted field.

### REQ011 UUID fields with other JSON types

**Setup:** Supply payer_firm_uuid and payee_firm_uuid as null, numbers, booleans, arrays and objects.

**Exercise:** Vary one field at a time.

### REQ012 Unknown top level attributes

**Setup:** Add fields such as request_note, internal_id and mode to a normal request.

**Exercise:** Submit each variant and one body containing several extra attributes.

### REQ013 Unknown payment attributes

**Setup:** Add currency, amount_cents, payer_firm_id and an arbitrary field to payment objects.

**Exercise:** Submit each variant without changing the documented fields.

### REQ014 Duplicate JSON member names

**Setup:** Repeat payer_firm_uuid, payments, amount and payee_firm_uuid with conflicting values inside raw JSON objects.

**Exercise:** Send the raw bodies through the actual server parser.

### REQ015 Content type variations

**Setup:** Prepare identical JSON bytes with application/json, no Content-Type, text/plain and an unsupported media type.

**Exercise:** Submit each header variant.

### REQ016 Character encoding variations

**Setup:** Prepare UTF-8, a UTF-8 byte order mark, invalid UTF-8 and a declared charset inconsistent with the bytes.

**Exercise:** Submit the bodies without automatic re-encoding by the client.

### REQ018 Field order and insignificant whitespace

**Setup:** Prepare semantically identical JSON objects with reordered fields, indentation, line breaks and compact encoding.

**Exercise:** Submit each form with the same logical payment data.

## FRM scenarios

### FRM001 Unknown payer UUID

**Setup:** Use X as payer and B as recipient.

**Exercise:** Submit a USD 10.00 payment.

### FRM002 Unknown recipient UUID

**Setup:** Use A as payer and X as the sole recipient.

**Exercise:** Submit USD 10.00 without creating or modifying firms.

### FRM003 Unknown recipient mixed with known recipients

**Setup:** Put B, X and C in a three entry batch.

**Exercise:** Repeat with X in the first, middle and last position.

### FRM004 Malformed UUID strings

**Setup:** Prepare truncated UUIDs, strings containing nonhexadecimal characters and arbitrary text.

**Exercise:** Test payer and recipient fields independently.

### FRM005 UUID letter case

**Setup:** Use upper, lower and mixed case representations of a known UUID.

**Exercise:** Submit each representation for payer and recipient fields.

### FRM006 Whitespace around UUIDs

**Setup:** Add spaces, tabs and line breaks around a known UUID string.

**Exercise:** Submit each variant without trimming in the client.

### FRM007 Internal IDs supplied as public identifiers

**Setup:** Supply the string form of a firm's integer ID in a UUID field.

**Exercise:** Repeat for payer and recipient fields.

### FRM008 UUID order differs from internal ID order

**Setup:** Use the base fixture, whose internal IDs deliberately differ from UUID order.

**Exercise:** Submit batches listing B, C and D in several orders.

## TXT scenarios

### TXT001 Ordinary short text

**Setup:** Use descriptions such as "Referral fee" and "Bookkeeping cleanup, 3 clients".

**Exercise:** Submit one request for each description.

### TXT002 Empty and whitespace descriptions

**Setup:** Supply an empty string, spaces, tabs and line breaks as separate descriptions.

**Exercise:** Submit each representation without client normalization.

### TXT003 Null and nonstring descriptions

**Setup:** Set description to null, a number, a boolean, an array and an object.

**Exercise:** Submit one request per value.

### TXT004 International text and emoji

**Setup:** Prepare Cyrillic, Dutch accented text, Arabic, Chinese and emoji descriptions.

**Exercise:** Submit them individually and in one mixed batch.

### TXT005 Unicode normalization forms

**Setup:** Prepare visually identical accented text in composed and decomposed Unicode forms.

**Exercise:** Submit both as separate calls and together in one batch, without identity inputs.

### TXT006 Escaped characters and control characters

**Setup:** Prepare quotes, backslashes, escaped newlines, tabs and a JSON escaped null character.

**Exercise:** Send each through the public endpoint using valid JSON encoding.

### TXT007 Markup and SQL shaped text

**Setup:** Use descriptions containing HTML tags, script shaped text, quotes, SQL keywords and SQL comment markers.

**Exercise:** Send them as ordinary string values.

### TXT008 Repeated description across different payments

**Setup:** Use the same description for different amounts, different recipients and several identical value entries.

**Exercise:** Submit each batch without introducing optional payment IDs.

## BAT scenarios

### BAT001 Each amount fits but the combined amount is larger

**Setup:** Set A to USD 100.00. Prepare USD 60.00 to B and USD 60.00 to C.

**Exercise:** Submit both entries as one batch.

### BAT002 Several entries together equal the balance

**Setup:** Set A to USD 100.00. Prepare amounts 10.00, 20.00 and 70.00 to different recipients.

**Exercise:** Submit them in several array orders.

### BAT003 One malformed amount among ordinary entries

**Setup:** Prepare two ordinary payments and one amount string "1.001".

**Exercise:** Move the malformed entry between the first, middle and last positions.

### BAT004 One missing description among ordinary entries

**Setup:** Prepare a three entry batch with description omitted from one entry.

**Exercise:** Submit variants placing that entry at different positions.

### BAT005 A single self payment

**Setup:** Set A to USD 100.00. Make A both payer and recipient for USD 25.00.

**Exercise:** Submit this as a one entry request.

### BAT006 Self payment equal to the balance

**Setup:** Set A to USD 100.00 and send A USD 100.00.

**Exercise:** Submit the request once.

### BAT007 Self payment greater than the balance

**Setup:** Set A to USD 100.00 and send A USD 100.01.

**Exercise:** Submit the request once.

### BAT008 Self payment combined with an external payment

**Setup:** Set A to USD 100.00. Include USD 100.00 to A and USD 100.00 to B.

**Exercise:** Submit both together, then reverse their array positions.

### BAT009 Several self payments plus other recipients

**Setup:** Set A to USD 100.00. Include USD 20.00 to A twice and USD 60.00 to B.

**Exercise:** Submit the array as given and with entries reordered.

### BAT010 One cent change to a batch total

**Setup:** Start with a batch whose total equals A's balance.

**Exercise:** Increase one entry by one cent in one fixture and decrease it by one cent in another.

### BAT011 Repeated recipient with mixed amount formats

**Setup:** Send B "1", "1.0" and "1.00" as three separate entries with distinct descriptions.

**Exercise:** Submit the three entries together.

### BAT012 Several independent input problems in one request

**Setup:** Combine an unknown recipient, an invalid amount and a missing field, with an ordinary payment included.

**Exercise:** Submit permutations of entry order and field placement.

## SEQ scenarios

### SEQ001 Two different batches from one payer

**Setup:** Set A to USD 100.00. Prepare USD 30.00 to B followed by USD 40.00 to C.

**Exercise:** Submit the requests sequentially, waiting for each response.

### SEQ002 Repeated payload without a key

**Setup:** Prepare a USD 25.00 A to B request without any idempotency header or field.

**Exercise:** Submit the exact request twice in sequence.

### SEQ004 Payer receives funds between calls

**Setup:** Set A to zero and D to USD 100.00.

**Exercise:** Submit A to B for USD 25.00, submit D to A for USD 50.00, then resend the A to B request. No request identity is supplied.

### SEQ005 Payer spends funds between similar calls

**Setup:** Set A to USD 100.00.

**Exercise:** Submit A to B for USD 80.00 and then A to C for USD 80.00 with a different description.

### SEQ006 Receiver later becomes payer

**Setup:** Start with C at zero.

**Exercise:** Submit A to C for USD 30.00, then C to B for USD 20.00 after the first response.

### SEQ007 Transfers in both directions

**Setup:** Use the base fixture.

**Exercise:** Submit A to B for USD 25.00, then B to A for USD 10.00 with distinct descriptions.

### SEQ008 Same logical amount with changed text formatting

**Setup:** Prepare otherwise identical bodies containing "25", "25.0" and "25.00".

**Exercise:** Submit sequentially using no key, then repeat concurrently with no identity input.

### SEQ010 A sequence of many debits from one balance

**Setup:** Set A to USD 100.00 and prepare twenty separate USD 10.00 requests.

**Exercise:** Send them sequentially with distinct descriptions and capture every response.

## CON scenarios

### CON001 Two competing large debits

**Setup:** Set A to USD 100.00. Prepare A to B for USD 80.00 and A to C for USD 80.00.

**Exercise:** Start both requests together using separate processes and database connections.

### CON002 Two debits together equal the balance

**Setup:** Set A to USD 100.00. Prepare A to B for USD 60.00 and A to C for USD 40.00.

**Exercise:** Start both together and repeat with their release order reversed.

### CON003 Many competing debits

**Setup:** Set A to USD 100.00. Prepare twenty USD 10.00 requests to B and C.

**Exercise:** Release them from a shared barrier with distinct descriptions.

### CON004 Many one cent requests

**Setup:** Set A to 100 cents and prepare two hundred separate one cent requests.

**Exercise:** Start them across several application processes.

### CON005 Different payers share one recipient

**Setup:** Set A and D to USD 100.00 and C to zero.

**Exercise:** Start A to C for USD 30.00 and D to C for USD 40.00 together.

### CON006 Opposite direction payments

**Setup:** Set A to USD 100.00 and B to USD 100.00.

**Exercise:** Start A to B for USD 40.00 and B to A for USD 30.00 together.

### CON007 Three firms in a payment cycle

**Setup:** Set A, B and C to USD 100.00 each.

**Exercise:** Start A to B, B to C and C to A, each for USD 30.00, together.

### CON008 Overlapping recipients in reverse array order

**Setup:** Set A and D to USD 100.00. One request lists B then C; the other lists C then B.

**Exercise:** Start both batches together, each containing two USD 10.00 entries.

### CON009 A firm pays while receiving

**Setup:** Use the base fixture and prepare A to B for USD 70.00 and D to A for USD 30.00.

**Exercise:** Run both requests together through different server processes.

### CON010 Incoming money and an initially unfunded debit

**Setup:** Set A to zero and D to USD 100.00. Prepare D to A for USD 100.00 and A to B for USD 80.00.

**Exercise:** Force incoming first, outgoing first and overlapping transaction schedules.

### CON011 Incoming transfer fails while another request uses the payer

**Setup:** Set A to zero and D to USD 100.00. Pause D to A for USD 100.00 before completion and inject a transaction failure.

**Exercise:** Start A to B for USD 80.00 during the pause.

### CON016 One shared firm is held by another transaction

**Setup:** Open a separate transaction that holds a conflicting lock on B.

**Exercise:** Start an A to B request, observe the wait, then separately release and roll back the blocker.

### CON017 An unrelated firm is held by another transaction

**Setup:** Open a transaction that holds a conflicting row lock on D.

**Exercise:** Start A to B while the blocker remains open.

### CON018 Opposite UUID and internal ID order

**Setup:** Use base IDs A 30, B 10, C 20 and D 40.

**Exercise:** Submit overlapping multi firm batches with UUID order, ID order and reversed input order arranged differently.

### CON019 Balance changes after an early application read

**Setup:** Pause a USD 80.00 request after any preliminary balance lookup. Let a distinct USD 50.00 request finish first.

**Exercise:** Resume the paused request using its original input.

### CON020 Mixed workload across several instances

**Setup:** Prepare same payer, shared recipient and disjoint firm requests with distinct descriptions.

**Exercise:** Send the mix through at least two server processes sharing one database.

### CON021 Large and small batches overlap

**Setup:** Prepare a large batch from A involving B and C, and a one entry batch from D involving B.

**Exercise:** Start both together and vary which transaction reaches shared rows first.

### CON022 An observer reads during an unfinished transfer

**Setup:** Pause a multi recipient request at several transaction stages.

**Exercise:** Use a separate database connection to read firms and payments during each pause and after completion.

## FLT scenarios

### FLT001 Failure after validation and before transaction work

**Setup:** Prepare an ordinary multi recipient request.

**Exercise:** Inject an application exception immediately after input validation and before the first database mutation.

### FLT002 Failure after firms are locked

**Setup:** Prepare a request involving A, B and C.

**Exercise:** If row locks are used, inject an exception after all selected locks are acquired and before balance changes.

### FLT003 Failure after the payer balance statement

**Setup:** Prepare a request with two recipients.

**Exercise:** Inject a fault immediately after the statement that modifies the payer balance.

### FLT004 Failure after one recipient balance statement

**Setup:** Prepare a request paying B and C.

**Exercise:** Inject a fault after the first recipient balance mutation and before the remaining transaction work.

### FLT005 Failure between balance work and payment inserts

**Setup:** Prepare a multi recipient request.

**Exercise:** At the implementation's boundary between balance changes and payment inserts, inject an exception; adapt the hook if inserts occur first.

### FLT006 Failure after the first payment insert

**Setup:** Prepare three separate payment entries.

**Exercise:** Inject an exception immediately after one payment row has been inserted.

### FLT007 One row in a multirow insert triggers a database error

**Setup:** Prepare a batch whose later row encounters a controlled database constraint or trigger failure.

**Exercise:** Execute it through the ordinary persistence path.

### FLT008 Failure after all statements and before commit

**Setup:** Prepare an ordinary batch.

**Exercise:** Inject an application exception after all intended statements have run but before commit is sent.

### FLT010 Connection loss before commit is sent

**Setup:** Pause a request after its transaction statements.

**Exercise:** Break the application database connection before a COMMIT command is transmitted.

### FLT013 Lock wait timeout

**Setup:** Hold a required firm row in another transaction and configure a short lock wait limit.

**Exercise:** Submit a request that reaches the blocked operation.

### FLT014 Statement timeout

**Setup:** Arrange a controlled slow database statement inside a payment transaction.

**Exercise:** Run the request with a configured statement timeout.

### FLT017 A later request reuses the same pooled connection

**Setup:** Cause a controlled transaction failure on a pooled connection.

**Exercise:** Return it through the application's normal cleanup path and send a new ordinary request that can reuse it.

## NET scenarios

### NET004 Retry while an earlier attempt is still running

**Setup:** Hold the first request at a test-only synchronization point.

**Exercise:** Send an identical second request to another API instance, then release the first. Use no request key.

### NET005 Committed request is retried without receiving its response

**Setup:** Commit a request and deliberately discard its response in the test client.

**Exercise:** Resend the identical body. This tests business retry semantics without a transport chaos proxy.

### NET008 Retry reaches another instance

**Setup:** Submit a request directly to api-1 and discard the received response.

**Exercise:** Submit the same body to api-2. Keep the database shared; supply no request identity.

### NET010 A delayed duplicate arrives after unrelated payments

**Setup:** Deliver a request, then issue several distinct transfers involving the same firms.

**Exercise:** Deliver an old copy of the original request afterward.

## DBS scenarios

### DBS007 Database arithmetic at numeric limits

**Setup:** Prepare values for which intermediate SQL sums, casts or update expressions approach the selected integer limits.

**Exercise:** Run through the real application query path, including repeated recipients.

### DBS010 Schema and seed initialization

**Setup:** Start with an empty database and then a database already containing the official fixture.

**Exercise:** Run the documented initialization process, restart the service and submit a sample request after each setup.

## OPS scenarios

### OPS001 Payment count around a configured limit

**Setup:** Using L = 1000, prepare batches with L minus one, L and L plus one entries.

**Exercise:** Submit them in both modes with small amounts and sufficient fixture balances where representable.

### OPS002 Request byte size around a configured limit

**Setup:** Prepare bodies just below, at and above the selected request byte limit.

**Exercise:** Vary description sizes while keeping the number of payments fixed.

### OPS003 Description length around a configured limit

**Setup:** Using the 1024-character description limit, prepare lengths just below, at and above it.

**Exercise:** Repeat using ASCII, multibyte Unicode and emoji to separate byte and character counts.

### OPS004 Extremely long amount strings

**Setup:** Prepare amount strings containing thousands and then many more digits, including a very long string of leading zeros.

**Exercise:** Submit them through the actual HTTP parser and numeric conversion path.

### OPS010 Database unavailable during a request

**Setup:** Make the database unavailable before connection acquisition and, separately, during an active request.

**Exercise:** Restore access and submit new requests plus repeats of interrupted requests.

### OPS011 Invalid or ambiguous mode configuration

**Setup:** Prepare missing, malformed and conflicting idempotency configuration values using supported startup and deployment inputs.

**Exercise:** Start a separate fresh deployment with each configuration; do not reload or change a running payment service.

## PAY scenarios

### PAY001 Equal history key and equal amount

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit A to B for 25.00 with description d; submit it again.

### PAY002 Equal history key and changed amount

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit A to B for 25.00 with description d; send 25.01 with the same payer, payee and description.

### PAY003 New payments mixed with equal repeats

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit A to B with description d; submit that entry together with a new A to C entry.

### PAY004 A conflict mixed with new payments

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit A to B with description d; submit a changed amount for d alongside a new A to C entry; vary array order.

### PAY005 Equal keys repeated inside one batch

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Submit two and three equal entries for the same payer, payee, description and amount.

### PAY006 Unequal amounts for one key inside one batch

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Submit the same key twice with amounts 25.00 and 25.01; vary order.

### PAY007 Concurrent identical payments

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Release identical requests through different API instances against one fresh database.

### PAY008 Concurrent unequal amounts for one key

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Release two same-key requests with different amounts from separate API instances; provide enough funds for either.

### PAY009 A changed description creates a different key

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Send identical payer, payee and amount with descriptions d, D, d-space and Unicode variants; preserve exact strings.

### PAY010 Different payees and payers have separate keys

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Reuse a description across A to B, A to C and D to B; ensure each payer can fund its request.

### PAY011 Equivalent amount spellings

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Use one key with 25, 25.0 and 25.00 in separate calls and in one batch.

### PAY012 All repeats after the balance is spent

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit A to B with description d; spend the remaining funds with another description; resubmit only the original entry.

### PAY013 Mixed batch funds cover only new payments

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Commit a historical payment; arrange a remaining balance sufficient for new entries but insufficient for the entire resubmitted array; submit the mixture.

### PAY014 Self-payment repeats and conflicts

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Submit a self-payment, an equal repeat and a changed-amount same-key request from fresh fixtures for each sequence.

### PAY015 Concurrent overlapping mixed batches

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Release two batches sharing a same-key entry and each containing a different new entry; repeat with a shared entry amount conflict.

### PAY016 No mode override in a request

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Send mode as an unknown JSON field; separately set caller/session custom settings while invoking the configured function in the restricted test role.

## CFG scenarios

### CFG001 Default and explicit modes on fresh deployments

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Start default, explicit ON and explicit OFF stacks separately using fresh databases; run the preflight and mode-specific suite.

### CFG002 Runner expected mode mismatch

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Start an ON stack and an OFF-expected runner, then the reverse, without switching a running stack.

### CFG003 Every instance reports the effective mode

**Setup:** Use a fresh fixture in each mode unless this sequence explicitly commits earlier payments.

**Exercise:** Read diagnostics directly from api-1, api-2 and api-3, through Nginx, and from database function metadata; test missing or invalid configuration in an isolated startup fixture.

