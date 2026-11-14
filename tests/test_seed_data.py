from decimal import Decimal

from scripts.seed_data import EXPECTED_COUNTS, build_dataset, completed_revenue, verify_dataset


def test_generated_dataset_has_required_counts() -> None:
    dataset = build_dataset()

    assert len(dataset.customers) == EXPECTED_COUNTS["customers"]
    assert len(dataset.products) == EXPECTED_COUNTS["products"]
    assert len(dataset.orders) == EXPECTED_COUNTS["orders"]
    assert len(dataset.order_items) == EXPECTED_COUNTS["order_items"]


def test_generated_dataset_is_deterministic() -> None:
    first = build_dataset()
    second = build_dataset()

    assert first == second


def test_generated_dataset_preserves_relationships() -> None:
    dataset = build_dataset()

    verify_dataset(dataset)


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
