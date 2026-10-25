"""`duckdb-sql-foundations` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
filtered_orders = con.sql(
    \"\"\"
    SELECT order_id, amount, refunded
    FROM orders
    WHERE refunded = FALSE AND amount >= 100
    \"\"\"
).pl()
print(filtered_orders.height)
print(filtered_orders.head(3))
""",
    "c3": """\
channel_stats = con.sql(
    \"\"\"
    SELECT
        channel,
        COUNT(*) AS orders,
        SUM(amount) AS revenue
    FROM orders
    GROUP BY channel
    ORDER BY revenue DESC
    \"\"\"
).pl()
print(channel_stats)
""",
    "c4": """\
big_channels = con.sql(
    \"\"\"
    SELECT
        channel,
        COUNT(*) AS orders,
        SUM(amount) AS revenue
    FROM orders
    GROUP BY channel
    HAVING COUNT(*) >= 1260
    ORDER BY revenue DESC
    \"\"\"
).pl()
print(big_channels)
""",
}