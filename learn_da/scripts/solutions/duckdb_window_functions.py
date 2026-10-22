"""`duckdb-window-functions` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
region_rank = con.sql(
    '''
    SELECT
        order_id,
        region,
        amount,
        RANK() OVER (PARTITION BY region ORDER BY amount DESC) AS amount_rank
    FROM orders
    ORDER BY region, amount_rank, order_id
    '''
).fetchall()
print(region_rank[:5])
print(len(region_rank))
""",
    "c3": """\
region_running = con.sql(
    '''
    SELECT
        region,
        order_date,
        amount,
        SUM(amount) OVER (
            PARTITION BY region
            ORDER BY order_date
        ) AS running_amount
    FROM orders
    ORDER BY region, order_date, order_id
    '''
).fetchall()
print(region_running[:5])
print(len(region_running))
""",
    "c4": """\
group_rows = con.sql(
    '''
    SELECT
        region,
        SUM(amount) AS revenue,
        COUNT(*) AS orders
    FROM orders
    GROUP BY region
    ORDER BY region
    '''
).fetchall()

window_rows = con.sql(
    '''
    SELECT
        order_id,
        region,
        amount,
        SUM(amount) OVER (PARTITION BY region) AS region_revenue
    FROM orders
    ORDER BY region, order_id
    '''
).fetchall()

print(group_rows)
print(len(window_rows))
""",
}