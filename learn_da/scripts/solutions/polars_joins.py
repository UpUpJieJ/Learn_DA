"""`polars-joins` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
orders_customers = orders.join(customers, on="customer_id", how="left")
print(orders_customers.height)
print(orders_customers.head(3))
""",
    "c3": """\
segment_stats = (
    orders_customers
    .with_columns(
        pl.when(pl.col("refunded"))
        .then(0.0)
        .otherwise(pl.col("amount"))
        .alias("net_amount")
    )
    .group_by("segment")
    .agg(
        pl.col("net_amount").sum().alias("revenue"),
        pl.len().alias("orders"),
    )
    .sort("revenue", descending=True)
)
print(segment_stats)
""",
    "c4": """\
orphan_orders = orders.join(customers, on="customer_id", how="anti")
print(orphan_orders.height)
print(orphan_orders.columns)
""",
}