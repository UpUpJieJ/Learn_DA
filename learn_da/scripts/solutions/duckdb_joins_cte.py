"""`duckdb-joins-cte` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
order_detail = con.sql(
    \"\"\"
    SELECT
        o.order_id,
        o.product_id,
        p.category,
        o.amount
    FROM orders o
    LEFT JOIN products p USING (product_id)
    \"\"\"
).pl()
print(order_detail.height)
print(order_detail.head(3))
""",
    "c3": """\
category_stats = con.sql(
    \"\"\"
    WITH order_profit AS (
        SELECT
            o.order_id,
            p.category,
            o.amount AS revenue,
            o.amount - p.cost * o.quantity AS profit
        FROM orders o
        LEFT JOIN products p USING (product_id)
    )
    SELECT
        category,
        SUM(revenue) AS revenue,
        SUM(profit) AS profit
    FROM order_profit
    GROUP BY category
    ORDER BY revenue DESC
    \"\"\"
).pl()
print(category_stats)
""",
    "c4": """\
con.execute(
    \"\"\"
    CREATE OR REPLACE TABLE orders AS
    SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')
    UNION ALL
    SELECT
        'O999999', 'C00001', 'P9999', '华东', 'app',
        1, 100.0, 1.0, 100.0, DATE '2025-12-31', FALSE
    \"\"\"
)
join_compare = con.sql(
    \"\"\"
    SELECT 'left' AS join_type, COUNT(*) AS row_count
    FROM orders o LEFT JOIN products p USING (product_id)
    UNION ALL
    SELECT 'inner' AS join_type, COUNT(*)
    FROM orders o JOIN products p USING (product_id)
    \"\"\"
).pl()
unmatched_orders = con.sql(
    \"\"\"
    SELECT o.order_id, o.product_id, o.amount
    FROM orders o
    LEFT JOIN products p USING (product_id)
    WHERE p.product_id IS NULL
    \"\"\"
).pl()
print(join_compare)
print(unmatched_orders)
""",
}