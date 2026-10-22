"""`polars-lazy-pipeline` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": """\
filtered = (
    orders.lazy()
    .filter(~pl.col("refunded"))
    .filter(pl.col("amount") >= 100)
    .with_columns(
        (pl.col("amount") / pl.col("discount")).round(2).alias("list_amount")
    )
    .collect()
)
print(filtered.shape)
print(filtered.head(3))
""",
    "c3": """\
region_stats = (
    filtered.lazy()
    .group_by("region")
    .agg(
        pl.col("amount").sum().alias("revenue"),
        pl.len().alias("orders"),
    )
    .sort("revenue", descending=True)
    .collect()
)
print(region_stats)
""",
    "c4": """\
pipeline = (
    orders.lazy()
    .filter(~pl.col("refunded"))
    .group_by("region")
    .agg(pl.col("amount").sum().alias("revenue"))
    .sort("revenue", descending=True)
)

plan_text = pipeline.explain()
print(plan_text)

lazy_result = pipeline.collect()
print(lazy_result)
""",
}