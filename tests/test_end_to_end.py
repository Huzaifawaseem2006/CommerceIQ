from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from commerceiq.claude_app import CLAUDE_TOOLS, CommerceIQAssistant
from scripts.seed_data import CommerceDataset, build_dataset, money


SQL_SIMPLE_FILTER_SORT_LIMIT = (
    "SELECT name, category, price FROM products "
    "WHERE category = 'Electronics' ORDER BY price DESC LIMIT 3"
)
SQL_JOIN_ORDER_HISTORY = (
    "SELECT c.name AS customer_name, o.order_date, o.status, p.name AS product_name, "
    "oi.quantity, oi.unit_price "
    "FROM customers c "
    "JOIN orders o ON o.customer_id = c.customer_id "
    "JOIN order_items oi ON oi.order_id = o.order_id "
    "JOIN products p ON p.product_id = oi.product_id "
    "WHERE c.customer_id = 1 "
    "ORDER BY o.order_date DESC, o.order_id DESC "
    "LIMIT 5"
)
SQL_AGGREGATE_PRODUCTS = (
    "SELECT category, COUNT(*) AS product_count, AVG(price) AS avg_price "
    "FROM products GROUP BY category ORDER BY category"
)
SQL_REVENUE_BY_CATEGORY = (
    "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue "
    "FROM products p "
    "JOIN order_items oi ON oi.product_id = p.product_id "
    "JOIN orders o ON o.order_id = oi.order_id "
    "WHERE o.status = 'Completed' "
    "GROUP BY p.category "
    "ORDER BY revenue DESC "
    "LIMIT 5"
)
SQL_COMPLETED_REVENUE = (
    "SELECT SUM(oi.quantity * oi.unit_price) AS revenue "
    "FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
    "WHERE o.status = 'Completed'"
)
SQL_PENDING_ORDERS = "SELECT COUNT(*) AS pending_orders FROM orders WHERE status = 'Pending'"


class FakeMessages:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("No fake responses left.")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.messages = FakeMessages(responses)


def text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[{"type": "text", "text": text}])


def tool_response(*tool_uses: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(content=list(tool_uses))


def tool_use(tool_id: str, sql_query: str) -> dict[str, object]:
    return {
        "type": "tool_use",
        "id": tool_id,
        "name": "query_database",
        "input": {"sql_query": sql_query},
    }


def structured_result(rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = list(rows[0].keys()) if rows else []
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": False,
        "error": None,
    }


def dataset_query_tool(sql_query: str) -> dict[str, Any]:
    dataset = build_dataset()
    if sql_query == SQL_SIMPLE_FILTER_SORT_LIMIT:
        return structured_result(simple_filter_sort_limit(dataset))
    if sql_query == SQL_JOIN_ORDER_HISTORY:
        return structured_result(join_order_history(dataset))
    if sql_query == SQL_AGGREGATE_PRODUCTS:
        return structured_result(aggregate_products(dataset))
    if sql_query == SQL_REVENUE_BY_CATEGORY:
        return structured_result(revenue_by_category(dataset))
    if sql_query == SQL_COMPLETED_REVENUE:
        return structured_result([{"revenue": str(completed_revenue(dataset))}])
    if sql_query == SQL_PENDING_ORDERS:
        pending_orders = sum(1 for order in dataset.orders if order["status"] == "Pending")
        return structured_result([{"pending_orders": pending_orders}])
    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "error": {"code": "unexpected_sql", "message": sql_query},
    }


def simple_filter_sort_limit(dataset: CommerceDataset) -> list[dict[str, Any]]:
    products = [
        product
        for product in dataset.products
        if product["category"] == "Electronics"
    ]
    products.sort(key=lambda product: Decimal(product["price"]), reverse=True)
    return [
        {
            "name": product["name"],
            "category": product["category"],
            "price": str(product["price"]),
        }
        for product in products[:3]
    ]


def join_order_history(dataset: CommerceDataset) -> list[dict[str, Any]]:
    customers = {customer["customer_id"]: customer for customer in dataset.customers}
    products = {product["product_id"]: product for product in dataset.products}
    orders = {order["order_id"]: order for order in dataset.orders}
    rows = []
    for item in dataset.order_items:
        order = orders[item["order_id"]]
        if order["customer_id"] != 1:
            continue
        customer = customers[order["customer_id"]]
        product = products[item["product_id"]]
        rows.append(
            {
                "customer_name": customer["name"],
                "order_date": order["order_date"].isoformat(),
                "status": order["status"],
                "product_name": product["name"],
                "quantity": item["quantity"],
                "unit_price": str(item["unit_price"]),
            }
        )
    rows.sort(key=lambda row: (row["order_date"], row["product_name"]), reverse=True)
    return rows[:5]


def aggregate_products(dataset: CommerceDataset) -> list[dict[str, Any]]:
    categories = sorted({product["category"] for product in dataset.products})
    rows = []
    for category in categories:
        products = [product for product in dataset.products if product["category"] == category]
        avg_price = sum(Decimal(product["price"]) for product in products) / len(products)
        rows.append(
            {
                "category": category,
                "product_count": len(products),
                "avg_price": str(money(avg_price)),
            }
        )
    return rows


def completed_revenue(dataset: CommerceDataset) -> Decimal:
    completed_order_ids = {
        order["order_id"]
        for order in dataset.orders
        if order["status"] == "Completed"
    }
    return money(
        sum(
            Decimal(item["quantity"]) * Decimal(item["unit_price"])
            for item in dataset.order_items
            if item["order_id"] in completed_order_ids
        )
    )


def revenue_by_category(dataset: CommerceDataset) -> list[dict[str, Any]]:
    products = {product["product_id"]: product for product in dataset.products}
    orders = {order["order_id"]: order for order in dataset.orders}
    revenue: dict[str, Decimal] = {}
    for item in dataset.order_items:
        order = orders[item["order_id"]]
        if order["status"] != "Completed":
            continue
        category = products[item["product_id"]]["category"]
        revenue[category] = revenue.get(category, Decimal("0.00")) + (
            Decimal(item["quantity"]) * Decimal(item["unit_price"])
        )
    rows = [
        {"category": category, "revenue": str(money(total))}
        for category, total in revenue.items()
    ]
    rows.sort(key=lambda row: Decimal(row["revenue"]), reverse=True)
    return rows[:5]


def assistant_with(responses: list[object]) -> CommerceIQAssistant:
    return CommerceIQAssistant(
        client=FakeClient(responses),
        model="test-model",
        system_prompt="schema",
        query_tool=dataset_query_tool,
    )


def test_simple_retrieval_filtering_sorting_and_limit_against_seeded_dataset() -> None:
    expected_rows = simple_filter_sort_limit(build_dataset())
    assistant = assistant_with(
        [
            tool_response(tool_use("toolu_simple", SQL_SIMPLE_FILTER_SORT_LIMIT)),
            text_response(f"The top electronics product is {expected_rows[0]['name']}."),
        ]
    )

    reply = assistant.ask("Show the 3 most expensive electronics products.")

    assert reply.error is None
    assert reply.tool_calls[0].sql_query == SQL_SIMPLE_FILTER_SORT_LIMIT
    assert expected_rows[0]["name"] in reply.answer


def test_join_query_across_customers_orders_items_and_products() -> None:
    expected_rows = join_order_history(build_dataset())
    assistant = assistant_with(
        [
            tool_response(tool_use("toolu_join", SQL_JOIN_ORDER_HISTORY)),
            text_response(f"The latest item for customer 1 is {expected_rows[0]['product_name']}."),
        ]
    )

    reply = assistant.ask("Show customer 1's recent order history.")

    assert reply.error is None
    assert reply.tool_calls[0].result_summary == f"rows={len(expected_rows)}, truncated=False"
    assert expected_rows[0]["product_name"] in reply.answer


def test_count_avg_group_by_aggregate_query_against_seeded_dataset() -> None:
    expected_rows = aggregate_products(build_dataset())
    office_row = next(row for row in expected_rows if row["category"] == "Office")
    assistant = assistant_with(
        [
            tool_response(tool_use("toolu_aggregate", SQL_AGGREGATE_PRODUCTS)),
            text_response(
                f"Office has {office_row['product_count']} products with average price {office_row['avg_price']}."
            ),
        ]
    )

    reply = assistant.ask("Count products and average price by category.")

    assert reply.error is None
    assert "Office" in reply.answer
    assert str(office_row["product_count"]) in reply.answer


def test_completed_revenue_uses_unit_price_and_completed_orders_only() -> None:
    expected_total = completed_revenue(build_dataset())
    expected_categories = revenue_by_category(build_dataset())
    assistant = assistant_with(
        [
            tool_response(tool_use("toolu_revenue", SQL_REVENUE_BY_CATEGORY)),
            text_response(
                f"Top category is {expected_categories[0]['category']}; total completed revenue is {expected_total}."
            ),
        ]
    )

    reply = assistant.ask("What are the top categories by completed-order revenue?")

    assert reply.error is None
    assert "SUM(oi.quantity * oi.unit_price)" in reply.tool_calls[0].sql_query
    assert "WHERE o.status = 'Completed'" in reply.tool_calls[0].sql_query
    assert str(expected_total) in reply.answer


def test_multiple_query_database_calls_in_single_user_request() -> None:
    assistant = assistant_with(
        [
            tool_response(
                tool_use("toolu_revenue_total", SQL_COMPLETED_REVENUE),
                tool_use("toolu_pending_orders", SQL_PENDING_ORDERS),
            ),
            text_response("Completed revenue and pending order count are now compared."),
        ]
    )

    reply = assistant.ask("Compare completed revenue with pending order count.")

    assert reply.error is None
    assert len(reply.tool_calls) == 2
    assert [call.tool_use_id for call in reply.tool_calls] == [
        "toolu_revenue_total",
        "toolu_pending_orders",
    ]


def test_multi_turn_follow_up_keeps_context_until_clear() -> None:
    expected_categories = revenue_by_category(build_dataset())
    top_category = expected_categories[0]["category"]
    assistant = assistant_with(
        [
            tool_response(tool_use("toolu_first", SQL_REVENUE_BY_CATEGORY)),
            text_response(f"The top revenue category is {top_category}."),
            tool_response(tool_use("toolu_followup", SQL_SIMPLE_FILTER_SORT_LIMIT)),
            text_response(f"Within that category, {top_category}, here is a product list."),
        ]
    )

    first = assistant.ask("What is the top category by completed revenue?")
    second = assistant.ask("Show me products in that category.")

    assert first.error is None
    assert second.error is None
    assert top_category in first.answer
    assert len(assistant.messages) > 4

    assistant.clear()
    assert assistant.messages == []


def test_tool_errors_are_returned_gracefully_to_claude() -> None:
    def failing_query_tool(sql_query: str) -> dict[str, Any]:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "error": {"code": "invalid_sql", "message": "Only SELECT is allowed."},
        }

    assistant = CommerceIQAssistant(
        client=FakeClient(
            [
                tool_response(tool_use("toolu_bad_sql", "UPDATE products SET price = 0")),
                text_response("That query was rejected because only read-only SELECT is allowed."),
            ]
        ),
        model="test-model",
        system_prompt="schema",
        query_tool=failing_query_tool,
    )

    reply = assistant.ask("Try an unsafe query.")

    assert reply.error is None
    assert reply.tool_calls[0].error == {
        "code": "invalid_sql",
        "message": "Only SELECT is allowed.",
    }
    assert "rejected" in reply.answer


def test_only_query_database_is_exposed_to_claude() -> None:
    assert len(CLAUDE_TOOLS) == 1
    assert CLAUDE_TOOLS[0]["name"] == "query_database"
