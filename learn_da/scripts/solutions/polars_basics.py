"""`polars-basics` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "app_orders = orders.filter(pl.col('channel') == 'app').select(\n"
        "    ['order_id', 'region', 'amount']\n"
        ")\n"
        "print(app_orders.head(5))\n"
        "print(app_orders.height)\n"
    ),
    "c3": (
        "with_gross = orders.with_columns(\n"
        "    (pl.col('unit_price') * pl.col('quantity')).alias('gross')\n"
        ")\n"
        "print(with_gross.head(3))\n"
    ),
    "c4": (
        "top_orders = (\n"
        "    orders.sort('amount', descending=True)\n"
        "    .head(10)\n"
        "    .select(['order_id', 'region', 'channel', 'amount'])\n"
        ")\n"
        "print(top_orders)\n"
    ),
}