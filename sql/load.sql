\set ON_ERROR_STOP on
BEGIN;
CREATE SCHEMA IF NOT EXISTS olist;
SET LOCAL search_path TO olist;
CREATE TABLE IF NOT EXISTS orders (
    order_id text PRIMARY KEY, customer_id text UNIQUE NOT NULL,
    customer_unique_id text NOT NULL, customer_state text NOT NULL,
    order_status text NOT NULL, purchase_date date NOT NULL,
    delivery_days integer CHECK (delivery_days >= 0),
    delivery_band text NOT NULL CHECK (delivery_band IN ('Late','On time','Unassessable')),
    review_score integer CHECK (review_score BETWEEN 1 AND 5)
);
CREATE TABLE IF NOT EXISTS products (product_id text PRIMARY KEY, category text NOT NULL);
CREATE TABLE IF NOT EXISTS sellers (seller_id text PRIMARY KEY, seller_state text NOT NULL);
CREATE TABLE IF NOT EXISTS items (
    order_id text REFERENCES orders, order_item_id integer,
    product_id text NOT NULL REFERENCES products, seller_id text NOT NULL REFERENCES sellers,
    price numeric(14,2) NOT NULL CHECK (price >= 0),
    freight_value numeric(14,2) NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);
CREATE TABLE IF NOT EXISTS payments (
    order_id text REFERENCES orders, payment_sequential integer,
    payment_type text NOT NULL, payment_value numeric(14,2) CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);
CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_zip_code_prefix text PRIMARY KEY, geolocation_lat double precision,
    geolocation_lng double precision
);
TRUNCATE items, payments, orders, products, sellers, geolocation;
\copy orders FROM 'data/clean/orders.csv' CSV HEADER
\copy products FROM 'data/clean/products.csv' CSV HEADER
\copy sellers FROM 'data/clean/sellers.csv' CSV HEADER
\copy items FROM 'data/clean/items.csv' CSV HEADER
\copy payments FROM 'data/clean/payments.csv' CSV HEADER
\copy geolocation FROM 'data/clean/geolocation.csv' CSV HEADER
CREATE INDEX IF NOT EXISTS order_customer_date ON orders(customer_unique_id, purchase_date);
CREATE INDEX IF NOT EXISTS order_purchase_date ON orders(purchase_date);
COMMIT;
