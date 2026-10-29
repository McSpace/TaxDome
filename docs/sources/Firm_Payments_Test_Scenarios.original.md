# Firm Payments Test Scenario Catalogue

Inputs and execution sequences for test design and architecture review

29 October 2026 · Scenario catalogue · Revision 1

This catalogue contains 220 scenarios for the TaxDome bulk payment service. It covers everyday use, input variations, concurrent transactions, interrupted requests and optional extensions. Use the stable case IDs when developing automated tests and reviewing the proposed architecture.

This revision defines test inputs and actions only. Expected HTTP responses, resulting balances, payment counts and pass or fail criteria will be specified separately for idempotency disabled and idempotency enabled. The scenarios do not establish business rules or select an implementation.

## Using the catalogue

Instantiate each applicable case as OFF and ON using the same starting fixture. For example, BAS001 OFF and BAS001 ON are two executions of one scenario definition. Reset the database between those executions. Preserve state only within a case that explicitly describes a sequence. For a mode transition case, run the transition written in that case rather than forcing a single fixed mode.

The challenge request has no request key, batch ID or payment ID. K1 and K2 are placeholders for a future request identity input. Q1 and Q2 name conceptual batches. p1, p2 and p3 label conceptual business payments; they do not imply that equal amount, recipient and description values identify the same payment. Adapt conditional cases only after the identity mechanism, scope and retention policy have been chosen. Keep them in the design backlog in the meantime. If disabled mode does not expose identity inputs, retain the underlying duplicate delivery scenario and record which identity inputs were actually sent.

M means the selected maximum stored cent value. For PostgreSQL INTEGER, M is 2147483647; for BIGINT, substitute the selected range. Numeric boundary cases describe inputs, not a schema change. L and other limits refer to configured limits if present. Authentication, tenant scope, archival, signatures, runtime mode switching and cleanup jobs are conditional extensions rather than challenge requirements.

For concurrency and fault scenarios, use the chosen relational database and separate connections. Use separate application processes when the case mentions multiple instances. Coordinate starts and pauses with barriers or controlled hooks, and record the actual overlap. Map failure hooks to the real order of statements; the catalogue does not prescribe whether inserts or balance changes happen first. For observations spanning firms and payments, collect a consistent database snapshot or wait until all participating transactions have ended. Keep database sequence values separate from payment row counts.

When a case is executed, record its ID, effective mode on each instance, starting fixture, exact request bytes and headers, instance routing, transaction schedule, injected fault, actual HTTP responses, and actual firm and payment rows. Where identity storage exists, include its actual records. Keep actual observations separate from the future expected result specification. This catalogue contains no execution results.

## Scenario index

| Cases | Area | Count |
| --- | --- | --- |
| BAS001 to BAS016 | Everyday payment flows | 16 |
| AMT001 to AMT022 | Amount representation and numeric boundaries | 22 |
| REQ001 to REQ018 | Request structure and transport format | 18 |
| FRM001 to FRM012 | Firm identifiers and lookup | 12 |
| TXT001 to TXT008 | Payment descriptions | 8 |
| BAT001 to BAT012 | Batch composition and self payments | 12 |
| SEQ001 to SEQ010 | Sequential calls and changing balances | 10 |
| CON001 to CON022 | Concurrent requests and coordination | 22 |
| FLT001 to FLT018 | Failures inside transaction processing | 18 |
| NET001 to NET012 | Network retries and ambiguous delivery | 12 |
| IDM001 to IDM020 | Request identity and idempotency controls | 20 |
| REU001 to REU012 | Payments reused across different batches | 12 |
| MOD001 to MOD008 | Idempotency mode changes and deployment | 8 |
| DBS001 to DBS010 | Database schema and alternative write paths | 10 |
| OPS001 to OPS012 | Capacity and operational conditions | 12 |
| SEC001 to SEC008 | Authorization and trust boundaries | 8 |

## Reference fixtures

All money in fixture tables is in integer USD cents. Amount strings in requests are in USD. Unless a case overrides it, start with the base fixture and an empty payments table. Use a short ASCII description for entries that do not specify one. Give logically distinct requests independent identities where the selected mechanism supports them.

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

## Everyday payment flows

Scope: Core request and balance scenarios.

Observation areas: Request mapping, balance arithmetic, individual payment records and changes to unrelated firms.

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

## Amount representation and numeric boundaries

Scope: Core inputs and storage boundaries.

Observation areas: Raw input strings, parsed cent values, aggregate arithmetic and database numeric types.

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

### AMT022 Values around language and driver precision limits

**Setup:** If the selected schema supports these values, prepare cent amounts around 2 to the power of 53 and around the chosen signed integer maximum.

**Exercise:** Send amounts through the full JSON parser, application, driver and database path.

## Request structure and transport format

Scope: Core request parsing and validation inputs.

Observation areas: Request decoding, field presence and types, parser behavior and validation timing.

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

### REQ017 Deeply nested unexpected values

**Setup:** Replace a description or an unknown field with objects nested to several depths.

**Exercise:** Increase nesting up to and beyond any configured parser limit.

### REQ018 Field order and insignificant whitespace

**Setup:** Prepare semantically identical JSON objects with reordered fields, indentation, line breaks and compact encoding.

**Exercise:** Submit each form with the same logical payment data.

## Firm identifiers and lookup

Scope: Core identifier mapping and database lookup scenarios.

Observation areas: Public UUID lookup, internal IDs, ambiguous data and changes to firm records.

### FRM001 Unknown payer UUID

**Setup:** Use X as payer and B as recipient.

**Exercise:** Submit a USD 10.00 payment.

### FRM002 Unknown recipient UUID

**Setup:** Use A as payer and X as the sole recipient.

**Exercise:** Submit USD 10.00, then create X and resend the same body. In separate fixtures, retain the original request identity and use an independent identity where supported.

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

### FRM009 Duplicate UUID rows in a legacy fixture

**Setup:** If the schema permits a legacy fixture without UUID uniqueness, create two rows with the same UUID.

**Exercise:** Send requests referring to that UUID as payer and recipient.

### FRM010 Missing or null UUID in stored data

**Setup:** If legacy data permits it, seed a firm with a null or empty stored UUID.

**Exercise:** Submit a normal request alongside a request attempting to reference that firm.

### FRM011 Firm rename between requests

**Setup:** Send a request using B's UUID, rename B and submit a new request using the same UUID.

**Exercise:** Keep all payment input fields except the independent request identity unchanged.

### FRM012 Firm removal and recreation

**Setup:** Arrange a previously used recipient UUID, remove its row using the supported maintenance path, then recreate a firm as permitted by the schema.

**Exercise:** Submit a later request using the old public UUID.

## Payment descriptions

Scope: Core text inputs and optional text policy boundaries.

Observation areas: Text presence, Unicode handling, exact stored content and parameter binding.

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

**Exercise:** Submit both using independent requests and, where applicable, the same idempotency identity.

### TXT006 Escaped characters and control characters

**Setup:** Prepare quotes, backslashes, escaped newlines, tabs and a JSON escaped null character.

**Exercise:** Send each through the public endpoint using valid JSON encoding.

### TXT007 Markup and SQL shaped text

**Setup:** Use descriptions containing HTML tags, script shaped text, quotes, SQL keywords and SQL comment markers.

**Exercise:** Send them as ordinary string values.

### TXT008 Repeated description across different payments

**Setup:** Use the same description for different amounts, different recipients and several identical value entries.

**Exercise:** Submit each batch without introducing optional payment IDs.

## Batch composition and self payments

Scope: Core composition scenarios and unresolved business policy inputs.

Observation areas: Payment multiplicity, gross batch amounts, self references and ordering of validation.

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

## Sequential calls and changing balances

Scope: Core sequences with distinct request identities unless stated otherwise.

Observation areas: State carried between calls, repeated business input and use of current database data.

### SEQ001 Two different batches from one payer

**Setup:** Set A to USD 100.00. Prepare USD 30.00 to B followed by USD 40.00 to C.

**Exercise:** Submit the requests sequentially, waiting for each response.

### SEQ002 Repeated payload without a key

**Setup:** Prepare a USD 25.00 A to B request without any idempotency header or field.

**Exercise:** Submit the exact request twice in sequence.

### SEQ003 Repeated payload with independent identities

**Setup:** Prepare identical USD 25.00 A to B bodies and use K1 and K2 where keys are supported.

**Exercise:** Submit K1, wait for its response, then submit K2.

### SEQ004 Payer receives funds between calls

**Setup:** Set A to zero and D to USD 100.00.

**Exercise:** Submit A to B for USD 25.00, submit D to A for USD 50.00, then resend the A to B request. Exercise independent identities and the original identity in separate fixtures.

### SEQ005 Payer spends funds between similar calls

**Setup:** Set A to USD 100.00.

**Exercise:** Submit A to B for USD 80.00 and then A to C for USD 80.00 with a distinct request identity.

### SEQ006 Receiver later becomes payer

**Setup:** Start with C at zero.

**Exercise:** Submit A to C for USD 30.00, then C to B for USD 20.00 after the first response.

### SEQ007 Transfers in both directions

**Setup:** Use the base fixture.

**Exercise:** Submit A to B for USD 25.00, then B to A for USD 10.00 with separate identities.

### SEQ008 Same logical amount with changed text formatting

**Setup:** Prepare otherwise identical bodies containing "25", "25.0" and "25.00".

**Exercise:** Submit sequentially using no key, then using independent keys where supported.

### SEQ009 External balance adjustment between calls

**Setup:** Submit one request, then change the payer or recipient balance through the supported administrative path.

**Exercise:** Submit a later request involving those firms.

### SEQ010 A sequence of many debits from one balance

**Setup:** Set A to USD 100.00 and prepare twenty separate USD 10.00 requests.

**Exercise:** Send them sequentially with unique identities and capture every response.

## Concurrent requests and coordination

Scope: Core concurrency scenarios on the selected relational database.

Observation areas: Actual overlap, transaction schedules, row versions, locks, waits and operations across server processes.

### CON001 Two competing large debits

**Setup:** Set A to USD 100.00. Prepare A to B for USD 80.00 and A to C for USD 80.00.

**Exercise:** Start both requests together using separate processes and database connections.

### CON002 Two debits together equal the balance

**Setup:** Set A to USD 100.00. Prepare A to B for USD 60.00 and A to C for USD 40.00.

**Exercise:** Start both together and repeat with their release order reversed.

### CON003 Many competing debits

**Setup:** Set A to USD 100.00. Prepare twenty USD 10.00 requests to B and C.

**Exercise:** Release them from a shared barrier with distinct request identities.

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

### CON012 Payment races with an administrative adjustment

**Setup:** Prepare A to B for USD 80.00 and an administrative change of plus or minus USD 30.00 to A.

**Exercise:** Execute them concurrently through the actual supported write paths.

### CON013 Payer deletion during request processing

**Setup:** Pause an A to B request after firm lookup.

**Exercise:** Attempt to delete A through a second database connection, then resume the request.

### CON014 Recipient deletion during request processing

**Setup:** Pause an A to B request after B has been resolved.

**Exercise:** Attempt to delete B through a second connection and resume processing.

### CON015 UUID remapping during request processing

**Setup:** Pause a request after UUID lookup. In a maintenance connection, attempt a supported change to the referenced UUID mapping.

**Exercise:** Resume the request while the maintenance transaction is active, then repeat after it completes.

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

**Setup:** Prepare same payer, shared recipient and disjoint firm requests with unique identities.

**Exercise:** Send the mix through at least two server processes sharing one database.

### CON021 Large and small batches overlap

**Setup:** Prepare a large batch from A involving B and C, and a one entry batch from D involving B.

**Exercise:** Start both together and vary which transaction reaches shared rows first.

### CON022 An observer reads during an unfinished transfer

**Setup:** Pause a multi recipient request at several transaction stages.

**Exercise:** Use a separate database connection to read firms and payments during each pause and after completion.

## Failures inside transaction processing

Scope: Core failure injection with implementation dependent hook placement.

Observation areas: Transaction boundaries, connection state, recorded errors and actual persistent state after fault injection.

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

### FLT009 Commit rejected by the database

**Setup:** Use a controlled database fault or deferred constraint that fails when commit is attempted.

**Exercise:** Submit a request that reaches that point.

### FLT010 Connection loss before commit is sent

**Setup:** Pause a request after its transaction statements.

**Exercise:** Break the application database connection before a COMMIT command is transmitted.

### FLT011 Request cancellation during database work

**Setup:** Pause a request while a database statement is active.

**Exercise:** Cancel the request task or execution context through the framework's actual cancellation path.

### FLT012 Application process exits during a transaction

**Setup:** Hold a request after a balance or payment mutation.

**Exercise:** Terminate the worker process and later restart it against the same database.

### FLT013 Lock wait timeout

**Setup:** Hold a required firm row in another transaction and configure a short lock wait limit.

**Exercise:** Submit a request that reaches the blocked operation.

### FLT014 Statement timeout

**Setup:** Arrange a controlled slow database statement inside a payment transaction.

**Exercise:** Run the request with a configured statement timeout.

### FLT015 Database selects the request as a deadlock victim

**Setup:** Use a controlled second transaction to create a genuine lock cycle with a payment request.

**Exercise:** Release the participants far enough for database deadlock detection to act.

### FLT016 Serialization conflict

**Setup:** Where the selected strategy can produce a serialization error, coordinate competing transactions around the same balances.

**Exercise:** Trigger the actual database error rather than mocking only its exception class.

### FLT017 A later request reuses the same pooled connection

**Setup:** Cause a controlled transaction failure on a pooled connection.

**Exercise:** Return it through the application's normal cleanup path and send a new ordinary request that can reuse it.

### FLT018 Repeated transient faults during internal retries

**Setup:** Configure a finite retry policy if present and inject the selected transient database fault on successive attempts.

**Exercise:** Exercise both a fault sequence that ends and one lasting longer than the retry budget.

## Network retries and ambiguous delivery

Scope: Delivery scenarios exercised with both idempotency modes.

Observation areas: Client request identity, server attempts, database transaction completion and available response bytes.

### NET001 Connection fails before the server receives the body

**Setup:** Prepare an ordinary payment request.

**Exercise:** Drop the client connection before delivery, then resend the same request.

### NET002 Body transmission stops partway through

**Setup:** Prepare a valid multi entry body and cut the upload after part of it is transmitted.

**Exercise:** Reconnect and send the complete original body.

### NET003 Proxy sends a duplicate

**Setup:** Configure a controlled proxy to forward the same request twice to different instances.

**Exercise:** Send one client request while retaining both forwarded copies and timestamps.

### NET004 Client timeout while server work continues

**Setup:** Delay server processing beyond the client's timeout.

**Exercise:** Let the client retry before the first server attempt completes.

### NET005 Connection drops after commit and before response headers

**Setup:** Use a hook that can establish that a database transaction has committed.

**Exercise:** Drop the response connection before headers reach the client and resend the request.

### NET006 Response body is truncated

**Setup:** Allow response headers and only part of the body to reach the client.

**Exercise:** Retry the original request using the same client identity.

### NET007 Database commit acknowledgment is lost

**Setup:** Interrupt the database connection at the commit acknowledgment boundary.

**Exercise:** Exercise the application's recovery path and a later client retry without presuming the transaction outcome.

### NET008 Retry reaches another instance

**Setup:** Send an attempt to one instance, interrupt its response path and send the retry to another.

**Exercise:** Keep the database and logical request data shared between attempts.

### NET009 Several retries with backoff

**Setup:** Prepare one logical payment request and a sequence of interrupted response deliveries.

**Exercise:** Resend it at increasing intervals while earlier attempts may still be active.

### NET010 A delayed duplicate arrives after unrelated payments

**Setup:** Deliver a request, then issue several distinct transfers involving the same firms.

**Exercise:** Deliver an old copy of the original request afterward.

### NET011 Attempts arrive in a different order from transmission

**Setup:** Hold the first request in a proxy and let a later identical attempt reach the server first.

**Exercise:** Release the older copy while the newer attempt is processing or after it completes.

### NET012 Client disconnects at several processing stages

**Setup:** Prepare hooks before transaction start, during a database wait and after commit.

**Exercise:** Disconnect at each hook, reconnect and resend the same request.

## Request identity and idempotency controls

Scope: Conditional on the selected request identity mechanism.

Observation areas: Identity scope, request representation, metadata persistence, concurrent claims and retention policy.

### IDM001 No idempotency identity supplied

**Setup:** Prepare an ordinary request without a key, batch ID or equivalent identity input.

**Exercise:** Send it once and twice sequentially in each mode.

### IDM002 Same key and same bytes in sequence

**Setup:** Where keys exist, use K1 for an ordinary request.

**Exercise:** Send the exact same body with K1 twice, waiting for the first response.

### IDM003 Same key and same bytes concurrently

**Setup:** Prepare two byte identical copies carrying K1.

**Exercise:** Send them simultaneously to different application processes.

### IDM004 Same payload with different keys

**Setup:** Use identical payment bodies with K1 and K2.

**Exercise:** Submit them sequentially and concurrently in separate fixtures.

### IDM005 Same key with a changed amount

**Setup:** Prepare K1 with USD 25.00, then K1 with USD 25.01. Also prepare a malformed amount string followed by a corrected string using K1.

**Exercise:** Test sequential delivery and concurrent delivery of the different representations.

### IDM006 Same key with a changed recipient

**Setup:** Prepare two K1 requests that differ only between recipients B and C.

**Exercise:** Submit them in each order and simultaneously.

### IDM007 Same key with a changed payer

**Setup:** Prepare one K1 request from A and one from D using matching recipient and amount fields.

**Exercise:** Submit under the applicable identity scope.

### IDM008 Same key with a changed description

**Setup:** Prepare two K1 requests differing only in description text.

**Exercise:** Exercise ordinary text changes, whitespace changes and Unicode normalization changes.

### IDM009 Same key with an entry added or removed

**Setup:** Prepare a two entry K1 batch and variants containing one or three entries.

**Exercise:** Submit each variant after and concurrently with the original representation.

### IDM010 Same key with the payment array reordered

**Setup:** Use two distinct payment entries and K1.

**Exercise:** Deliver the original order and reversed order, sequentially and concurrently.

### IDM011 Same key with equivalent amount strings

**Setup:** Prepare K1 bodies using "25", "25.0" and "25.00" for the same entry.

**Exercise:** Submit every pair of representations.

### IDM012 Same key with equivalent JSON encoding

**Setup:** Change only object field order, indentation or escaped character spelling in K1 bodies.

**Exercise:** Submit both forms through the real parser and identity calculation path.

### IDM013 Same key with changed entry multiplicity

**Setup:** Prepare a K1 request with one entry and another with two identical copies of that entry.

**Exercise:** Submit the one entry and two entry versions in both orders.

### IDM014 Boundary forms of the key input

**Setup:** Where a key input exists, prepare empty, whitespace, mixed case, Unicode, very long and duplicate header values.

**Exercise:** Submit each form and variants differing only by case or surrounding whitespace.

### IDM015 Same key under different callers or scopes

**Setup:** If callers, tenants or endpoints are part of key scope, prepare requests sharing K1 across those boundaries.

**Exercise:** Send each pair sequentially and concurrently using authorized fixtures.

### IDM016 Worker stops after identity acquisition

**Setup:** Pause the selected identity mechanism immediately after a claim or metadata write.

**Exercise:** Stop the worker, restart it and resend K1.

### IDM017 Failure at the identity and payment persistence boundary

**Setup:** Locate each boundary between idempotency metadata, payment writes, balance writes and stored response data.

**Exercise:** Inject a fault at each boundary, then resend the original identity.

### IDM018 Old request repeated with a different current balance

**Setup:** Arrange a previously committed request identified by K1, then independently change the payer balance, including to zero.

**Exercise:** Resend its original body and K1.

### IDM019 Old request repeated after firm data changes

**Setup:** Arrange a previously committed K1 request. Rename, remove or otherwise change its referenced firms using supported maintenance operations.

**Exercise:** Resend the original K1 request for each separate fixture.

### IDM020 Identity expiration and cleanup race

**Setup:** If identities have retention limits, arrange K1 near expiry and a cleanup job about to process it.

**Exercise:** Resend just before, at and after the boundary, including a concurrent cleanup attempt.

## Payments reused across different batches

Scope: Conditional on a future payment identity or business duplicate mechanism.

Observation areas: How batch identity differs from payment identity and how partial overlaps are represented. Payment labels here identify fixture obligations only.

### REU001 Two batches share one payment

**Setup:** Prepare conceptual batch Q1 containing p1 and p2, and Q2 containing p2 and p3.

**Exercise:** Submit Q1 then Q2 with distinct batch identities; repeat concurrently.

### REU002 A later batch is a strict subset

**Setup:** Prepare Q1 containing p1, p2 and p3, then Q2 containing p2 only.

**Exercise:** Submit the two batches sequentially using independent request identities.

### REU003 A later batch is a strict superset

**Setup:** Prepare Q1 containing p1 and p2, then Q2 containing p1, p2 and p3.

**Exercise:** Submit Q1 followed by Q2 with distinct batch identities.

### REU004 The same payment set has a new batch identity

**Setup:** Prepare the same conceptual p1 and p2 in Q1 and Q2.

**Exercise:** Use different batch identities while keeping payment identities fixed, if such inputs exist.

### REU005 The same payment identity carries a changed amount

**Setup:** Where payment IDs exist, prepare p1 with USD 10.00 and later with USD 11.00 in a different batch.

**Exercise:** Submit both representations sequentially and concurrently.

### REU006 The same payment identity carries other changed fields

**Setup:** Where payment IDs exist, reuse p1 while changing recipient, description or payer in separate variants.

**Exercise:** Place the changed representation in a batch with a new request identity.

### REU007 One payment identity occurs twice within one batch

**Setup:** If payment IDs are introduced, place p1 twice in the same array.

**Exercise:** Exercise identical representations and two representations with conflicting fields.

### REU008 Shared payments in concurrently created batches

**Setup:** Prepare Q1 containing p1 and p2 and Q2 containing p2 and p3, with no prior requests.

**Exercise:** Start both on different instances and vary which attempt reaches shared identity storage first.

### REU009 The same payment label is used by different payers

**Setup:** Where identity scope is configurable, give A and D entries labeled p1.

**Exercise:** Submit the entries under separate payer and batch identities.

### REU010 Equal values represent separate obligations

**Setup:** Prepare p1 and p2 with the same payer, recipient, amount and description but representing two independently created obligations.

**Exercise:** Submit them within one batch and across separate batches; include a variant without optional payment IDs.

### REU011 Different payments share one recipient

**Setup:** Prepare distinct p1 and p2 for B with equal or different amounts.

**Exercise:** Submit them together and in separate batches while retaining their distinct identities where supported.

### REU012 A reused payment belongs to an unfinished earlier batch

**Setup:** Pause Q1 containing p1 and p2 before its transaction ends. Start Q2 containing p2 and p3.

**Exercise:** Complete, fail and stop Q1 in separate runs while Q2 is active.

## Idempotency mode changes and deployment

Scope: Both modes and conditional runtime switching scenarios.

Observation areas: Effective configuration, instance agreement, identity history and behavior across deployment boundaries.

### MOD001 Disabled mode followed by enabled mode

**Setup:** Submit a request while idempotency is disabled, then change the deployment to enabled mode.

**Exercise:** Resend the same input and any originally supplied identity.

### MOD002 Enabled mode followed by disabled mode

**Setup:** Arrange a completed request in enabled mode, then change to disabled mode.

**Exercise:** Resend its body and identity through the new configuration.

### MOD003 Mode changes while a request waits

**Setup:** Pause a request before transaction work or while it waits on a database row.

**Exercise:** Change the mode through the supported configuration path, resume it and send a retry.

### MOD004 Instances temporarily use different modes

**Setup:** Configure one instance with idempotency enabled and another with it disabled.

**Exercise:** Route identical and overlapping requests to both during a simulated rollout.

### MOD005 Enabled mode after a service restart

**Setup:** Submit identity bearing requests in enabled mode and stop all application processes.

**Exercise:** Restart them using the same database and resend the requests.

### MOD006 Disabled mode after a service restart

**Setup:** Submit requests in disabled mode and stop all application processes.

**Exercise:** Restart against the same database and resend the original input.

### MOD007 Application rollback with existing identity metadata

**Setup:** Arrange metadata using the newer application version, then deploy a supported previous version or schema compatibility fixture.

**Exercise:** Send new requests and repeats under both available modes.

### MOD008 Different modes for different scopes

**Setup:** If configuration supports payer or tenant scoped flags, enable idempotency for one scope and disable it for another.

**Exercise:** Send matching payloads and matching key strings across those scopes.

## Database schema and alternative write paths

Scope: Architecture checks using direct database and maintenance scenarios.

Observation areas: Constraints, referential integrity, legacy data, integer expressions and every path that changes money.

### DBS001 Direct writes with missing monetary data

**Setup:** Through a controlled database connection, attempt null balances, null payment amounts and missing payer or recipient references.

**Exercise:** Exercise each field independently using the selected schema.

### DBS002 Direct writes with nonpositive amounts or negative balances

**Setup:** Prepare direct inserts and updates using zero or negative payment amounts and a negative firm balance.

**Exercise:** Execute them outside the HTTP endpoint in an isolated fixture.

### DBS003 Direct writes with nonexistent firm references

**Setup:** Use nonexistent internal payer and recipient IDs in payment inserts.

**Exercise:** Test each reference independently and together.

### DBS004 Concurrent creation of the same public UUID

**Setup:** Prepare two separate database transactions inserting firms with the same public UUID.

**Exercise:** Start both together, then exercise lookup through the service.

### DBS005 Generated IDs near exhaustion

**Setup:** Use an isolated sequence or identity column near its selected maximum.

**Exercise:** Insert firms and payments through normal paths across that boundary.

### DBS006 Preexisting inconsistent monetary data

**Setup:** Seed a controlled legacy fixture with a negative balance or a payment row not represented by fixture balance history.

**Exercise:** Submit requests touching that firm and separate requests touching other firms.

### DBS007 Database arithmetic at numeric limits

**Setup:** Prepare values for which intermediate SQL sums, casts or update expressions approach the selected integer limits.

**Exercise:** Run through the real application query path, including repeated recipients.

### DBS008 Firm deletion with existing payment references

**Setup:** Arrange firms referenced by previously committed payment rows.

**Exercise:** Invoke each supported deletion or archival path while another request references the same firms.

### DBS009 Another writer changes balances

**Setup:** Exercise a background job, administrative tool or direct SQL writer that adjusts balances alongside a payment request.

**Exercise:** Use both any shared coordination protocol and a controlled legacy writer, if one exists.

### DBS010 Schema and seed initialization

**Setup:** Start with an empty database and then a database already containing the official fixture.

**Exercise:** Run the documented initialization process, restart the service and submit a sample request after each setup.

## Capacity and operational conditions

Scope: Configured limits and operational architecture scenarios.

Observation areas: Request sizes, resource use, time limits, connections, configuration and diagnostic records.

### OPS001 Payment count around a configured limit

**Setup:** If the service defines maximum count L, prepare batches with L minus one, L and L plus one entries.

**Exercise:** Submit them in both modes with small amounts and sufficient fixture balances where representable.

### OPS002 Request byte size around a configured limit

**Setup:** Prepare bodies just below, at and above the selected request byte limit.

**Exercise:** Vary description sizes while keeping the number of payments fixed.

### OPS003 Description length around a configured limit

**Setup:** If a description limit exists, prepare lengths just below, at and above it.

**Exercise:** Repeat using ASCII, multibyte Unicode and emoji to separate byte and character counts.

### OPS004 Extremely long amount strings

**Setup:** Prepare amount strings containing thousands and then many more digits, including a very long string of leading zeros.

**Exercise:** Submit them through the actual HTTP parser and numeric conversion path.

### OPS005 Very large arrays with one recipient

**Setup:** Prepare a large array of small payments to B within a suitably funded fixture.

**Exercise:** Increase the array size, including variants with mostly identical entries.

### OPS006 Large result and identity response records

**Setup:** If responses include individual payment IDs or stored replay data, prepare a batch large enough to produce a large response.

**Exercise:** Send it once, interrupt response delivery and later repeat its identity where supported.

### OPS007 Sustained traffic for one payer

**Setup:** Generate a sustained series of requests for A using unique identities and a documented starting balance.

**Exercise:** Run across several instances for a fixed measured interval.

### OPS008 Independent large batches in parallel

**Setup:** Create several disjoint sets of firms with adequate balances.

**Exercise:** Run large batches on all sets concurrently and record resource and wait measurements.

### OPS009 Database connection pool exhaustion

**Setup:** Occupy the configured pool with controlled long running operations.

**Exercise:** Submit ordinary payments, repeats and then new requests as connections become available.

### OPS010 Database unavailable during a request

**Setup:** Make the database unavailable before connection acquisition and, separately, during an active request.

**Exercise:** Restore access and submit new requests plus repeats of interrupted requests.

### OPS011 Invalid or ambiguous mode configuration

**Setup:** Prepare missing, malformed and conflicting idempotency configuration values using supported startup and deployment inputs.

**Exercise:** Start or reload the service with each configuration.

### OPS012 Operational records under concurrency and retries

**Setup:** Run a mixed sequence of ordinary requests, repeated identities, validation inputs and injected faults.

**Exercise:** Capture application logs, correlation identifiers and database observations for each attempt.

## Authorization and trust boundaries

Scope: Conditional extension if authentication or tenant isolation is included.

Observation areas: Caller identity, payer authority, tenant boundaries, untrusted fields and exposed diagnostic data.

### SEC001 Missing or invalid credentials

**Setup:** If authentication is present, prepare absent, malformed, expired and revoked credentials.

**Exercise:** Submit ordinary requests and requests repeating a previously used identity.

### SEC002 Caller references another payer

**Setup:** Give a caller access to A but use D as payer in the body.

**Exercise:** Send a new request and a request carrying an identity previously used by D's authorized caller.

### SEC003 Recipient crosses an access boundary

**Setup:** If tenants or recipient visibility rules exist, give the caller a payer in one scope and a recipient in another.

**Exercise:** Submit one recipient and mixed recipient batches across the boundary.

### SEC004 Another caller repeats a known identity

**Setup:** Arrange an identity bearing request by one caller and disclose only its key to a second test caller.

**Exercise:** Send the same body and altered bodies as the second caller under the applicable authorization fixtures.

### SEC005 Injection shaped identifier and text input

**Setup:** Place quotes, SQL fragments and comment markers in UUID fields and description strings.

**Exercise:** Submit them through the public API with valid credentials where needed.

### SEC006 Client supplies internal balance or ownership fields

**Setup:** Add balance_cents, payer_firm_id, payee_firm_id and ownership shaped fields to the body.

**Exercise:** Vary both top level and payment object placement.

### SEC007 Signed request data is modified

**Setup:** If signatures or request digests are implemented, prepare a signed ordinary request.

**Exercise:** Change amount, payer, recipient or key after signing, including repeated delivery variants.

### SEC008 Diagnostic exposure during failures

**Setup:** Trigger malformed input, unknown UUIDs, constraint errors and database unavailability using distinct test identities.

**Exercise:** Capture complete HTTP responses and diagnostic output visible to each caller role.

## References

- **Challenge brief:** TA Firm Payments.pdf, pages 2 to 5. The original request and sample fixtures are the source of the core service context.
- **Scope of this revision:** Working specification dated 29 October 2026. Two idempotency modes are planned; mode specific expected results are deferred.
- **PostgreSQL transaction isolation:** https://www.postgresql.org/docs/18/transaction-iso.html
- **PostgreSQL explicit locking:** https://www.postgresql.org/docs/18/explicit-locking.html
- **PostgreSQL numeric types:** https://www.postgresql.org/docs/18/datatype-numeric.html
- **PostgreSQL constraints:** https://www.postgresql.org/docs/18/ddl-constraints.html
