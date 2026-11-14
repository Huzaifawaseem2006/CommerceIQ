# CommerceIQ — AI-Powered E-Commerce Database Assistant

CommerceIQ is a Python-based AI assistant that enables users to query an e-commerce MySQL database using natural language.

Built with the **Claude API**, the project demonstrates LLM tool calling, multi-turn conversations, SQL validation, and secure database access.

## Key Features

- **Natural Language Queries:** Ask business questions without writing SQL manually.
- **LLM Tool Calling:** Claude generates SQL queries and invokes a Python database tool.
- **Secure Database Access:** Read-only MySQL permissions and SQLGlot-based query validation.
- **Multi-Turn Conversations:** Maintains conversation context across questions.
- **Safety Controls:** Rejects unauthorized SQL operations and limits query execution.
- **Automated Testing:** Includes tests for database operations, tool integration, and CLI behavior.

## Tech Stack

- **Language:** Python
- **AI:** Anthropic Claude API
- **Database:** MySQL
- **SQL Validation:** SQLGlot
- **Testing:** pytest

## How It Works

1. The user asks a business question in natural language.
2. Claude analyzes the question and generates a tool call.
3. The `query_database()` function validates the SQL query.
4. The validated query executes against the read-only MySQL database.
5. The database returns structured results.
6. Claude interprets the results and responds to the user.

## Example Questions

- What are the top 5 products by completed-order revenue?
- Which customers have placed the most orders?
- Which products are running low on stock?
- What is the total completed revenue by month?

## Project Purpose

CommerceIQ explores how LLM-powered assistants can make structured business data accessible through natural-language interactions while maintaining controlled database access.

## Prerequisites
1. Python 3.11+
2. MySQL 8+
3. MySQL Workbench, recommended for instructor verification

## Python setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with local setup credentials. Do not commit real passwords or API keys.

## Database setup
Create the schema and tables:

```powershell
mysql -u root -p < scripts/init_db.sql
```

Generate and validate the deterministic sample data without touching MySQL:

```powershell
python scripts/seed_data.py --dry-run
```

Load the sample data:

```powershell
python scripts/seed_data.py
```

The seed script inserts approximately 50 customers, 30 products, 200 orders, and 400 order items. It refuses to seed if any target table already has rows. To intentionally reload the sample dataset, run:

```powershell
python scripts/seed_data.py --reset
```

Create the runtime read-only account after replacing the placeholder password in `scripts/create_readonly_user.sql`:

```powershell
mysql -u root -p < scripts/create_readonly_user.sql
```

## Query tool
`commerceiq.query_database.query_database(sql_query: str)` is the single database tool that will later be exposed to Claude. It currently:

- Reads runtime database credentials from `COMMERCEIQ_DB_*` environment variables.
- Accepts one MySQL `SELECT` statement only.
- Uses `sqlglot` plus explicit allowlist checks for the `commerceiq` schema and the four documented tables.
- Rejects comments, write statements, metadata schemas, multi-statements, `SELECT INTO OUTFILE`, and locking reads.
- Sets a MySQL session query timeout where supported.
- Fetches at most 100 rows and returns JSON-safe structured results.

Example local smoke test after MySQL is configured:

```powershell
python -c "from commerceiq.query_database import query_database; import json; print(json.dumps(query_database('SELECT name, price FROM products LIMIT 5'), indent=2))"
```

## Verification
Run the automated tests:

```powershell
pytest
```

The default tests mock MySQL for the query tool, so they do not require a live database or a Claude API call.

## Claude CLI
Configure these values in `.env`:

```powershell
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5
COMMERCEIQ_DB_HOST=localhost
COMMERCEIQ_DB_PORT=3306
COMMERCEIQ_DB_NAME=commerceiq
COMMERCEIQ_DB_USER=commerceiq_readonly
COMMERCEIQ_DB_PASSWORD=your_readonly_password
```

Start the interactive CLI:

```powershell
python -m commerceiq.cli
```

Useful commands inside the CLI:

- `/clear`: reset conversation history for a fresh question.
- `exit` or `quit`: close the CLI.

The CLI prints every SQL query Claude asks the `query_database` tool to run so the instructor can compare it in MySQL Workbench. Add `--debug` to also print summarized tool results:

```powershell
python -m commerceiq.cli --debug
```

Sample demo questions:

- `What are the top 5 products by completed-order revenue?`
- `Which customers in Seattle have completed orders?`
- `Show total completed revenue by month in 2026.`
- `Which products are low on stock, below 15 units?`
- `What is the profit margin by category?`

In MySQL Workbench, verify these row counts after seeding:

- `customers`: 50
- `products`: 30
- `orders`: 200
- `order_items`: 400

Revenue must be calculated as `SUM(order_items.quantity * order_items.unit_price)` for `Completed` orders only. Pending and cancelled orders do not count toward realized revenue.
