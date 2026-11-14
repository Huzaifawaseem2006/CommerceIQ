from __future__ import annotations

import argparse
import os
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

try:
    import mysql.connector
    from mysql.connector import MySQLConnection
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    mysql = None
    MySQLConnection = object  # type: ignore[assignment,misc]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional for tests
    load_dotenv = None


RANDOM_SEED = 20261009
DATABASE_NAME = "commerceiq"
EXPECTED_COUNTS = {
    "customers": 50,
    "products": 30,
    "orders": 200,
    "order_items": 400,
}


@dataclass(frozen=True)
class CommerceDataset:
    customers: list[dict[str, object]]
    products: list[dict[str, object]]
    orders: list[dict[str, object]]
    order_items: list[dict[str, object]]


def money(value: Decimal | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_dataset() -> CommerceDataset:
    rng = random.Random(RANDOM_SEED)
    cities = [
        "Austin",
        "Boston",
        "Chicago",
        "Denver",
        "Miami",
        "Portland",
        "San Diego",
        "Seattle",
        "Phoenix",
        "Atlanta",
    ]
    first_names = [
        "Avery",
        "Blake",
        "Casey",
        "Drew",
        "Emerson",
        "Finley",
        "Harper",
        "Jordan",
        "Morgan",
        "Riley",
    ]
    last_names = [
        "Adams",
        "Brooks",
        "Chen",
        "Diaz",
        "Evans",
        "Foster",
        "Garcia",
        "Hughes",
        "Patel",
        "Rivera",
    ]

    customers = [
        {
            "customer_id": customer_id,
            "name": f"{first_names[(customer_id - 1) % len(first_names)]} {last_names[(customer_id - 1) // 5 % len(last_names)]}",
            "email": f"customer{customer_id:03d}@example.com",
            "city": cities[(customer_id - 1) % len(cities)],
        }
        for customer_id in range(1, 51)
    ]

    product_specs = [
        ("Wireless Mouse", "Electronics", "24.99", 85),
        ("Mechanical Keyboard", "Electronics", "89.99", 32),
        ("USB-C Hub", "Electronics", "39.50", 48),
        ("Noise Cancelling Headphones", "Electronics", "149.99", 18),
        ("Portable Monitor", "Electronics", "219.00", 9),
        ("Smart LED Bulb", "Home", "14.99", 120),
        ("Air Purifier", "Home", "129.99", 16),
        ("Desk Lamp", "Home", "34.99", 44),
        ("Cotton Sheet Set", "Home", "59.99", 27),
        ("Ceramic Dinner Set", "Home", "74.50", 13),
        ("Running Shoes", "Apparel", "79.99", 41),
        ("Rain Jacket", "Apparel", "119.00", 22),
        ("Graphic T-Shirt", "Apparel", "21.99", 96),
        ("Yoga Pants", "Apparel", "49.99", 35),
        ("Wool Beanie", "Apparel", "18.50", 7),
        ("Protein Powder", "Grocery", "42.99", 52),
        ("Organic Coffee Beans", "Grocery", "16.99", 73),
        ("Trail Mix Box", "Grocery", "27.50", 64),
        ("Olive Oil", "Grocery", "22.25", 28),
        ("Dark Chocolate Pack", "Grocery", "12.99", 88),
        ("Planner Notebook", "Office", "15.99", 60),
        ("Ergonomic Chair", "Office", "249.99", 6),
        ("Standing Desk Mat", "Office", "45.00", 20),
        ("Gel Pens Pack", "Office", "9.99", 110),
        ("Document Organizer", "Office", "29.99", 37),
        ("Board Game", "Toys", "34.50", 25),
        ("Building Blocks Set", "Toys", "54.99", 19),
        ("Science Kit", "Toys", "39.99", 14),
        ("Puzzle 1000 Pieces", "Toys", "17.99", 57),
        ("Plush Dinosaur", "Toys", "24.50", 11),
    ]
    products = [
        {
            "product_id": index,
            "name": name,
            "category": category,
            "price": money(price),
            "stock_quantity": stock_quantity,
        }
        for index, (name, category, price, stock_quantity) in enumerate(product_specs, start=1)
    ]

    start_date = date(2026, 1, 1)
    status_cycle = ["Completed"] * 7 + ["Pending"] * 2 + ["Cancelled"]
    orders = []
    for order_id in range(1, 201):
        orders.append(
            {
                "order_id": order_id,
                "customer_id": rng.randint(1, len(customers)),
                "order_date": start_date + timedelta(days=rng.randint(0, 364)),
                "status": status_cycle[(order_id + rng.randint(0, 9)) % len(status_cycle)],
            }
        )

    order_items = []
    order_item_id = 1
    price_adjustments = [Decimal("0.90"), Decimal("0.95"), Decimal("1.00"), Decimal("1.05")]
    for order in orders:
        used_product_ids: set[int] = set()
        for _ in range(2):
            product = rng.choice(products)
            while int(product["product_id"]) in used_product_ids:
                product = rng.choice(products)
            used_product_ids.add(int(product["product_id"]))

            order_items.append(
                {
                    "order_item_id": order_item_id,
                    "order_id": order["order_id"],
                    "product_id": product["product_id"],
                    "quantity": rng.randint(1, 5),
                    "unit_price": money(Decimal(product["price"]) * rng.choice(price_adjustments)),
                }
            )
            order_item_id += 1

    return CommerceDataset(
        customers=customers,
        products=products,
        orders=orders,
        order_items=order_items,
    )


def completed_revenue(dataset: CommerceDataset) -> Decimal:
    completed_order_ids = {
        int(order["order_id"])
        for order in dataset.orders
        if order["status"] == "Completed"
    }
    total = Decimal("0.00")
    for item in dataset.order_items:
        if int(item["order_id"]) in completed_order_ids:
            total += Decimal(item["quantity"]) * Decimal(item["unit_price"])
    return money(total)


def iter_table_rows(dataset: CommerceDataset, table_name: str) -> Iterable[dict[str, object]]:
    return getattr(dataset, table_name)


def connect() -> MySQLConnection:
    if mysql is None:
        raise RuntimeError(
            "mysql-connector-python is required to load seed data. "
            "Install dependencies with: pip install -r requirements.txt"
        )
    if load_dotenv is not None:
        load_dotenv()

    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.getenv("MYSQL_DATABASE", DATABASE_NAME),
    )


def table_counts(connection: MySQLConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    cursor = connection.cursor()
    try:
        for table_name in EXPECTED_COUNTS:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            counts[table_name] = int(cursor.fetchone()[0])
    finally:
        cursor.close()
    return counts


def ensure_empty_or_reset(connection: MySQLConnection, reset: bool) -> None:
    counts = table_counts(connection)
    populated = {table: count for table, count in counts.items() if count > 0}
    if not populated:
        return
    if not reset:
        details = ", ".join(f"{table}={count}" for table, count in populated.items())
        raise RuntimeError(
            "Refusing to seed non-empty tables. "
            f"Existing row counts: {details}. Re-run with --reset to explicitly reload sample data."
        )

    cursor = connection.cursor()
    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table_name in ("order_items", "orders", "products", "customers"):
            cursor.execute(f"TRUNCATE TABLE {table_name}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    except Exception:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        raise
    finally:
        cursor.close()


def insert_rows(connection: MySQLConnection, table_name: str, rows: list[dict[str, object]]) -> None:
    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_list = ", ".join(columns)
    values = [tuple(row[column] for column in columns) for row in rows]
    cursor = connection.cursor()
    try:
        cursor.executemany(
            f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})",
            values,
        )
    finally:
        cursor.close()


def seed_database(reset: bool) -> dict[str, int]:
    dataset = build_dataset()
    connection = connect()
    try:
        ensure_empty_or_reset(connection, reset=reset)
        insert_rows(connection, "customers", dataset.customers)
        insert_rows(connection, "products", dataset.products)
        insert_rows(connection, "orders", dataset.orders)
        insert_rows(connection, "order_items", dataset.order_items)
        connection.commit()
        return table_counts(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify_dataset(dataset: CommerceDataset) -> None:
    counts = {
        "customers": len(dataset.customers),
        "products": len(dataset.products),
        "orders": len(dataset.orders),
        "order_items": len(dataset.order_items),
    }
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"Unexpected generated counts: {counts}")

    customer_ids = {customer["customer_id"] for customer in dataset.customers}
    product_ids = {product["product_id"] for product in dataset.products}
    order_ids = {order["order_id"] for order in dataset.orders}
    for order in dataset.orders:
        if order["customer_id"] not in customer_ids:
            raise ValueError(f"Order references missing customer: {order}")
    for item in dataset.order_items:
        if item["order_id"] not in order_ids:
            raise ValueError(f"Order item references missing order: {item}")
        if item["product_id"] not in product_ids:
            raise ValueError(f"Order item references missing product: {item}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the CommerceIQ MySQL sample dataset.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Explicitly truncate and reload sample tables if they already contain data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate the deterministic dataset without connecting to MySQL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset()
    verify_dataset(dataset)
    revenue = completed_revenue(dataset)

    if args.dry_run:
        print("Generated deterministic CommerceIQ dataset.")
        print(f"Counts: {EXPECTED_COUNTS}")
        print(f"Completed-order revenue: {revenue}")
        return

    counts = seed_database(reset=args.reset)
    print("Seeded CommerceIQ sample data.")
    print(f"Counts: {counts}")
    print(f"Completed-order revenue: {revenue}")


if __name__ == "__main__":
    main()
