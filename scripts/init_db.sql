CREATE DATABASE IF NOT EXISTS commerceiq
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE commerceiq;

CREATE TABLE IF NOT EXISTS customers (
  customer_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  city VARCHAR(80) NOT NULL,
  INDEX idx_customers_city (city)
) ENGINE=InnoDB;

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
