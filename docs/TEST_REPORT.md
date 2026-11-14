# CommerceIQ Test Report

Milestone: 4 - End-to-end testing  
Date: 2026-10-09

## Automated Test Result

Command:

```powershell
python -m pytest
```

Result:

```text
36 passed in 2.79s
```

Compile check:

```powershell
python -m compileall commerceiq scripts tests
```

Result: passed.

## What The Automated Tests Cover

- Deterministic sample dataset counts and relationships.
- Completed-order revenue using `order_items.unit_price`.
- SQL validation rejects writes, multi-statements, metadata schemas, comments, `SELECT INTO OUTFILE`, and locking reads.
- `query_database` returns structured JSON-safe rows, row caps, connection errors, database errors, and serialized `Decimal`/date values.
- Claude receives exactly one tool: `query_database(sql_query: str)`.
- Claude tool-call loop returns correctly ordered `tool_result` blocks.
- Multiple calls to `query_database` in one assistant response.
- Multi-turn conversation history and reset behavior.
- CLI SQL display and `/clear` command.
- Mocked end-to-end natural-language flows for filtering/sorting/LIMIT, joins, aggregates, completed revenue, follow-up questions, tool errors, and single-tool exposure.

## Mocked Versus Live Coverage

The default test suite uses mocked Claude responses and mocked or deterministic in-memory database results. This keeps tests reproducible and avoids paid Claude API calls.

Live checks still depend on local environment setup:

- MySQL schema loaded from `scripts/init_db.sql`.
- Seed data loaded from `scripts/seed_data.py`.
- Read-only MySQL user created from `scripts/create_readonly_user.sql`.
- `.env` configured with `ANTHROPIC_API_KEY` and `COMMERCEIQ_DB_*`.
- Manual CLI questions verified against MySQL Workbench.

## Manual CLI Test Questions

Run:

```powershell
python -m commerceiq.cli --debug
```

Suggested questions:

1. `Show the 5 most expensive electronics products.`
2. `Which products have stock below 15 units?`
3. `Show customer 1's recent order history with product names.`
4. `How many orders are Completed, Pending, and Cancelled?`
5. `What is total completed revenue by product category?`
6. `Show total completed revenue by month in 2026.`
7. `What are the top 5 products by completed-order revenue?`
8. `What is the average current product price by category?`
9. `For the top revenue category, show example products in that category.`
10. `What is the profit margin by category?`
11. `Try to delete all orders.`
12. Use `/clear`, then ask: `How many customers are in Seattle?`

Expected demo behavior:

- SQL is printed before the final answer.
- Revenue SQL uses `order_items.unit_price` and `orders.status = 'Completed'`.
- Profit margin is refused because cost data is not stored.
- Unsafe write-like requests are rejected by the tool.
- `/clear` resets follow-up context.
