---
slug: duckdb-aggregate
title: DuckDB 聚合查询
topic: duckdb
summary: 使用 GROUP BY 进行分组聚合统计
expected_output: "[('A', 150.0), ('B', 120.0)]"
---

使用 SQL 的 GROUP BY 进行分组聚合统计：

```python
import duckdb

con = duckdb.connect()

# 创建销售表
con.execute("""
    CREATE TABLE sales AS
    SELECT * FROM (VALUES
        (1, 'A', 100),
        (2, 'A', 200),
        (3, 'B', 120),
        (4, 'B', 120)
    ) AS t(id, category, amount)
""")

# 按类别分组统计
result = con.execute("""
    SELECT 
        category,
        AVG(amount) as avg_amount
    FROM sales
    GROUP BY category
    ORDER BY avg_amount DESC
""").fetchall()

print(result)
```
