"""`polars-groupby` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "region_stats = (\n"
        "    orders.group_by('region')\n"
        "    .agg(\n"
        "        pl.col('amount').sum().alias('revenue'),\n"
        "        pl.len().alias('orders'),\n"
        "    )\n"
        "    .sort('revenue', descending=True)\n"
        ")\n"
        "print(region_stats)\n"
    ),
    "c3": (
        "region_share = region_stats.with_columns(\n"
        "    (pl.col('revenue') / pl.col('revenue').sum()).round(2).alias('share')\n"
        ")\n"
        "print(region_share)\n"
    ),
}