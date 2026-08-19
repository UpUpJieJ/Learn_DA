---
id: 13
slug: python-collections
title: Python 集合与循环
topic: programming
category: python
difficulty: beginner
description: 学会用 list 保存多项数据，并用 for 循环逐个处理。
estimated_minutes: 20
order: 13
tags: [python, list, for, collection]
practice_objective: >-
  能创建一个列表，并使用 for 循环处理列表中的每个元素。
completion_criteria:
  - 创建至少包含 3 个元素的 list
  - 使用 for 循环遍历列表
  - 在循环中调用函数或完成一次计算
  - 打印每次处理后的结果
track: python_basics
prerequisites: [python-functions]
recommended_next: []
skill_tags: [list, loop, iteration, function]
is_review_friendly: true
is_branch_point: false
exercise:
  id: python-collections-double-loop-v1
  title: 用循环给每个分数翻倍
  language: python
  starter_code: |
    def double_score(score):
        # TODO: 返回 score 的 2 倍
        pass

    scores = [80, 92, 76]

    # TODO: 用 for 循环遍历 scores，调用 double_score 并打印每个结果
  objective: 实现 double_score 返回分数的 2 倍，用 for 循环逐个处理列表并打印。
  hints:
    - return score * 2 返回计算结果
    - "for score in scores: 逐个取出分数"
    - 在循环内 print(double_score(score))
  validator:
    type: stdout_exact
    expected: "160\n184\n152"
---

# Python 集合与循环

当你有多项数据要处理时，可以先把它们放进 `list`，再用 `for` 循环逐个处理。

## 最小示例

```python:example
def add_bonus(score):
    return score + 5

scores = [80, 92, 76]

for score in scores:
    upgraded = add_bonus(score)
    print(upgraded)
```

这段代码中：

- `scores` 是一个列表，保存了多个分数。
- `for score in scores` 会把列表里的分数逐个取出来。
- 循环内部复用了上一课的函数思路，把每个分数都加上奖励分。

## 练习

把 `add_bonus` 改成 `double_score`，让它返回分数的 2 倍，并用 `for` 循环逐个处理 `scores` 列表中的 3 个分数（80、92、76），打印每个结果。
