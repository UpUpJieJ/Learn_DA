---
id: 12
slug: python-functions
title: Python 函数入门
topic: programming
category: python
difficulty: beginner
description: 学会用函数封装重复逻辑，理解参数、返回值和调用过程。
estimated_minutes: 18
order: 12
tags: [python, function, 参数, 返回值]
practice_objective: >-
  能定义一个接收参数的 Python 函数，并通过 return 返回计算结果。
completion_criteria:
  - 使用 def 定义函数
  - 至少传入一个参数
  - 使用 return 返回结果
  - 调用函数并打印输出
track: python_basics
prerequisites: []
recommended_next: [python-collections]
skill_tags: [function, parameter, return_value]
is_review_friendly: true
is_branch_point: false
---

# Python 函数入门

函数可以把一段重复使用的逻辑封装起来。你给它输入参数，它执行步骤，然后把结果返回给调用方。

## 最小示例

```python:example
def double(number):
    return number * 2

result = double(21)
print(result)
```

这段代码中：

- `def double(number)` 定义了一个名为 `double` 的函数。
- `number` 是参数，代表调用时传进来的值。
- `return number * 2` 会把计算结果交回给调用方。
- `double(21)` 是一次函数调用。

## 练习

把 `double` 改成 `add_bonus(score)`，让它给分数加上 5 分并返回结果。
