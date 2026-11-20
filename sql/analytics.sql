\set ON_ERROR_STOP on
SET search_path TO olist;

-- Monthly performance. Aggregate the items before joining to orders.
WITH order_value AS (
    SELECT order_id, SUM(price) AS revenue FROM items GROUP BY order_id
), monthly AS (
    SELECT date_trunc('month', purchase_date)::date AS month,
           COUNT(*) AS order_count, COALESCE(SUM(revenue), 0) AS revenue
    FROM orders LEFT JOIN order_value USING (order_id)
    WHERE order_status = 'delivered' GROUP BY 1
), calendar AS (
    SELECT generate_series(MIN(month), MAX(month), INTERVAL '1 month')::date AS month
    FROM monthly
), previous AS (
    SELECT calendar.month, COALESCE(order_count, 0) AS order_count,
           COALESCE(revenue, 0) AS revenue,
           LAG(COALESCE(revenue, 0)) OVER (ORDER BY calendar.month) AS prior_revenue
    FROM calendar LEFT JOIN monthly USING (month)
)
SELECT *, ROUND(revenue / NULLIF(prior_revenue, 0) - 1, 4) AS mom_growth,
       ROUND(revenue / NULLIF(order_count, 0), 2) AS aov
FROM previous ORDER BY month;

-- Date of the second completed order and elapsed calendar days.
WITH purchase_sequence AS (
    SELECT customer_unique_id, purchase_date,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchase_date, order_id) AS purchase_number,
           LAG(purchase_date) OVER (PARTITION BY customer_unique_id ORDER BY purchase_date, order_id) AS prior_purchase
    FROM orders WHERE order_status = 'delivered'
)
SELECT COUNT(*) FILTER (WHERE purchase_number = 1) AS customers,
       COUNT(*) FILTER (WHERE purchase_number = 2) AS repeat_customers,
       ROUND(AVG(purchase_date - prior_purchase) FILTER (WHERE purchase_number = 2), 1)
        AS average_days_to_second_purchase
FROM purchase_sequence;

-- Comparable delivered orders. Review coverage is shown alongside averages.
SELECT customer_state, COUNT(*) AS comparable_orders,
       COUNT(*) FILTER (WHERE delivery_band = 'Late') AS late_orders,
       ROUND(AVG((delivery_band = 'Late')::int), 4) AS late_rate,
       COUNT(review_score) FILTER (WHERE delivery_band = 'Late') AS late_review_count,
       ROUND(AVG(review_score) FILTER (WHERE delivery_band = 'Late'), 2) AS late_rating,
       ROUND(AVG(review_score) FILTER (WHERE delivery_band = 'On time'), 2) AS on_time_rating
FROM orders WHERE delivery_band IN ('Late','On time')
GROUP BY customer_state ORDER BY late_orders DESC;

-- Category share and ranking are calculated at the item grain.
WITH category_sales AS (
    SELECT category, SUM(price) AS revenue, COUNT(*) AS units, COUNT(DISTINCT order_id) AS orders
    FROM items JOIN products USING (product_id) JOIN orders USING (order_id)
    WHERE order_status = 'delivered' GROUP BY category
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY revenue DESC, category) AS rank,
           ROUND(revenue / NULLIF(SUM(revenue) OVER (), 0), 4) AS revenue_share
    FROM category_sales
)
SELECT * FROM ranked WHERE rank <= 10 ORDER BY rank;

-- Payment mix uses payment value; an order can contribute to several payment types.
SELECT payment_type, SUM(payment_value) AS paid_amount, COUNT(DISTINCT order_id) AS orders
FROM payments JOIN orders USING (order_id) WHERE order_status = 'delivered'
GROUP BY payment_type ORDER BY paid_amount DESC NULLS LAST;
