"""`polars-cleaning` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "null_counts = dirty.null_count()\n"
        "filled_orders = dirty.with_columns(\n"
        "    pl.col('discount').fill_null(1.0),\n"
        "    pl.col('quantity').fill_null(1),\n"
        ")\n"
        "print(filled_orders.head(3))\n"
    ),
    "c3": (
        "cleaned_text = (\n"
        "    filled_orders.unique(subset=['order_id'], keep='first')\n"
        "    .with_columns(\n"
        "        pl.col('region').str.strip_chars(),\n"
        "        pl.col('channel').str.to_lowercase(),\n"
        "    )\n"
        ")\n"
        "print(cleaned_text.shape)\n"
    ),
    "c4": (
        "typed_orders = (\n"
        "    cleaned_text.with_columns(\n"
        "        pl.col('amount').cast(pl.Float64, strict=False),\n"
        "        pl.col('order_date').str.replace_all('-', '/'),\n"
        "    )\n"
        "    .with_columns(pl.col('order_date').str.to_date('%Y/%m/%d'))\n"
        ")\n"
        "print(typed_orders.schema)\n"
    ),
}