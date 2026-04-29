---
slug: polars-filter
title: Polars 筛选数据
topic: polars
summary: 使用 filter 方法根据条件筛选行数据
expected_output: "shape: (2, 2)"
---

使用 `filter` 方法根据条件筛选 DataFrame 的行：

```python
import polars as pl

df = pl.DataFrame({
    'name': ['Alice', 'Bob', 'Charlie', 'David'],
    'age': [25, 30, 35, 40],
    'city': ['Beijing', 'Shanghai', 'Beijing', 'Shenzhen'],
})

# 筛选年龄大于 28 的人
result = df.filter(pl.col('age') > 28)
print(result)
```
