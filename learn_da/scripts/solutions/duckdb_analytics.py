"""`duckdb-analytics` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
con.execute(
    "CREATE OR REPLACE TABLE orders AS "
    "SELECT * FROM read_csv_auto('data/ecommerce/orders.csv')"
)
orders_df = con.sql("SELECT * FROM orders").pl()
order_count = orders_df.height
print(order_count)
print(orders_df.head(3))
""",
    "c3": """\
region_stats = con.sql(
    \"\"\"
    SELECT
        region,
        SUM(amount) AS revenue,
        COUNT(*) AS orders
    FROM orders
    GROUP BY region
    ORDER BY revenue DESC
    \"\"\"
).pl()
print(region_stats)
""",
    "c4": """\
top_orders = con.sql(
    "SELECT order_id, amount FROM orders ORDER BY amount DESC LIMIT 5"
).pl()
print(top_orders)
""",
}