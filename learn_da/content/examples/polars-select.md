---
slug: polars-select
title: Polars 选择列
topic: polars
summary: 使用 select 方法选择指定列
expected_output: "shape: (3, 2)"
---

使用 `select` 方法选择 DataFrame 的指定列：

```python
import polars as pl

df = pl.DataFrame({
    'name': ['Alice', 'Bob', 'Charlie'],
    'age': [25, 30, 35],
    'salary': [5000, 6000, 7000],
    'department': ['IT', 'HR', 'IT'],
})

# 只选择 name 和 salary 列
result = df.select(['name', 'salary'])
print(result)
```
