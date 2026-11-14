from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from mysql.connector import Error as MySQLError

from commerceiq import query_database as query_module
from commerceiq.query_database import query_database, serialize_value, validate_sql


class FakeCursor:
    def __init__(
        self,
        rows: list[tuple[object, ...]] | None = None,
        description: list[tuple[str]] | None = None,
        fail_on_query: bool = False,
    ) -> None:
        self.rows = rows or []
        self.description = description or [("name",), ("price",)]
        self.fail_on_query = fail_on_query
        self.executed: list[tuple[object, object | None]] = []
        self.closed = False

    def execute(self, query: str, params: object | None = None) -> None:
        self.executed.append((query, params))
        if self.fail_on_query and not query.startswith("SET SESSION"):
            raise MySQLError(errno=1142, msg="permission denied")

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        return self.rows[:size]

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "sql_query",
    [
        "UPDATE products SET price = 1",
        "DELETE FROM customers",
        "DROP TABLE orders",
        "SELECT * FROM products; SELECT * FROM customers",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM mysql.user",
        "SELECT * FROM products INTO OUTFILE '/tmp/products.csv'",
        "SELECT * FROM products FOR UPDATE",
        "SELECT * FROM products -- hide this",
        "SELECT 1",
    ],
)
def test_validate_sql_rejects_unsafe_queries(sql_query: str) -> None:
    result = validate_sql(sql_query)

    assert not result.is_valid
    assert result.error


def test_validate_sql_accepts_allowlisted_select() -> None:
    result = validate_sql(
        """
        SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
        FROM commerceiq.products p
        JOIN order_items oi ON oi.product_id = p.product_id
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.status = 'Completed'
        GROUP BY p.category
        ORDER BY revenue DESC
        LIMIT 5
        """
    )

    assert result.is_valid


def test_query_database_returns_structured_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        rows=[("Wireless Mouse", Decimal("24.99"))],
        description=[("name",), ("price",)],
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr(query_module, "create_connection", lambda: connection)

    result = query_database("SELECT name, price FROM products LIMIT 1")

    assert result == {
        "columns": ["name", "price"],
        "rows": [{"name": "Wireless Mouse", "price": "24.99"}],
        "row_count": 1,
        "truncated": False,
        "error": None,
    }
    assert cursor.executed[0] == (
        "SET SESSION MAX_EXECUTION_TIME = %s",
        (query_module.QUERY_TIMEOUT_MS,),
    )
    assert cursor.executed[1] == ("SELECT name, price FROM products LIMIT 1", None)
    assert cursor.closed
    assert connection.closed


def test_query_database_caps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [(f"Product {index}", Decimal("1.00")) for index in range(query_module.MAX_ROWS + 1)]
    cursor = FakeCursor(rows=rows)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(query_module, "create_connection", lambda: connection)

    result = query_database("SELECT name, price FROM products")

    assert result["row_count"] == query_module.MAX_ROWS
    assert result["truncated"] is True
    assert result["error"] is None


def test_query_database_returns_invalid_sql_error_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_connection = Mock()
    monkeypatch.setattr(query_module, "create_connection", create_connection)

    result = query_database("DROP TABLE products")

    assert result["error"]["code"] == "invalid_sql"
    create_connection.assert_not_called()


def test_query_database_handles_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        query_module,
        "create_connection",
        Mock(side_effect=RuntimeError("missing password")),
    )

    result = query_database("SELECT name FROM products LIMIT 1")

    assert result["error"] == {
        "code": "connection_failed",
        "message": "Could not connect to the CommerceIQ database.",
    }


def test_query_database_handles_database_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(fail_on_query=True)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(query_module, "create_connection", lambda: connection)

    result = query_database("SELECT name FROM products LIMIT 1")

    assert result["error"]["code"] == "database_error"
    assert "1142" in result["error"]["message"]
    assert connection.closed


def test_serialize_value_handles_json_types() -> None:
    assert serialize_value(Decimal("12.30")) == "12.30"
    assert serialize_value(date(2026, 5, 1)) == "2026-05-01"
    assert serialize_value(datetime(2026, 5, 1, 9, 30, 0)) == "2026-05-01 09:30:00"
