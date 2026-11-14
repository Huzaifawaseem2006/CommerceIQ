from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import mysql.connector
import sqlglot
from dotenv import load_dotenv
from mysql.connector import Error as MySQLError
from sqlglot import expressions as exp


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


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    error: str | None = None


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


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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


def set_query_timeout(cursor: Any) -> None:
    try:
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (QUERY_TIMEOUT_MS,))
    except MySQLError:
        # Some MySQL-compatible environments may not allow this session setting.
        # Continue with read-only DB permissions and result caps as the hard boundary.
        pass


def serialize_row(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        column: serialize_value(value)
        for column, value in zip(columns, row, strict=True)
    }


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


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


def safe_database_message(exc: MySQLError) -> str:
    error_number = getattr(exc, "errno", None)
    if error_number:
        return f"Database rejected the query. MySQL error code: {error_number}."
    return "Database rejected the query."
