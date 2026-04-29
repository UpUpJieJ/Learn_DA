---
slug: duckdb-create-table
title: DuckDB 创建表
topic: duckdb
summary: 使用 SQL 在 DuckDB 中创建内存表
expected_output: "[(1, 'Alice', 100)]"
---

在 DuckDB 内存数据库中创建表并插入数据：

```python
import duckdb

con = duckdb.connect()

# 创建表
con.execute("""
    CREATE TABLE users (
        id INTEGER,
        name VARCHAR,
        score INTEGER
    )
""")

# 插入数据
con.execute("INSERT INTO users VALUES (1, 'Alice', 100)")
con.execute("INSERT INTO users VALUES (2, 'Bob', 85)")

# 查询
result = con.execute("SELECT * FROM users WHERE score >= 90").fetchall()
print(result)
```
