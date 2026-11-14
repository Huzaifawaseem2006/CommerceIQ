# Product Requirements Document — CommerceIQ

**Version:** 1.0  
**Status:** Ready for implementation  
**Project type:** Small AI engineering assignment

## 1. Summary
CommerceIQ is a Python CLI application that lets users ask natural-language questions about a sample e-commerce MySQL database. Claude receives a documented, allowlisted database schema, generates a read-only SQL query, and invokes **exactly one LLM-exposed tool**: `query_database(sql_query: str)`. The Python application validates and executes the query, returns structured results to Claude, and displays Claude's grounded answer.

## 2. Goals
- Demonstrate an end-to-end Claude API tool-use loop with a real relational database.
- Support natural-language filtering, joins, grouping, sorting, and aggregation.
- Let the instructor inspect all tables and independently reproduce SQL results in MySQL Workbench.
- Keep the implementation understandable, reproducible, secure, and small.

## 3. Non-goals
- Web frontend, authentication UI, deployment, multi-user sessions, vector search, RAG, LangChain, MCP, database writes, arbitrary filesystem access, or multiple LLM tools.
- Perfect natural-language-to-SQL accuracy on all possible questions.

## 4. Users and demo
Primary user: student developer demonstrating the project to an instructor. Demo: open MySQL Workbench, show tables and data; start CLI; ask questions; display the generated SQL, tool output, and final Claude answer; cross-check a query in Workbench.

## 5. Stack
- Python 3.11+
- Anthropic Python SDK (current supported release), Claude model configured via environment variable
- MySQL 8+
- `mysql-connector-python` for DB access
- `python-dotenv` for local environment configuration
- `pytest` for tests
- MySQL Workbench for inspection
- No orchestration frameworks

## 6. Data model
Create schema `commerceiq` with four tables:
- `customers(customer_id PK, name, email UNIQUE, city)`
- `products(product_id PK, name, category, price DECIMAL(10,2), stock_quantity INT)`
- `orders(order_id PK, customer_id FK, order_date DATE, status ENUM('Completed','Pending','Cancelled'))`
- `order_items(order_item_id PK, order_id FK, product_id FK, quantity INT, unit_price DECIMAL(10,2))`

Seed approximately 50 customers, 30 products, 200 orders, and 400 order items. Use deterministic random seed and fixed dates in 2026. Enforce foreign keys, positive quantities/prices, nonnegative stock, and valid order status. `unit_price` is the historical purchase price, which may differ from current product price.

Business rules: revenue = SUM(order_items.quantity * order_items.unit_price) for **Completed** orders only. Pending and Cancelled orders do not count toward realized revenue. Top-selling products by quantity should also use Completed orders unless the user explicitly requests another status. No cost fields exist, so profit margin cannot be computed.

## 7. Core user stories
1. As a user, I can ask for products matching price, category, and stock conditions.
2. As a user, I can ask for customer order histories.
3. As a user, I can ask for sales totals by date range.
4. As a user, I can ask for top products or categories by revenue or units sold.
5. As a user, I receive an honest explanation when the schema lacks requested information.
6. As an instructor, I can inspect the generated SQL and reproduce its results in Workbench.

## 8. Functional requirements
### FR-01 Database initialization
Provide scripts to create tables, insert deterministic synthetic records, and verify row counts. Do not overwrite an existing populated database without an explicit confirmation step.

### FR-02 Schema context
Provide Claude only the documented allowlisted table and column definitions, relationships, and revenue rules. Keep this schema in `docs/DATABASE_SCHEMA.md` and load it into the system instructions or equivalent application-controlled context. Do not include credentials.

### FR-03 Single tool
Expose exactly one LLM tool with name `query_database`, description explaining it executes a read-only query against the e-commerce dataset, and required string input `sql_query`. No other tool is exposed to Claude.

### FR-04 Tool implementation
The Python dispatcher must validate tool name and input, validate SQL, execute against a MySQL account restricted to SELECT on `commerceiq` tables, and return JSON-serializable structured data with columns, rows, row count, truncation status, and an error object on failure. Serialize `Decimal`, `date`, and `datetime` explicitly.

### FR-05 Safety
- Only one SQL statement per invocation.
- Only read-only SELECT queries; disallow DML, DDL, administrative commands, `INTO OUTFILE`, locking reads, stored procedures, and other side-effect-capable syntax.
- Use a robust MySQL-aware SQL parser/validator or conservative allowlist; do not depend only on a `startswith('SELECT')` check or regex.
- Enforce least-privilege MySQL credentials at the server level; this is the primary safety boundary.
- Restrict to the `commerceiq` schema; do not expose other schemas or metadata tables.
- Set database execution timeout where supported, limit result rows to 100, and cap serialized output size.
- Do not interpolate user-supplied values into any application-authored SQL; parameterize such values. For model-generated SQL, validation and DB permissions are mandatory.
- Do not expose secrets or raw stack traces to Claude or CLI users.

### FR-06 Claude integration
Implement Anthropic Messages API tool calling with the current SDK. Handle assistant `tool_use` blocks, dispatch to `query_database`, append correctly structured `tool_result` blocks, and continue until a final assistant answer is returned. Support multiple invocations of the **same** tool in one user turn; limit tool-use iterations (e.g., 5). Respect the API's required message ordering. Handle API failures gracefully.

### FR-07 CLI
Interactive CLI accepting questions until `exit` or `quit`. Display final natural-language answer. Provide a `--debug` option to display tool arguments, generated SQL, and summarized tool results, without leaking credentials.

### FR-08 Grounding
Instruct Claude to use returned rows for factual answers, not invent missing values, and clearly report empty or incomplete results. If user asks for unavailable profit margins, state that product costs are not stored.

## 9. Quality and testing
- Unit tests: SQL rejection cases, serialization, tool input validation, result caps, and empty results.
- Integration tests: MySQL connection, seeded row counts, joins, revenue totals, and read-only DB permissions (when test DB available).
- Mocked Claude tests: tool-use -> tool-result -> final response; multiple calls to the same tool; API errors and loop limits.
- At least 10 manual prompts covering filters, joins, aggregates, date ranges, ambiguous requests, missing data, and adversarial SQL.
- Tests should run without a paid API call by default; live API tests opt-in.

## 10. Acceptance criteria
- [ ] MySQL Workbench shows 4 populated, relationally valid tables.
- [ ] CLI handles at least 8 of 10 documented representative prompts correctly on the fixed dataset; expected SQL outputs are checked in Workbench.
- [ ] Exactly one tool (`query_database`) is registered with Claude.
- [ ] Generated SQL and result are visible in debug mode.
- [ ] Read-only SQL works; UPDATE, DELETE, DROP, multi-statements, and disallowed SELECT forms are rejected.
- [ ] Tool result is returned to Claude, and final response is based on that result.
- [ ] Empty results and unsupported questions are handled honestly.
- [ ] README includes prerequisites, environment variables, setup, demo, and tests.
- [ ] No credentials are committed.

## 11. Implementation milestones
1. Scaffold repo, schema, and reproducible seed script.
2. Build and test secure `query_database` implementation without Claude.
3. Add Claude tool schema, dispatcher, and complete Messages API loop.
4. Add interactive CLI and optional debug output.
5. Test end-to-end, document Workbench demo, and refine error handling.

**Workflow requirement:** Codex should first inspect PRD.md and AGENTS.md, propose a short plan, then implement milestone-by-milestone with tests. Do not introduce extra tools or frameworks without explaining why.
