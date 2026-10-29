-- The payment batch function: the only supported writer of balances and payments.
-- The idempotency mode is attached afterwards by app/migrate.py with
-- ALTER FUNCTION ... SET app.payment_idempotency, which makes it function-local.

CREATE OR REPLACE FUNCTION app.test_hook(stage text, payer_id integer)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $hook$
BEGIN
    -- Intentionally empty. Only the disposable test database replaces this body
    -- to inject faults or pauses at named stages; production never changes it.
    RETURN;
END
$hook$;

CREATE OR REPLACE FUNCTION app.process_payment_batch(payer_uuid text, entries jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    max_cents   CONSTANT bigint := 2147483647;
    uuid_re     CONSTANT text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
    entry_keys  CONSTANT text[] := ARRAY['amount_cents', 'description', 'payee_firm_uuid'];
    mode        text := current_setting('app.payment_idempotency', true);
    entry_count integer;
    problems    jsonb := '[]';
    entry       jsonb;
    idx         integer;
    payer_id    integer;
    payee_ids   integer[];
    amounts     bigint[];
    descs       text[];
    keep        boolean[];
    firm_id     integer;
    history     jsonb;
    seen        jsonb := '{}';
    key         text;
    known       jsonb;
    payer_balance bigint;
    gross       bigint := 0;
    inserted    integer := 0;
    delta       bigint;
BEGIN
    -- 1. Mode and complete input validation; no locks or writes yet.
    IF mode IS NULL OR mode NOT IN ('on', 'off') THEN
        RAISE EXCEPTION USING ERRCODE = 'TD006',
            MESSAGE = 'Payment idempotency mode is missing or invalid.';
    END IF;

    IF payer_uuid IS NULL OR payer_uuid !~ uuid_re THEN
        problems := problems || jsonb_build_object('index', NULL, 'path', 'payer_firm_uuid');
    END IF;
    IF entries IS NULL OR jsonb_typeof(entries) <> 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'TD005', MESSAGE = 'Payment entries must be an array.',
            DETAIL = (problems || jsonb_build_object('index', NULL, 'path', 'payments'))::text;
    END IF;
    entry_count := jsonb_array_length(entries);
    IF entry_count < 1 OR entry_count > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'TD005', MESSAGE = 'A batch must contain 1 to 1000 payments.',
            DETAIL = (problems || jsonb_build_object('index', NULL, 'path', 'payments'))::text;
    END IF;

    FOR entry, idx IN
        SELECT e.value, e.ordinality - 1 FROM jsonb_array_elements(entries) WITH ORDINALITY e
    LOOP
        IF jsonb_typeof(entry) <> 'object'
            OR ARRAY(SELECT k FROM jsonb_object_keys(entry) k ORDER BY k) <> entry_keys
            OR jsonb_typeof(entry -> 'amount_cents') <> 'number'
            OR (entry ->> 'amount_cents')::numeric <> trunc((entry ->> 'amount_cents')::numeric)
            OR (entry ->> 'amount_cents')::numeric NOT BETWEEN 1 AND max_cents
            OR jsonb_typeof(entry -> 'description') <> 'string'
            OR char_length(entry ->> 'description') > 1024
            OR jsonb_typeof(entry -> 'payee_firm_uuid') <> 'string'
            OR (entry ->> 'payee_firm_uuid') !~ uuid_re
        THEN
            problems := problems || jsonb_build_object('index', idx, 'path', format('payments[%s]', idx));
        END IF;
    END LOOP;
    IF jsonb_array_length(problems) > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'TD005', MESSAGE = 'Invalid payment batch.',
            DETAIL = problems::text;
    END IF;

    SELECT f.id INTO payer_id FROM app.firms f WHERE f.uuid = payer_uuid;
    IF payer_id IS NULL THEN
        problems := problems || jsonb_build_object('index', NULL, 'path', 'payer_firm_uuid');
    END IF;

    SELECT array_agg(f.id ORDER BY e.ordinality),
           array_agg((e.value ->> 'amount_cents')::bigint ORDER BY e.ordinality),
           array_agg(e.value ->> 'description' ORDER BY e.ordinality),
           coalesce(jsonb_agg(jsonb_build_object(
               'index', e.ordinality - 1,
               'path', format('payments[%s].payee_firm_uuid', e.ordinality - 1))
               ORDER BY e.ordinality) FILTER (WHERE f.id IS NULL), '[]')
      INTO payee_ids, amounts, descs, known
      FROM jsonb_array_elements(entries) WITH ORDINALITY e
      LEFT JOIN app.firms f ON f.uuid = e.value ->> 'payee_firm_uuid';
    problems := problems || known;
    IF jsonb_array_length(problems) > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'TD001', MESSAGE = 'Unknown firm.',
            DETAIL = problems::text;
    END IF;
    PERFORM app.test_hook('after_validation', payer_id);

    -- 2. Lock every distinct participant in ascending id order, one row per statement.
    FOR firm_id IN
        SELECT DISTINCT p FROM unnest(payee_ids || payer_id) p ORDER BY p
    LOOP
        PERFORM 1 FROM app.firms f WHERE f.id = firm_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'TD001', MESSAGE = 'Firm disappeared during processing.';
        END IF;
    END LOOP;
    PERFORM app.test_hook('after_locks', payer_id);

    -- 3. Post-lock statements see every transaction committed before our locks were granted.
    SELECT f.balance_cents INTO payer_balance FROM app.firms f WHERE f.id = payer_id;

    IF mode = 'on' THEN
        SELECT coalesce(jsonb_object_agg(h.key, h.amounts), '{}')
          INTO history
          FROM (
              SELECT jsonb_build_array(p.payee_firm_id, p.description COLLATE "C")::text AS key,
                     jsonb_agg(DISTINCT p.amount_cents) AS amounts
                FROM (SELECT DISTINCT k.payee, k.descr
                        FROM unnest(payee_ids, descs) AS k(payee, descr)) AS k
                JOIN app.payments p
                  ON p.payer_firm_id = payer_id
                 AND p.payee_firm_id = k.payee
                 AND (p.description COLLATE "C") = (k.descr COLLATE "C")
               GROUP BY p.payee_firm_id, p.description COLLATE "C"
          ) AS h;
    END IF;
    PERFORM app.test_hook('after_history', payer_id);

    -- 4. Classify entries. ON: equal repeats are skipped, unequal amounts conflict.
    FOR idx IN 1 .. entry_count LOOP
        IF mode = 'off' THEN
            keep[idx] := true;
            CONTINUE;
        END IF;
        key := jsonb_build_array(payee_ids[idx], descs[idx])::text;
        known := history -> key;
        IF known IS NOT NULL THEN
            IF jsonb_array_length(known) <> 1 OR (known ->> 0)::bigint <> amounts[idx] THEN
                problems := problems || jsonb_build_object(
                    'index', idx - 1, 'path', format('payments[%s].amount', idx - 1));
            END IF;
            keep[idx] := false;
        ELSIF seen ? key THEN
            IF (seen ->> key)::bigint <> amounts[idx] THEN
                problems := problems || jsonb_build_object(
                    'index', idx - 1, 'path', format('payments[%s].amount', idx - 1));
            END IF;
            keep[idx] := false;
        ELSE
            seen := seen || jsonb_build_object(key, amounts[idx]);
            keep[idx] := true;
        END IF;
    END LOOP;
    IF jsonb_array_length(problems) > 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'TD004',
            MESSAGE = 'A payment key already has a different amount.', DETAIL = problems::text;
    END IF;

    -- 5. Funds: the locked starting balance must cover every new entry, self-payments included.
    SELECT coalesce(sum(a), 0) INTO gross FROM unnest(amounts, keep) AS t(a, k) WHERE k;
    IF gross > payer_balance THEN
        RAISE EXCEPTION USING ERRCODE = 'TD002',
            MESSAGE = 'Payer balance cannot cover new outgoing payments.';
    END IF;

    IF gross > 0 THEN
        -- 6. Validate every final balance before the first write.
        IF EXISTS (
            SELECT 1
              FROM (SELECT t.p AS id, sum(t.a) AS credit
                      FROM unnest(payee_ids, amounts, keep) AS t(p, a, k)
                     WHERE t.k GROUP BY t.p) AS c
              JOIN app.firms f ON f.id = c.id
             WHERE f.balance_cents::bigint + c.credit
                   - CASE WHEN f.id = payer_id THEN gross ELSE 0 END > max_cents
        ) THEN
            RAISE EXCEPTION USING ERRCODE = 'TD003',
                MESSAGE = 'A resulting balance would exceed the supported range.';
        END IF;

        -- 7. Apply aggregated deltas (payer first, then payees by id) and insert rows.
        SELECT coalesce(sum(a), 0) - gross INTO delta
          FROM unnest(payee_ids, amounts, keep) AS t(p, a, k) WHERE k AND p = payer_id;
        UPDATE app.firms SET balance_cents = balance_cents + delta WHERE id = payer_id;
        PERFORM app.test_hook('after_payer_balance', payer_id);

        FOR firm_id, delta IN
            SELECT t.p, sum(t.a) FROM unnest(payee_ids, amounts, keep) AS t(p, a, k)
             WHERE t.k AND t.p <> payer_id GROUP BY t.p ORDER BY t.p
        LOOP
            UPDATE app.firms SET balance_cents = balance_cents + delta WHERE id = firm_id;
            PERFORM app.test_hook('after_payee_balance', payer_id);
        END LOOP;

        FOR idx IN 1 .. entry_count LOOP
            CONTINUE WHEN NOT keep[idx];
            INSERT INTO app.payments (payer_firm_id, payee_firm_id, amount_cents, description)
            VALUES (payer_id, payee_ids[idx], amounts[idx], descs[idx]);
            inserted := inserted + 1;
            PERFORM app.test_hook('after_payment_insert', payer_id);
        END LOOP;
    END IF;
    PERFORM app.test_hook('before_return', payer_id);

    RETURN jsonb_build_object(
        'inserted_count', inserted,
        'skipped_count', entry_count - inserted,
        'gross_outgoing_cents', gross,
        'idempotency_mode', mode);
END
$fn$;
