"""`polars-duckdb-workflow` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "orders_clean = (\n"
        "    orders.join(\n"
        "        products.select(['product_id', 'category']),\n"
        "        on='product_id',\n"
        "        how='left',\n"
        "    )\n"
        "    .with_columns(\n"
        "        pl.when(pl.col('refunded'))\n"
        "        .then(pl.lit(0.0))\n"
        "        .otherwise(pl.col('amount'))\n"
        "        .alias('net_amount')\n"
        "    )\n"
        ")\n"
        "print(orders_clean.head(3))\n"
    ),
    "c3": (
        "arrow_table = orders_clean.to_arrow()\n"
        "con = duckdb.connect()\n"
        "con.register('orders_clean', arrow_table)\n"
        "registered_rows = con.execute(\n"
        "    'SELECT COUNT(*) FROM orders_clean'\n"
        ").fetchone()[0]\n"
        "print(registered_rows)\n"
    ),
    "c4": (
        "category_stats = con.sql(\n"
        "    '''\n"
        "    SELECT category, SUM(net_amount) AS revenue, COUNT(*) AS orders\n"
        "    FROM orders_clean\n"
        "    GROUP BY category\n"
        "    ORDER BY revenue DESC\n"
        "    '''\n"
        ").pl()\n"
        "print(category_stats)\n"
    ),
}