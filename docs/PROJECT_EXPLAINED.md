# CommerceIQ Project Explained

This document explains the actual CommerceIQ implementation in this repository. It is written so you can understand the project deeply and explain it clearly in an instructor demo or viva.

The main files discussed are:

- `commerceiq/query_database.py`
- `commerceiq/claude_app.py`
- `commerceiq/cli.py`
- `scripts/init_db.sql`
- `scripts/seed_data.py`
- `scripts/create_readonly_user.sql`
- `docs/DATABASE_SCHEMA.md`
- `tests/*.py`

No API keys, database passwords, or private values are included here.

## 1. Project Overview

CommerceIQ is a Python command-line application that lets a user ask natural-language questions about a sample e-commerce MySQL database.

Example user question:

```text
What are the top 5 products by completed-order revenue?
```

Claude reads the database schema and business rules, decides what SQL query is needed, and asks Python to run exactly one tool:

```text
query_database(sql_query: str)
```

Python validates the SQL, executes it against MySQL using a read-only database user, returns structured results to Claude, and Claude writes a final natural-language answer.

### What problem it solves

The project demonstrates how an LLM can answer data questions without getting direct, unrestricted database access. The Python validator and the configured MySQL account limit what queries can do, but the validator is not a complete guarantee against every side-effect-capable `SELECT`.

The important idea is separation of responsibility:

- Claude understands natural language and generates SQL.
- Python validates and executes SQL.
- MySQL stores the real data.
- `query_database` is the only bridge between Claude and the database.

Claude does not receive database credentials. Claude does not connect directly to MySQL. Claude can only request a SQL query through the one registered tool.

### Technologies used and why

| Technology | Where used | Why |
|---|---|---|
| Python 3.11+ | Application code | Simple scripting, CLI, tests, API calls |
| MySQL 8+ | Database | Real relational database for demo and Workbench inspection |
| Anthropic Python SDK | `commerceiq/claude_app.py` | Official Claude Messages API integration |
| `mysql-connector-python` | `commerceiq/query_database.py`, `scripts/seed_data.py` | Connect Python to MySQL |
| `sqlglot` | `commerceiq/query_database.py` | Parse SQL before execution |
| `python-dotenv` | DB and API config | Load `.env` without hardcoding secrets |
| `pytest` | `tests/` | Automated tests without paid API calls by default |

### Complete workflow

Text diagram:

```text
User question
    |
    v
commerceiq.cli.main()
    |
    v
CommerceIQAssistant.ask()
    |
    v
Claude Messages API
    |
    v
Claude returns tool_use: query_database(sql_query)
    |
    v
CommerceIQAssistant.dispatch_tool_use()
    |
    v
query_database(sql_query)
    |
    v
validate_sql()
    |
    v
MySQL read-only connection
    |
    v
execute query and serialize rows
    |
    v
tool_result sent back to Claude
    |
    v
Claude final answer
    |
    v
CLI prints answer
```

## 2. Project Folder Structure

Important files and directories:

```text
CommerceIQ/
  AGENTS.md
  PRD.md
  README.md
  requirements.txt

  commerceiq/
    __init__.py
    query_database.py
    claude_app.py
    cli.py

  docs/
    DATABASE_SCHEMA.md
    TEST_REPORT.md
    PROJECT_EXPLAINED.md

  scripts/
    init_db.sql
    seed_data.py
    create_readonly_user.sql

  tests/
    test_seed_data.py
    test_query_database.py
    test_claude_app.py
    test_cli.py
    test_end_to_end.py
```

### `AGENTS.md`

Project-specific instructions for Codex. It says to follow `PRD.md`, use `docs/DATABASE_SCHEMA.md` as the database contract, expose exactly one Claude tool, avoid LangChain/MCP/RAG/web UI, and test ordinary functions without live API calls.

### `PRD.md`

The product requirements document. It defines the assignment goals, stack, data model, business rules, functional requirements, safety requirements, and acceptance criteria.

### `README.md`

Setup and usage instructions. It explains Python setup, database setup, seed loading, query tool usage, CLI commands, and demo questions.

### `requirements.txt`

Python dependencies:

```text
anthropic
mysql-connector-python
python-dotenv
pytest
sqlglot
```

### `commerceiq/query_database.py`

The database tool implementation. It validates SQL, connects to MySQL, executes the query, serializes results, and returns structured dictionaries.

### `commerceiq/claude_app.py`

The Claude integration. It defines the single Claude tool, builds the system prompt, stores conversation history, handles `tool_use` blocks, dispatches tool calls, and sends `tool_result` blocks back to Claude.

### `commerceiq/cli.py`

The interactive command-line interface. It reads user questions, calls `CommerceIQAssistant.ask()`, prints generated SQL, supports `/clear`, and exits on `exit` or `quit`.

### `scripts/init_db.sql`

Creates the `commerceiq` database and four tables.

### `scripts/seed_data.py`

Builds deterministic sample data and inserts it into MySQL. It refuses to overwrite existing rows unless `--reset` is passed.

### `scripts/create_readonly_user.sql`

Creates the dedicated read-only MySQL user and grants `SELECT` only on the four CommerceIQ tables.

### `docs/DATABASE_SCHEMA.md`

The schema contract given to Claude in the system prompt. It also documents the revenue rule.

### `tests/`

Automated tests for seed data, SQL validation, database tool behavior, Claude tool-calling, CLI behavior, and mocked end-to-end flows.

## 3. MySQL Database

The database name is:

```text
commerceiq
```

It contains exactly four application tables:

1. `customers`
2. `products`
3. `orders`
4. `order_items`

These are created in `scripts/init_db.sql`.

### `customers`

From `scripts/init_db.sql`:

```sql
CREATE TABLE IF NOT EXISTS customers (
  customer_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  city VARCHAR(80) NOT NULL,
  INDEX idx_customers_city (city)
) ENGINE=InnoDB;
```

Columns:

- `customer_id`: primary key. Unique identifier for each customer.
- `name`: customer name.
- `email`: unique email address.
- `city`: customer city.

The `idx_customers_city` index helps city-based filters.

### `products`

```sql
CREATE TABLE IF NOT EXISTS products (
  product_id INT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  category VARCHAR(80) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  stock_quantity INT NOT NULL,
  CONSTRAINT chk_products_price_positive CHECK (price > 0),
  CONSTRAINT chk_products_stock_nonnegative CHECK (stock_quantity >= 0),
  INDEX idx_products_category (category),
  INDEX idx_products_stock_quantity (stock_quantity)
) ENGINE=InnoDB;
```

Columns:

- `product_id`: primary key.
- `name`: product name.
- `category`: product category, such as Electronics or Office.
- `price`: current listed price.
- `stock_quantity`: current inventory count.

Important rule: `products.price` is the current listed price. It is not used for historical revenue.

### `orders`

```sql
CREATE TABLE IF NOT EXISTS orders (
  order_id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  order_date DATE NOT NULL,
  status ENUM('Completed', 'Pending', 'Cancelled') NOT NULL,
  CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  INDEX idx_orders_customer_id (customer_id),
  INDEX idx_orders_order_date (order_date),
  INDEX idx_orders_status (status)
) ENGINE=InnoDB;
```

Columns:

- `order_id`: primary key.
- `customer_id`: foreign key to `customers.customer_id`.
- `order_date`: date of the order.
- `status`: one of `Completed`, `Pending`, or `Cancelled`.

Relationship:

```text
customers.customer_id -> orders.customer_id
```

One customer can have many orders.

### `order_items`

```sql
CREATE TABLE IF NOT EXISTS order_items (
  order_item_id INT PRIMARY KEY,
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  CONSTRAINT fk_order_items_order
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_order_items_product
    FOREIGN KEY (product_id) REFERENCES products(product_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT chk_order_items_quantity_positive CHECK (quantity > 0),
  CONSTRAINT chk_order_items_unit_price_positive CHECK (unit_price > 0),
  INDEX idx_order_items_order_id (order_id),
  INDEX idx_order_items_product_id (product_id)
) ENGINE=InnoDB;
```

Columns:

- `order_item_id`: primary key.
- `order_id`: foreign key to `orders.order_id`.
- `product_id`: foreign key to `products.product_id`.
- `quantity`: number of units purchased.
- `unit_price`: historical purchase price at the time of the order.

Relationships:

```text
orders.order_id -> order_items.order_id
products.product_id -> order_items.product_id
```

One order can have many order items. One product can appear in many order items.

### Revenue rule

The project's revenue rule is:

```sql
SUM(order_items.quantity * order_items.unit_price)
```

but only for orders where:

```sql
orders.status = 'Completed'
```

Pending and cancelled orders do not count as realized revenue.

### How the database is initialized

In MySQL Workbench, connect with an account allowed to create the database and tables. Use **File > Open SQL Script** to open `scripts/init_db.sql`, then execute the script. PowerShell does not support the `mysql ... < scripts/init_db.sql` input-redirection command.

The script creates the database and tables if they do not already exist.

### How the database is seeded

The seed script is `scripts/seed_data.py`.

Important constants:

```python
RANDOM_SEED = 20261009
DATABASE_NAME = "commerceiq"
EXPECTED_COUNTS = {
    "customers": 50,
    "products": 30,
    "orders": 200,
    "order_items": 400,
}
```

The fixed `RANDOM_SEED` makes the data deterministic. That means the same dataset is generated every time.

Dry run:

```powershell
python scripts/seed_data.py --dry-run
```

Load data:

```powershell
python scripts/seed_data.py
```

Reload intentionally:

```powershell
python scripts/seed_data.py --reset
```

The script protects existing data using `ensure_empty_or_reset()`. If tables already contain rows and `--reset` is not used, it raises an error instead of overwriting data.

### Purpose of the read-only MySQL user

The file `scripts/create_readonly_user.sql` contains:

```sql
CREATE USER IF NOT EXISTS 'commerceiq_readonly'@'localhost'
  IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';

GRANT SELECT ON commerceiq.customers TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.products TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.orders TO 'commerceiq_readonly'@'localhost';
GRANT SELECT ON commerceiq.order_items TO 'commerceiq_readonly'@'localhost';
```

This user should be configured in `.env` for the application at runtime. `create_connection()` reads the configured username; it does not itself check that the account is read-only. The `SELECT` grants in this script are the intended database permission boundary.

Why it matters:

- Even if Claude generates dangerous SQL, the database account should not have permission to write.
- It supports defense in depth: database permissions plus Python SQL validation.
- It lets you tell your instructor that safety is enforced both in code and at the database level.

## 4. The `query_database` Tool: Very Detailed

File:

```text
commerceiq/query_database.py
```

This is the only database tool that Claude can use indirectly.

Actual function:

```python
def query_database(sql_query: str) -> dict[str, Any]:
    """Validate and execute one safe read-only query against CommerceIQ."""
    validation = validate_sql(sql_query)
    if not validation.is_valid:
        return error_result("invalid_sql", validation.error or "SQL query is not allowed.")

    try:
        connection = create_connection()
    except Exception:
        return error_result("connection_failed", "Could not connect to the CommerceIQ database.")

    try:
        return execute_validated_query(connection, sql_query)
    except MySQLError as exc:
        return error_result("database_error", safe_database_message(exc))
    except Exception:
        return error_result("execution_error", "Query execution failed.")
    finally:
        try:
            connection.close()
        except Exception:
            pass
```

### Input

The function accepts one argument:

```python
sql_query: str
```

Example:

```python
query_database("SELECT name, price FROM products LIMIT 5")
```

### Output

It returns a Python dictionary that can be converted to JSON.

Successful result shape:

```python
{
    "columns": ["name", "price"],
    "rows": [{"name": "Wireless Mouse", "price": "24.99"}],
    "row_count": 1,
    "truncated": False,
    "error": None,
}
```

Error result shape:

```python
{
    "columns": [],
    "rows": [],
    "row_count": 0,
    "truncated": False,
    "error": {
        "code": "invalid_sql",
        "message": "Only read-only SELECT queries are allowed.",
    },
}
```

### Step-by-step explanation

```python
validation = validate_sql(sql_query)
```

This applies the implemented SQL checks before connecting to MySQL. It does not prove that every accepted `SELECT` is free of side effects.

```python
if not validation.is_valid:
    return error_result("invalid_sql", validation.error or "SQL query is not allowed.")
```

If validation fails, the function immediately returns a structured error. It does not connect to the database.

```python
try:
    connection = create_connection()
except Exception:
    return error_result("connection_failed", "Could not connect to the CommerceIQ database.")
```

This tries to connect using the read-only DB credentials from environment variables. If the connection fails, the function returns a safe error message.

```python
try:
    return execute_validated_query(connection, sql_query)
```

Once SQL is validated and the DB connection exists, this executes the query and returns rows.

```python
except MySQLError as exc:
    return error_result("database_error", safe_database_message(exc))
```

If MySQL rejects the query, the tool returns a database error without exposing stack traces or secrets.

```python
except Exception:
    return error_result("execution_error", "Query execution failed.")
```

Any other unexpected error becomes a generic safe error.

```python
finally:
    try:
        connection.close()
    except Exception:
        pass
```

The database connection is closed even if execution fails.

### Why this is the only tool exposed to Claude

The PRD requires exactly one Claude-exposed tool:

```text
query_database(sql_query: str)
```

This design keeps the application small and limits Claude's available actions:

- Claude cannot call file tools.
- Claude cannot call write tools.
- With the dedicated `SELECT`-only MySQL account configured, Claude cannot use this tool to create users, change schema, or update stored data.
- Every database request passes through one validation and execution path.

## 5. All Helper Functions: Very Detailed

This section covers helper functions in `commerceiq/query_database.py`.

### Constants

```python
ALLOWED_SCHEMA = "commerceiq"
ALLOWED_TABLES = {"customers", "products", "orders", "order_items"}
MAX_ROWS = 100
MAX_SERIALIZED_BYTES = 100_000
QUERY_TIMEOUT_MS = 5_000

COMMENT_PATTERNS = ("--", "#", "/*", "*/")
DISALLOWED_PATTERNS = (
    r"\bINTO\s+(OUTFILE|DUMPFILE)\b",
    r"\bFOR\s+UPDATE\b",
    r"\bLOCK\s+IN\s+SHARE\s+MODE\b",
    r"\bPROCEDURE\s+ANALYSE\b",
)
```

Explanation:

- `ALLOWED_SCHEMA` rejects table references explicitly qualified with a different schema. For unqualified table names, the connected default database comes from `COMMERCEIQ_DB_NAME`, which should be `commerceiq`.
- `ALLOWED_TABLES` restricts table names to the four listed names.
- `MAX_ROWS` limits the number of rows returned to Claude.
- `MAX_SERIALIZED_BYTES` checks the serialized result; if it is too large, the helper drops the rows and returns an error. The response still retains column names, so this is not an absolute byte limit on every possible response.
- `QUERY_TIMEOUT_MS` is the requested MySQL execution-time setting. It is best effort because the code ignores a MySQL error while setting it.
- `COMMENT_PATTERNS` blocks SQL comments.
- `DISALLOWED_PATTERNS` blocks the listed forms, including `INTO OUTFILE`, `FOR UPDATE`, and `LOCK IN SHARE MODE`. It does not block every risky `SELECT` form.

### `ValidationResult`

```python
@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    error: str | None = None
```

This small dataclass represents the result of SQL validation.

Fields:

- `is_valid`: `True` if SQL is allowed.
- `error`: error message if SQL is rejected.

`frozen=True` means instances cannot be changed after creation.

### `validate_sql(sql_query: str) -> ValidationResult`

Actual code:

```python
def validate_sql(sql_query: str) -> ValidationResult:
    if not isinstance(sql_query, str) or not sql_query.strip():
        return ValidationResult(False, "sql_query must be a non-empty string.")

    query = sql_query.strip()
    upper_query = query.upper()
    if any(marker in query for marker in COMMENT_PATTERNS):
        return ValidationResult(False, "SQL comments are not allowed.")

    for pattern in DISALLOWED_PATTERNS:
        if re.search(pattern, upper_query):
            return ValidationResult(False, "This SELECT form is not allowed.")

    try:
        parsed_statements = sqlglot.parse(query, read="mysql")
    except sqlglot.errors.ParseError:
        return ValidationResult(False, "SQL could not be parsed.")

    if len(parsed_statements) != 1:
        return ValidationResult(False, "Exactly one SQL statement is allowed.")

    statement = parsed_statements[0]
    if not isinstance(statement, exp.Select):
        return ValidationResult(False, "Only read-only SELECT queries are allowed.")

    if list(statement.find_all(exp.Command)):
        return ValidationResult(False, "Administrative SQL commands are not allowed.")

    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()
        database_name = table.db.lower() if table.db else None
        if database_name and database_name != ALLOWED_SCHEMA:
            return ValidationResult(False, "Queries may only access the commerceiq schema.")
        if table_name not in ALLOWED_TABLES:
            return ValidationResult(False, f"Table '{table.name}' is not allowlisted.")

    if not list(statement.find_all(exp.Table)):
        return ValidationResult(False, "Query must read from an allowlisted CommerceIQ table.")

    return ValidationResult(True)
```

Parameter:

- `sql_query`: the SQL string Claude requested.

Return value:

- A `ValidationResult`.

Important steps:

1. It checks that the input is a non-empty string.
2. It strips whitespace.
3. It rejects SQL comments such as `--`, `#`, and `/* */`.
4. It rejects dangerous SELECT variants using `DISALLOWED_PATTERNS`.
5. It parses the SQL with `sqlglot.parse(query, read="mysql")`.
6. It requires exactly one SQL statement.
7. It requires the parsed statement to be a `SELECT`.
8. It rejects administrative commands.
9. It checks every table reference.
10. It requires at least one allowlisted table.

Why it matters:

This is the main application-level SQL check. It rejects many unsafe requests before connecting, but it currently accepts `SELECT name FROM products FOR SHARE` (a locking read) and `SELECT @x := name FROM products` (a session-variable assignment). Neither `FOR SHARE` nor that assignment is covered by the listed patterns or a separate AST check. Do not describe the validator as blocking every side-effect-capable `SELECT`. The configured read-only MySQL permissions remain important, but they do not make the validator's coverage complete.

### `create_connection() -> mysql.connector.MySQLConnection`

Actual code:

```python
def create_connection() -> mysql.connector.MySQLConnection:
    load_dotenv()
    return mysql.connector.connect(
        host=os.getenv("COMMERCEIQ_DB_HOST", "localhost"),
        port=int(os.getenv("COMMERCEIQ_DB_PORT", "3306")),
        user=required_env("COMMERCEIQ_DB_USER"),
        password=required_env("COMMERCEIQ_DB_PASSWORD"),
        database=os.getenv("COMMERCEIQ_DB_NAME", ALLOWED_SCHEMA),
        connection_timeout=5,
    )
```

Parameters:

- None.

Return value:

- A MySQL connection object.

Important steps:

- `load_dotenv()` loads values from `.env`.
- Host defaults to `localhost`.
- Port defaults to `3306`.
- User and password are required.
- Database defaults to `commerceiq`.
- `connection_timeout=5` prevents hanging too long during connection.

Set `COMMERCEIQ_DB_NAME=commerceiq` when configuring `.env`. The code does not reject a different default database name, and unqualified SQL table names resolve against that connection setting.

This function uses the configured runtime DB credentials:

```text
COMMERCEIQ_DB_USER
COMMERCEIQ_DB_PASSWORD
```

To use the dedicated read-only account, set `COMMERCEIQ_DB_USER` to `commerceiq_readonly` and its password in `.env`. The function does not verify the account's grants.

### `required_env(name: str) -> str`

Actual code:

```python
def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
```

Parameter:

- `name`: environment variable name.

Return value:

- The environment variable value.

If the variable is missing, it raises `RuntimeError`.

This is used so the app does not silently connect with an empty user or password.

### `execute_validated_query(connection: Any, sql_query: str) -> dict[str, Any]`

Actual code:

```python
def execute_validated_query(connection: Any, sql_query: str) -> dict[str, Any]:
    cursor = connection.cursor()
    try:
        set_query_timeout(cursor)
        cursor.execute(sql_query)
        columns = [column[0] for column in (cursor.description or [])]
        raw_rows = cursor.fetchmany(MAX_ROWS + 1)
        truncated = len(raw_rows) > MAX_ROWS
        rows = [serialize_row(columns, row) for row in raw_rows[:MAX_ROWS]]
        result = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "error": None,
        }
        return cap_serialized_result(result)
    finally:
        cursor.close()
```

Parameters:

- `connection`: an open MySQL connection.
- `sql_query`: already validated SQL.

Return value:

- A structured result dictionary.

Important steps:

```python
cursor = connection.cursor()
```

Creates a cursor. A cursor is the object used to send SQL to MySQL.

```python
set_query_timeout(cursor)
```

Requests a session query timeout; the request may fail without stopping query execution.

```python
cursor.execute(sql_query)
```

Runs the SQL.

```python
columns = [column[0] for column in (cursor.description or [])]
```

Extracts column names returned by MySQL.

```python
raw_rows = cursor.fetchmany(MAX_ROWS + 1)
```

Fetches one more row than the maximum. This lets the code know whether the result was truncated.

```python
truncated = len(raw_rows) > MAX_ROWS
```

If more than 100 rows came back, the result is marked as truncated.

```python
rows = [serialize_row(columns, row) for row in raw_rows[:MAX_ROWS]]
```

Converts row tuples into dictionaries.

```python
return cap_serialized_result(result)
```

Checks the JSON size cap before returning.

```python
finally:
    cursor.close()
```

Always closes the cursor.

### `set_query_timeout(cursor: Any) -> None`

Actual code:

```python
def set_query_timeout(cursor: Any) -> None:
    try:
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (QUERY_TIMEOUT_MS,))
    except MySQLError:
        # Some MySQL-compatible environments may not allow this session setting.
        # Continue with read-only DB permissions and result caps as the hard boundary.
        pass
```

Parameter:

- `cursor`: MySQL cursor.

Return value:

- `None`.

This tries to set a 5,000 ms MySQL session execution timeout. If MySQL rejects the setting, the function ignores that error and continues. The timeout is therefore best effort, not guaranteed. The 100-row fetch cap and serialized-result check limit returned data; they do not limit how long MySQL may spend executing a query. The dedicated read-only account limits database permissions, not query duration.

### `serialize_row(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]`

Actual code:

```python
def serialize_row(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        column: serialize_value(value)
        for column, value in zip(columns, row, strict=True)
    }
```

Parameters:

- `columns`: list of column names.
- `row`: tuple of row values.

Return value:

- Dictionary mapping column names to JSON-safe values.

Example:

```python
columns = ["name", "price"]
row = ("Wireless Mouse", Decimal("24.99"))
```

Output:

```python
{"name": "Wireless Mouse", "price": "24.99"}
```

`zip(columns, row, strict=True)` ensures the number of columns and values match.

Because a dictionary can contain each key only once, duplicate SQL column names can lose data: if two selected columns are both named `customer_id`, the later value overwrites the earlier one. Use distinct `AS` aliases when inspecting a join that selects same-named columns.

### `serialize_value(value: Any) -> Any`

Actual code:

```python
def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value
```

Parameter:

- `value`: a value returned by MySQL.

Return value:

- A JSON-friendly value for the explicitly handled `Decimal`, `datetime`, and `date` types, or the original value for any other type.

Why it exists:

Python's `json.dumps()` cannot directly serialize all MySQL/Python types. For example:

- `Decimal("24.99")`
- `date(2026, 5, 1)`
- `datetime(2026, 5, 1, 9, 30)`

This helper converts:

- `Decimal` to string.
- `datetime` to string like `2026-05-01 09:30:00`.
- `date` to string like `2026-05-01`.

### `cap_serialized_result(result: dict[str, Any]) -> dict[str, Any]`

Actual code:

```python
def cap_serialized_result(result: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(result, default=str)
    if len(encoded.encode("utf-8")) <= MAX_SERIALIZED_BYTES:
        return result

    capped = dict(result)
    capped["rows"] = []
    capped["row_count"] = 0
    capped["truncated"] = True
    capped["error"] = {
        "code": "result_too_large",
        "message": "Query result exceeded the serialized output size cap.",
    }
    return capped
```

Parameter:

- `result`: the result dictionary.

Return value:

- Original result if small enough, or a capped error result if too large.

Important steps:

- Converts the result to JSON text.
- Measures UTF-8 byte size.
- If the result is too large, it removes rows and returns a `result_too_large` error.

This usually prevents large row payloads from being sent to Claude. It drops rows when the candidate JSON exceeds the cap, but it keeps the `columns` list in the error result; the function does not recheck the size of that error result.

### `error_result(code: str, message: str) -> dict[str, Any]`

Actual code:

```python
def error_result(code: str, message: str) -> dict[str, Any]:
    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
```

Parameters:

- `code`: short machine-readable error code.
- `message`: human-readable explanation.

Return value:

- Standard error result dictionary.

This keeps error responses consistent.

### `safe_database_message(exc: MySQLError) -> str`

Actual code:

```python
def safe_database_message(exc: MySQLError) -> str:
    error_number = getattr(exc, "errno", None)
    if error_number:
        return f"Database rejected the query. MySQL error code: {error_number}."
    return "Database rejected the query."
```

Parameter:

- `exc`: MySQL exception.

Return value:

- Safe error message.

This intentionally does not return raw stack traces, connection strings, or secrets.

## 6. Claude API Integration

File:

```text
commerceiq/claude_app.py
```

### Anthropic SDK initialization

In `CommerceIQAssistant.__init__()`:

```python
load_dotenv()
self.client = client if client is not None else anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
self.system_prompt = system_prompt or build_system_prompt()
self.query_tool = query_tool
self.messages: list[dict[str, Any]] = []
```

Explanation:

- `load_dotenv()` loads `.env`.
- If tests pass a fake client, it uses that fake client.
- Otherwise it creates a real `anthropic.Anthropic` client.
- The API key comes from `ANTHROPIC_API_KEY`.
- The model comes from `ANTHROPIC_MODEL`, defaulting to `claude-sonnet-4-5`.
- `self.messages` stores conversation history in memory.

### Exact code that registers the tool

The tool definition:

```python
QUERY_DATABASE_TOOL = {
    "name": "query_database",
    "description": (
        "Execute one validated, read-only MySQL SELECT query against the CommerceIQ "
        "e-commerce sample database. Use this for factual questions that require "
        "database rows or aggregations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql_query": {
                "type": "string",
                "description": "A single read-only MySQL SELECT query over the allowlisted CommerceIQ tables.",
            }
        },
        "required": ["sql_query"],
        "additionalProperties": False,
    },
}

CLAUDE_TOOLS = [QUERY_DATABASE_TOOL]
```

Only one tool is placed in `CLAUDE_TOOLS`.

When calling Claude:

```python
response = self.client.messages.create(
    model=self.model,
    max_tokens=MAX_TOKENS,
    system=self.system_prompt,
    messages=list(self.messages),
    tools=CLAUDE_TOOLS,
)
```

The important part is:

```python
tools=CLAUDE_TOOLS
```

Since `CLAUDE_TOOLS` contains one tool, Claude can only call `query_database`.

### Tool JSON schema

This section:

```python
"input_schema": {
    "type": "object",
    "properties": {
        "sql_query": {
            "type": "string",
            "description": "A single read-only MySQL SELECT query over the allowlisted CommerceIQ tables.",
        }
    },
    "required": ["sql_query"],
    "additionalProperties": False,
}
```

Means Claude must provide input like:

```json
{
  "sql_query": "SELECT name, price FROM products LIMIT 5"
}
```

`additionalProperties: False` tells Claude the expected input shape. The Python dispatcher checks that `sql_query` is a string, but it does not separately reject extra keys in a returned input dictionary.

### System prompt and schema context

Schema loading:

```python
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "DATABASE_SCHEMA.md"

def load_schema_context() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")
```

Prompt construction:

```python
def build_system_prompt(schema_context: str | None = None) -> str:
    schema = schema_context if schema_context is not None else load_schema_context()
    return f"""You are CommerceIQ, a concise data assistant for a fixed MySQL e-commerce database.

Use the query_database tool when a user asks for facts, counts, lists, joins, filters, rankings, date ranges, or aggregations from the database.
Use only the documented schema and business rules below. Do not invent columns or tables.

Important SQL rules:
- Generate MySQL SELECT queries only.
- Query only the commerceiq schema and these tables: customers, products, orders, order_items.
- Revenue is SUM(order_items.quantity * order_items.unit_price) for orders where status = 'Completed'.
- Current products.price is not historical revenue.
- Quantity sold should use Completed orders by default unless the user explicitly asks for another status.
- If the user asks for profit, margin, cost, or unavailable data, say the schema does not store it.
- Prefer clear column aliases for aggregates.
- Keep result sets small. Use LIMIT for lists.
- Base final answers on tool results, and say when results are empty or incomplete.

Database schema and conventions:
{schema}
"""
```

Claude learns the schema because the contents of `docs/DATABASE_SCHEMA.md` are inserted into the system prompt.

### `tool_use` and `tool_result`

Claude can return a content block like:

```python
{
    "type": "tool_use",
    "id": "toolu_1",
    "name": "query_database",
    "input": {"sql_query": "SELECT name FROM products LIMIT 5"},
}
```

Python must respond with a matching `tool_result`:

```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_1",
    "content": "... JSON result ...",
    "is_error": False,
}
```

The `tool_use_id` must match Claude's tool use id.

The actual function that builds this is:

```python
def build_tool_result(tool_use_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, ensure_ascii=True),
        "is_error": bool(result.get("error")),
    }
```

### Complete tool-calling loop

The main loop is inside `CommerceIQAssistant.ask()`:

```python
for _ in range(MAX_TOOL_ITERATIONS):
    response = self.client.messages.create(
        model=self.model,
        max_tokens=MAX_TOKENS,
        system=self.system_prompt,
        messages=list(self.messages),
        tools=CLAUDE_TOOLS,
    )
    assistant_content = normalize_content(response.content)
    self.messages.append({"role": "assistant", "content": assistant_content})

    tool_uses = [block for block in assistant_content if block.get("type") == "tool_use"]
    if not tool_uses:
        return AssistantReply(answer=extract_text(assistant_content), tool_calls=tool_logs)

    tool_results = []
    for tool_use in tool_uses:
        tool_result, log = self.dispatch_tool_use(tool_use)
        tool_logs.append(log)
        if on_tool_call is not None and log.sql_query:
            on_tool_call(log.sql_query)
        tool_results.append(tool_result)

    self.messages.append({"role": "user", "content": tool_results})
```

Step by step:

1. Send conversation history and tools to Claude.
2. Normalize Claude's response content into dictionaries.
3. Store Claude's assistant message in history.
4. Look for `tool_use` blocks.
5. If there are no tool calls, return Claude's final text.
6. If there are tool calls, dispatch each one.
7. Store all `tool_result` blocks as the next user message.
8. Loop again so Claude can see the tool results and write a final answer.

The loop limit is:

```python
MAX_TOOL_ITERATIONS = 5
```

This prevents infinite tool loops.

If the Claude API raises an exception, `ask()` returns an error reply. It does not roll back messages already appended to `self.messages`; the current user question can therefore remain in history even though that API request failed. A later question may include it unless `/clear` is used.

### Tool dispatch

Actual dispatch code:

```python
def dispatch_tool_use(self, tool_use: dict[str, Any]) -> tuple[dict[str, Any], ToolCallLog]:
    tool_use_id = str(tool_use.get("id", "unknown_tool_use"))
    tool_name = str(tool_use.get("name", ""))
    tool_input = tool_use.get("input", {})

    if tool_name != "query_database":
        result = tool_error("unknown_tool", f"Tool '{tool_name}' is not available.")
        return build_tool_result(tool_use_id, result), ToolCallLog(
            tool_use_id=tool_use_id,
            name=tool_name,
            sql_query="",
            result_summary="Rejected unknown tool.",
            error=result["error"],
        )

    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("sql_query"), str):
        result = tool_error("invalid_tool_input", "query_database requires a string sql_query.")
        return build_tool_result(tool_use_id, result), ToolCallLog(
            tool_use_id=tool_use_id,
            name=tool_name,
            sql_query="",
            result_summary="Rejected invalid tool input.",
            error=result["error"],
        )

    sql_query = tool_input["sql_query"]
    result = self.query_tool(sql_query)
    error = result.get("error") if isinstance(result, dict) else None
    summary = summarize_tool_result(result)
    return build_tool_result(tool_use_id, result), ToolCallLog(
        tool_use_id=tool_use_id,
        name=tool_name,
        sql_query=sql_query,
        result_summary=summary,
        error=error,
    )
```

Key point:

```python
if tool_name != "query_database":
```

Even if Claude somehow asks for another tool name, Python rejects it.

## 7. Multi-Turn Conversations and Conversation History: Very Detailed

This is handled in:

```text
commerceiq/claude_app.py
CommerceIQAssistant
```

### Exact variable responsible for history

In `CommerceIQAssistant.__init__()`:

```python
self.messages: list[dict[str, Any]] = []
```

This is the conversation history.

It is stored in memory only.

It is not stored in:

- a file
- MySQL
- a vector database
- browser storage

When the Python process exits, the history is gone.

### How a user message is appended

In `ask()`:

```python
self.messages.append({"role": "user", "content": user_question})
```

If the user asks:

```text
How many customers are in Seattle?
```

The list becomes:

```python
[
    {"role": "user", "content": "How many customers are in Seattle?"}
]
```

### How previous messages are sent to Claude

In the Claude API call:

```python
messages=list(self.messages)
```

The `list(...)` creates a snapshot of the current history before the API call.

It is a shallow copy of the list, so the stored message dictionaries are not copied separately.

This means every new API call receives previous user messages, assistant messages, and tool result messages.

### How assistant messages are stored

After Claude responds:

```python
assistant_content = normalize_content(response.content)
self.messages.append({"role": "assistant", "content": assistant_content})
```

If Claude returns a final text answer, the stored message might look like:

```python
{
    "role": "assistant",
    "content": [
        {"type": "text", "text": "There are 5 customers in Seattle."}
    ],
}
```

If Claude returns a tool call, the stored message might look like:

```python
{
    "role": "assistant",
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "query_database",
            "input": {
                "sql_query": "SELECT COUNT(*) AS customer_count FROM customers WHERE city = 'Seattle'"
            },
        }
    ],
}
```

### How tool results are preserved

After Python executes the tool:

```python
self.messages.append({"role": "user", "content": tool_results})
```

This stores the tool result as a user-role message because that is the message ordering expected by the Messages API.

Example:

```python
{
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": "{\"columns\": [\"customer_count\"], \"rows\": [{\"customer_count\": 5}], ...}",
            "is_error": False,
        }
    ],
}
```

### How follow-up questions use previous context

Suppose the first user question is:

```text
What is the top category by completed revenue?
```

Claude might answer:

```text
Electronics is the top category by completed revenue.
```

Then the user asks:

```text
Show me products in that category.
```

The second question depends on the phrase "that category." Claude understands it because the previous question, SQL, tool result, and final answer are still in `self.messages`.

### How `/clear` resets history

In `CommerceIQAssistant`:

```python
def clear(self) -> None:
    self.messages.clear()
```

In `commerceiq/cli.py`:

```python
if question == "/clear":
    assistant.clear()
    print("Conversation history cleared.")
    continue
```

So `/clear` calls `assistant.clear()`, which empties the in-memory list.

After that, the next question starts a fresh conversation.

If an API call fails, `ask()` does not automatically remove the question it appended before calling Claude. `/clear` also removes that failed turn when a fresh context is needed.

### Walkthrough: two consecutive user questions

Initial state:

```python
self.messages = []
```

#### First question

User enters:

```text
What is the top category by completed revenue?
```

After appending the user message:

```python
[
    {
        "role": "user",
        "content": "What is the top category by completed revenue?"
    }
]
```

Claude returns a tool call. After storing assistant content:

```python
[
    {"role": "user", "content": "What is the top category by completed revenue?"},
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "query_database",
                "input": {
                    "sql_query": "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue FROM products p JOIN order_items oi ON oi.product_id = p.product_id JOIN orders o ON o.order_id = oi.order_id WHERE o.status = 'Completed' GROUP BY p.category ORDER BY revenue DESC LIMIT 5"
                },
            }
        ],
    },
]
```

Python runs the tool and stores a tool result:

```python
[
    {"role": "user", "content": "What is the top category by completed revenue?"},
    {"role": "assistant", "content": [{"type": "tool_use", "...": "..."}]},
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": "{\"columns\": [\"category\", \"revenue\"], ...}",
                "is_error": False,
            }
        ],
    },
]
```

Claude then writes the final answer, and it is also stored:

```python
[
    {"role": "user", "content": "What is the top category by completed revenue?"},
    {"role": "assistant", "content": [{"type": "tool_use", "...": "..."}]},
    {"role": "user", "content": [{"type": "tool_result", "...": "..."}]},
    {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "The top category is Electronics."}
        ],
    },
]
```

#### Second question

User enters:

```text
Show me products in that category.
```

Now the history includes the entire first exchange plus the new user question:

```python
self.messages.append({"role": "user", "content": "Show me products in that category."})
```

Claude receives the full list and can understand that "that category" refers to the category from the previous answer.

### Summary of history behavior

- History is stored in `self.messages`.
- History is in memory only.
- User messages, assistant text, assistant tool calls, and tool results are all stored.
- `/clear` empties the list.
- Follow-up questions work because previous messages are sent to Claude each time.
- A failed API request can leave its user message in history until `/clear` or the process exits.

## 8. Interactive CLI

File:

```text
commerceiq/cli.py
```

### How the CLI starts

The module ends with:

```python
if __name__ == "__main__":
    main()
```

Run it with:

```powershell
python -m commerceiq.cli
```

### Argument parsing

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask Claude questions about the CommerceIQ MySQL database.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Display generated SQL and summarized tool results.",
    )
    return parser.parse_args()
```

The only CLI option is:

```text
--debug
```

### Creating the assistant

```python
args = parse_args()
assistant = CommerceIQAssistant()
```

This creates the Claude integration object.

### Reading input

```python
question = input("\n> ").strip()
```

The CLI reads one line from the user.

### Exit commands

```python
if question.lower() in {"exit", "quit"}:
    print("Goodbye.")
    break
```

Typing `exit` or `quit` stops the loop.

### `/clear`

```python
if question == "/clear":
    assistant.clear()
    print("Conversation history cleared.")
    continue
```

This resets conversation history.

### SQL display

```python
def show_sql(sql_query: str) -> None:
    print("\nGenerated SQL:")
    print(sql_query)

reply = assistant.ask(question, on_tool_call=show_sql)
```

`show_sql` is passed as a callback. Whenever Claude calls `query_database`, the SQL is printed.

This is useful in the demo because your instructor can see the SQL and reproduce it in MySQL Workbench.

### Debug mode

```python
if args.debug and reply.tool_calls:
    print("\nTool results:")
    for index, tool_call in enumerate(reply.tool_calls, start=1):
        print(f"{index}. {tool_call.result_summary}")
```

Debug mode prints summaries like:

```text
1. rows=5, truncated=False
```

These are summaries, not the actual result rows. When Claude supplies a SQL query, the CLI prints it through `show_sql`; `--debug` adds the summaries and error details. It does not intentionally print credentials. To inspect row values independently, run the displayed SQL in MySQL Workbench.

## 9. Complete End-to-End Example

Question:

```text
What are the top 5 products by completed-order revenue?
```

### 1. User enters the question

In the CLI:

```python
question = input("\n> ").strip()
```

The variable `question` becomes:

```python
"What are the top 5 products by completed-order revenue?"
```

### 2. CLI sends it to the assistant

```python
reply = assistant.ask(question, on_tool_call=show_sql)
```

The CLI passes the user question and a SQL display callback.

### 3. Claude receives system prompt, schema, and history

In `CommerceIQAssistant.ask()`:

```python
self.messages.append({"role": "user", "content": user_question})
```

Then:

```python
response = self.client.messages.create(
    model=self.model,
    max_tokens=MAX_TOKENS,
    system=self.system_prompt,
    messages=list(self.messages),
    tools=CLAUDE_TOOLS,
)
```

Claude receives:

- system prompt
- database schema from `docs/DATABASE_SCHEMA.md`
- conversation history
- the single tool definition

### 4. Claude generates SQL and requests the tool

Claude might produce a `tool_use` similar to:

```python
{
    "type": "tool_use",
    "id": "toolu_1",
    "name": "query_database",
    "input": {
        "sql_query": (
            "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue "
            "FROM products p "
            "JOIN order_items oi ON oi.product_id = p.product_id "
            "JOIN orders o ON o.order_id = oi.order_id "
            "WHERE o.status = 'Completed' "
            "GROUP BY p.product_id, p.name "
            "ORDER BY revenue DESC "
            "LIMIT 5"
        )
    },
}
```

Important details:

- It uses `unit_price`, not `products.price`.
- It includes `o.status = 'Completed'`.
- It uses joins across `products`, `order_items`, and `orders`.
- It limits output to 5 rows.

### 5. Python validates and executes the query

In `dispatch_tool_use()`:

```python
sql_query = tool_input["sql_query"]
result = self.query_tool(sql_query)
```

By default:

```python
self.query_tool = query_database
```

So Python calls:

```python
query_database(sql_query)
```

Inside `query_database()`:

```python
validation = validate_sql(sql_query)
```

Then:

```python
connection = create_connection()
```

Then:

```python
return execute_validated_query(connection, sql_query)
```

### 6. MySQL returns results

`execute_validated_query()` runs:

```python
cursor.execute(sql_query)
columns = [column[0] for column in (cursor.description or [])]
raw_rows = cursor.fetchmany(MAX_ROWS + 1)
rows = [serialize_row(columns, row) for row in raw_rows[:MAX_ROWS]]
```

The result is shaped like:

```python
{
    "columns": ["name", "revenue"],
    "rows": [
        {"name": "Example Product", "revenue": "1234.56"}
    ],
    "row_count": 1,
    "truncated": False,
    "error": None,
}
```

This is an illustrative one-row excerpt, so `row_count` is 1. A real top-five result can contain up to five rows, depending on the database response.

### 7. Tool response is sent back to Claude

`build_tool_result()` creates:

```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_1",
    "content": json.dumps(result, ensure_ascii=True),
    "is_error": False,
}
```

Then this is appended:

```python
self.messages.append({"role": "user", "content": tool_results})
```

### 8. Claude generates the final answer

The loop calls Claude again. This time Claude sees the tool result and writes a final text answer.

If no more tool calls exist:

```python
return AssistantReply(answer=extract_text(assistant_content), tool_calls=tool_logs)
```

### 9. Conversation history is updated

The final assistant message is already appended here:

```python
self.messages.append({"role": "assistant", "content": assistant_content})
```

So the conversation history now contains:

1. User question.
2. Assistant tool use.
3. User tool result.
4. Assistant final answer.

This makes future follow-up questions possible.

## 10. Testing

The project uses `pytest`.

Run:

```powershell
python -m pytest
```

### `tests/test_seed_data.py`

Covers:

- Expected row counts.
- Deterministic seed generation.
- Relationship validity.
- Completed-only revenue calculation.

Example:

```python
def test_completed_revenue_uses_only_completed_orders() -> None:
    dataset = build_dataset()
    completed_order_ids = {
        order["order_id"]
        for order in dataset.orders
        if order["status"] == "Completed"
    }
    expected = sum(
        Decimal(item["quantity"]) * Decimal(item["unit_price"])
        for item in dataset.order_items
        if item["order_id"] in completed_order_ids
    ).quantize(Decimal("0.01"))

    assert completed_revenue(dataset) == expected
```

### `tests/test_query_database.py`

Covers:

- SQL rejection cases.
- Successful structured result.
- Row caps.
- Invalid SQL without connecting.
- Connection failure.
- Database error.
- Serialization of `Decimal`, `date`, and `datetime`.

It uses fake connection and cursor classes so tests do not need a real database.

### `tests/test_claude_app.py`

Covers:

- Exactly one tool is registered.
- Tool loop sends `tool_result` then receives final answer.
- Multiple same-tool calls in one response.
- Conversation history.
- `clear()`.
- Invalid tool input.
- API errors.

It uses fake Claude clients and fake responses.

### `tests/test_cli.py`

Covers:

- CLI prints generated SQL.
- `/clear` calls `assistant.clear()`.
- Questions are passed to the assistant.

### `tests/test_end_to_end.py`

Covers mocked end-to-end flows:

- Simple retrieval, filtering, sorting, and limit.
- Join query.
- Aggregates.
- Revenue rule.
- Multiple tool calls.
- Multi-turn follow-up.
- Tool errors.
- Single-tool exposure.

The tests compute expected values from `scripts.seed_data.build_dataset()`. The mocked query tool maps known SQL strings to Python calculations; it does not send those SQL strings to MySQL. Fake Claude responses also supply the tool calls and final text, so these tests verify message flow and expected sample values, not Claude's live SQL choices.

### Mocked Claude API calls

The tests do not call the real Claude API. They use fake classes like:

```python
class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.messages = FakeMessages(responses)
```

This makes tests:

- deterministic
- free to run
- independent of internet/API availability

### Unit testing versus live end-to-end testing

Unit and mocked tests:

- Run with `pytest`.
- Do not require Claude API calls.
- Do not require a live MySQL database for any of the current automated checks.
- Verify code logic.

Passing these tests does not prove that the example SQL returns those values in MySQL or that Claude will choose the same SQL in a live conversation.

Live end-to-end testing:

- Requires MySQL running.
- Requires seeded tables.
- Requires `.env` credentials.
- Requires `ANTHROPIC_API_KEY`.
- Verifies the real user experience through the CLI when performed manually. The pytest suite does not run this live path; any manual Claude call is separate from the automated test result.

## 11. Important Programming Concepts

### Python functions and modules

Files like `commerceiq/query_database.py` are modules. Functions like `query_database()` and `validate_sql()` group related behavior.

### Dictionaries and lists

The project uses dictionaries for structured data:

```python
{"role": "user", "content": user_question}
```

Lists store sequences:

```python
self.messages: list[dict[str, Any]] = []
```

### JSON

Tool results are converted to JSON before being sent back to Claude:

```python
json.dumps(result, ensure_ascii=True)
```

JSON is useful because tool results need a portable structured format.

### Environment variables

Secrets and configuration come from `.env` and environment variables:

```python
os.getenv("ANTHROPIC_API_KEY")
required_env("COMMERCEIQ_DB_USER")
required_env("COMMERCEIQ_DB_PASSWORD")
```

This avoids hardcoding credentials in source code.

### API requests and responses

The Claude API call is:

```python
self.client.messages.create(...)
```

The response contains content blocks, which may be text or tool calls.

### Tool calling

Tool calling means Claude asks the application to run a function. In this project, that function is only:

```python
query_database(sql_query: str)
```

### SQL

SQL is the language used to query MySQL. Claude generates SQL, but Python validates and executes it.

### Exception handling

The project uses `try`/`except` to handle failures:

```python
try:
    connection = create_connection()
except Exception:
    return error_result("connection_failed", "Could not connect to the CommerceIQ database.")
```

This prevents raw exceptions from reaching the user.

### Conversation state

Conversation state is stored in:

```python
self.messages
```

This lets follow-up questions refer to earlier answers.

## 12. Instructor Questions and Answers

### 1. What is CommerceIQ?

CommerceIQ is a Python CLI application that lets users ask natural-language questions about a MySQL e-commerce database through Claude.

### 2. What is tool calling?

Tool calling is when Claude asks the application to run a defined function. Here, Claude can ask Python to run `query_database(sql_query)`.

### 3. Why did you expose only one tool?

The PRD requires exactly one tool, and one tool keeps the security boundary simple. All database access passes through `query_database()`.

### 4. Does Claude directly connect to MySQL?

No. Claude only generates a tool request. Python connects to MySQL.

### 5. Who generates the SQL?

Claude generates SQL based on the schema and user question.

### 6. Who executes the SQL?

Python executes SQL inside `query_database()` after validation.

### 7. What are helper functions?

Helper functions are smaller functions that support the main function. For example, `validate_sql()` checks safety and `serialize_row()` formats database rows.

### 8. How is conversation history maintained?

`CommerceIQAssistant` stores history in `self.messages`, an in-memory list.

### 9. How does Claude understand follow-up questions?

Each API call sends `messages=list(self.messages)`, so Claude sees earlier user questions, tool results, and assistant answers.

### 10. How does `/clear` work?

The CLI calls `assistant.clear()`, and `clear()` runs `self.messages.clear()`.

### 11. Why is a read-only database account used?

It prevents runtime database writes even if unsafe SQL somehow reaches MySQL.

### 12. How are SQL queries validated?

`validate_sql()` uses `sqlglot` to parse MySQL SQL, requires one `SELECT`, checks allowlisted tables, blocks comments, and rejects risky patterns.

This is not exhaustive: `FOR SHARE` and session-variable assignments currently pass validation.

### 13. What happens if Claude generates invalid SQL?

`query_database()` returns a structured `invalid_sql` error. The error is sent back to Claude as a `tool_result`.

### 14. What is the difference between `tool_use` and `tool_result`?

`tool_use` is Claude asking Python to run a tool. `tool_result` is Python returning the result to Claude.

### 15. How are multiple tool calls handled?

`ask()` collects all `tool_use` blocks in one Claude response, dispatches each one, and sends all matching `tool_result` blocks back.

### 16. What happens if the database connection fails?

`query_database()` returns a structured `connection_failed` error.

### 17. What happens if the Claude API fails?

`CommerceIQAssistant.ask()` catches the exception and returns an `AssistantReply` with a safe error message.

The question was appended to in-memory history before the API call, so it can remain there after a failure. Use `/clear` when you need to start without that failed turn.

### 18. How is revenue calculated?

Revenue is `SUM(order_items.quantity * order_items.unit_price)` for orders where `orders.status = 'Completed'`.

### 19. Why not use `products.price` for revenue?

`products.price` is the current listed price. Historical revenue uses `order_items.unit_price`, which is the price at order time.

### 20. What is stored in MySQL?

Customers, products, orders, and order_items are stored in MySQL.

### 21. Is conversation history stored in the database?

No. It is only stored in memory in `self.messages`.

### 22. What does `--debug` do?

It prints summarized tool results, such as row count and whether output was truncated.

It does not display the result rows. Generated SQL is printed even without `--debug`; use MySQL Workbench to inspect the rows for a demo.

### 23. Why use `sqlglot`?

It parses SQL into a structured form, which is safer than checking only whether a string starts with `SELECT`.

### 24. Why cap rows at 100?

To prevent huge outputs from being sent back to Claude or printed in the CLI.

### 25. What tests prove the tool loop works?

`tests/test_claude_app.py` and `tests/test_end_to_end.py` use mocked Claude responses to verify tool calls, tool results, multiple tool calls, and conversation history.

## 13. How to Demonstrate the Project

### Setup commands

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create the database schema in MySQL Workbench: connect with an admin/setup account, open `scripts/init_db.sql` with **File > Open SQL Script**, and execute it.

Seed data:

```powershell
python scripts/seed_data.py
```

Create the read-only user in MySQL Workbench: open `scripts/create_readonly_user.sql` with **File > Open SQL Script**, replace `REPLACE_WITH_STRONG_PASSWORD` in the Workbench editor with a local password, and execute it with an admin/setup account. Do not save the password into the project script. Put the same password in `.env` for `COMMERCEIQ_DB_PASSWORD`.

Configure `.env`:

```text
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5
COMMERCEIQ_DB_HOST=localhost
COMMERCEIQ_DB_PORT=3306
COMMERCEIQ_DB_NAME=commerceiq
COMMERCEIQ_DB_USER=commerceiq_readonly
COMMERCEIQ_DB_PASSWORD=your_readonly_password
```

Run tests:

```powershell
python -m pytest
```

Run the CLI:

```powershell
python -m commerceiq.cli --debug
```

### Suggested demonstration questions

1. `What are the top 5 products by completed-order revenue?`
2. `Show total completed revenue by month in 2026.`
3. `Which products have stock below 15 units?`
4. `Which customers in Seattle have completed orders?`
5. `Show customer 1's recent order history with product names.`
6. `What is the average current product price by category?`
7. `How many orders are Completed, Pending, and Cancelled?`
8. `What is the profit margin by category?`
9. `For the top revenue category, show example products in that category.`
10. `Try to delete all orders.`

For the last question, Claude may refuse without calling a tool. If it does request a `DELETE`, the validator rejects that statement; the prompt alone does not prove the rejection path was exercised.

### How to show generated SQL

The CLI always prints generated SQL through:

```python
def show_sql(sql_query: str) -> None:
    print("\nGenerated SQL:")
    print(sql_query)
```

So during the demo, ask a question and point out:

```text
Generated SQL:
SELECT ...
```

Then paste that SQL into MySQL Workbench to verify the result.

`--debug` shows a tool-result summary, not the returned rows. Compare the query's rows in Workbench with Claude's answer during the live demonstration; the automated mocked tests do not perform this check.

### How to explain the workflow to the instructor

Use this short explanation:

```text
The user asks a question in the CLI. The CLI sends it to CommerceIQAssistant.
CommerceIQAssistant sends the conversation history, schema prompt, and one tool definition to Claude.
Claude generates a SQL SELECT query and requests query_database.
Python validates the SQL using sqlglot and allowlist checks.
Python runs the query using a read-only MySQL user.
The result is serialized into JSON and returned as a tool_result.
Claude reads the tool_result and writes the final answer.
The conversation history stays in memory so follow-up questions work.
```

That is the core architecture of CommerceIQ.
