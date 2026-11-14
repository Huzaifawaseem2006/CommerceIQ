# CommerceIQ Database Schema Contract

Database: `commerceiq` (MySQL 8+). Only these tables may be queried by the AI tool.

## customers
- `customer_id`: INT primary key
- `name`: VARCHAR(100)
- `email`: VARCHAR(150) unique
- `city`: VARCHAR(80)

## products
- `product_id`: INT primary key
- `name`: VARCHAR(120)
- `category`: VARCHAR(80)
- `price`: DECIMAL(10,2), current listed price
- `stock_quantity`: INT, current inventory

## orders
- `order_id`: INT primary key
- `customer_id`: INT, foreign key to customers.customer_id
- `order_date`: DATE
- `status`: ENUM('Completed','Pending','Cancelled')

## order_items
- `order_item_id`: INT primary key
- `order_id`: INT, foreign key to orders.order_id
- `product_id`: INT, foreign key to products.product_id
- `quantity`: INT
- `unit_price`: DECIMAL(10,2), price at order time

## Relationships
- One customer has many orders.
- One order has many order items.
- One product may appear in many order items.

## Business rules
- Revenue is `SUM(order_items.quantity * order_items.unit_price)` for orders where `status = 'Completed'`.
- Current `products.price` is not used for historical revenue.
- Quantity sold counts completed orders by default.
- Pending and cancelled orders do not contribute to realized revenue.
- No cost or profit data is stored; do not calculate profit margin.
- Sample data uses fixed 2026 dates; do not assume it contains records for the real current month.
- All queries must be read-only, single-statement, limited in size, and scoped to these tables.
