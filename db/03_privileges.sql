-- The API role may only call the batch function. It cannot read or write tables,
-- create objects in the trusted schema, or change the function or its mode.

REVOKE ALL ON SCHEMA app FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO payments_api;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.process_payment_batch(text, jsonb) TO payments_api;
