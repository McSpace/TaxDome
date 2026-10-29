-- Official challenge seed. Inserted only into an empty firms table, so restarts and
-- re-initialization never overwrite existing balances or payments.

INSERT INTO app.firms (id, name, balance_cents, uuid)
SELECT v.id, v.name, v.balance_cents, v.uuid
  FROM (VALUES
        (1, 'Pinecrest CPA Group', 5000000, '3f1c9a2e-7b4d-4c1e-9a55-2d8e6f0b7c41'),
        (2, 'Lopez Bookkeeping',     50000, '8b2e4c71-0d3a-4f6e-b1c9-5a7d2e9f4c10'),
        (3, 'Nair Tax Services',    200000, 'e5f18b3c-2a9d-4c07-8e6b-1d4a7f9c3b25')
       ) AS v (id, name, balance_cents, uuid)
 WHERE NOT EXISTS (SELECT 1 FROM app.firms);
