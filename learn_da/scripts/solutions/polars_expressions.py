"""`polars-expressions` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "with_amounts = orders.with_columns(\n"
        "    (pl.col('unit_price') * pl.col('quantity')).alias('gross'),\n"
        "    (pl.col('unit_price') * pl.col('quantity') * pl.col('discount'))\n"
        "    .round(2)\n"
        "    .alias('net_amount'),\n"
        ")\n"
        "print(with_amounts.head(3))\n"
    ),
    "c3": (
        "tiered_orders = with_amounts.with_columns(\n"
        "    pl.when(pl.col('amount') >= 500)\n"
        "    .then(pl.lit('高客单'))\n"
        "    .when(pl.col('amount') >= 200)\n"
        "    .then(pl.lit('中客单'))\n"
        "    .otherwise(pl.lit('低客单'))\n"
        "    .alias('amount_tier')\n"
        ")\n"
        "print(tiered_orders.group_by('amount_tier').len().sort('amount_tier'))\n"
    ),
    "c4": (
        "tagged_orders = tiered_orders.with_columns(\n"
        "    pl.lit('ecommerce').alias('source'),\n"
        "    (pl.col('amount') / pl.lit(1000)).round(2).alias('amount_k'),\n"
        ")\n"
        "print(tagged_orders.head(3))\n"
    ),
}