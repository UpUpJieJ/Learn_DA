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
# 改版 M4：多 cell 工作区（重放式，严格顺序）
workspace:
  cells:
    - id: c1
      kind: starter
      code: |
        # 起步：一个列表 + 一次 for 循环
        names = ["小明", "小红", "小刚"]
        for name in names:
            print(name)
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: 建一个至少 3 个元素的 regions 列表，for 循环逐个打印，
        #       每打印一个就让 region_lines 加 1
        regions = []
        region_lines = 0
        print(region_lines)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: for 循环累加出 total_amount，并把大于 200 的金额收进 big_amounts
        amounts = [120, 899, 240, 59, 180, 620]
        total_amount = 0
        big_amounts = []
        print(total_amount, big_amounts)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: 用 dict 统计 region_log 里每个区域出现的次数，存进 region_counts
        region_log = ["华东", "华南", "华东", "华北", "华东", "华南", "西南"]
        region_counts = {}
        print(region_counts)
  tasks:
    - id: t1
      title: 创建列表并用 for 逐个打印
      cell: c2
      objective: 建一个至少 3 个字符串元素的 regions 列表，用 for 循环逐个打印，并把打印次数累加进 region_lines。
      assertions:
        - id: t1-size
          type: expr_true
          title: regions 至少有 3 个元素
          expr: "len(regions) >= 3"
        - id: t1-count
          type: expr_true
          title: region_lines 等于列表长度（每个元素都进过循环）
          expr: "region_lines == len(regions)"
        - id: t1-strings
          type: expr_true
          title: 列表里都是字符串，打印出来才是区域名
          expr: "all(str(r) == r for r in regions)"
    - id: t2
      title: 在循环里累加与筛选
      cell: c3
      objective: 用 for 循环把 amounts 累加进 total_amount（应为 2118），并把大于 200 的金额收进 big_amounts。
      assertions:
        - id: t2-sum
          type: expr_true
          title: total_amount == 2118
          expr: "total_amount == 2118"
        - id: t2-sum-check
          type: expr_true
          title: 累加结果等于所有金额之和
          expr: "abs(total_amount - sum(amounts)) < 1e-6"
        - id: t2-big
          type: expr_true
          title: big_amounts 只收 > 200 的三笔，且保持原顺序
          expr: "big_amounts == [899, 240, 620]"
    - id: t3
      title: 用 dict 做分组计数
      cell: c4
      objective: 用 dict 统计 region_log 里每个区域出现的次数：华东 3 次、华南 2 次、华北 1 次、西南 1 次，结果存进 region_counts。
      assertions:
        - id: t3-size
          type: expr_true
          title: region_counts 只有 4 个键
          expr: "len(region_counts) == 4"
        - id: t3-keys
          type: expr_true
          title: 键就是出现过的区域
          expr: "sorted(region_counts.keys()) == ['华东', '华北', '华南', '西南']"
        - id: t3-values
          type: expr_true
          title: 计数正确：华东 3、华南 2、华北 1、西南 1
          expr: "region_counts['华东'] == 3 and region_counts['华南'] == 2 and region_counts['华北'] == 1 and region_counts['西南'] == 1"
        - id: t3-total
          type: expr_true
          title: 所有计数加起来等于 7（没有漏数或重复数）
          expr: "sum(region_counts.values()) == 7"
---

# Python 集合与循环

当你有多项数据要处理时，先把它们放进 `list`，再用 `for` 循环逐个处理；需要「按类别统计」时，就换用 `dict` 计数。这一课就是这两种容器 + 一个循环。

## 这节课解决什么问题

一个分数用一个变量就够了，但一门课的 50 个分数、一张表的 4 个区域，用 `score1`、`score2`… 写下去是无法维护的。列表让「一组同类数据」只有一个名字，循环让「对每个元素做同一件事」只写一遍。

本课三件事：**建 list → 用 for 遍历 → 用 dict 分组计数**。最后一件是数据分析里出现频率最高的动作之一（按区域算订单数、按品类算销量，本质都是它）。

## list：把多项数据装进一个名字

```python:example
scores = [80, 92, 76]
print(scores[0])       # 取第一个
print(len(scores))     # 有几个元素
print(scores + [100])  # 拼成新列表
```

- 方括号里的元素按顺序存放，下标从 `0` 开始。
- `len()` 返回元素个数，`scores[0]` 取下标的元素；列表里可以放任意类型，但**同一份列表最好放同一种东西**，循环时才不用判断类型。

## for：逐个取出来

```python:example
scores = [80, 92, 76]

for score in scores:
    print(score * 2)
```

- `for 变量 in 列表:` 每次循环把下一个元素塞进 `score`，直到取完。
- 循环体靠**缩进**表示归属，四格空格是标准写法。
- 循环结束后 `score` 仍保留最后一个值——别指望它自动清空。

## 在循环里做计算

循环里最常见的两种活是**累加**和**筛选**：

```python:example
scores = [80, 55, 92, 40]
total = 0
passed = []

for score in scores:
    total = total + score
    if score >= 60:
        passed.append(score)

print(total, passed)
```

要点：累加变量在循环**前**初始化；`append()` 把满足条件的元素收进新列表；循环结束后再统一用 `total` / `passed`。

## dict：按 key 分组计数

`dict` 存「键 → 值」的对应关系。最常用的计数套路是：**有则加 1，无则先建**。

```python:example
cities = ["上海", "北京", "上海"]
counts = {}

for city in cities:
    if city in counts:
        counts[city] = counts[city] + 1
    else:
        counts[city] = 1

print(counts)          # {'上海': 2, '北京': 1}
```

也可以先 `counts[city] = counts.get(city, 0) + 1` 一行搞定，两段代码等价；初学先把 if/else 写清楚，理解「键不存在时读它就会报错」。

看结果时记住两点：`len(counts)` 是**不同类别**的个数，`sum(counts.values())` 才是**被统计的总条数**——两者相等说明每个元素都恰好被数了一次。

## 常见错误

**循环里改列表** —— 边遍历边 `append`/`remove` 同一个列表会让元素跳过或重复；要改就先遍历副本或另建新列表。

**累加变量写在循环里 / dict 直接自增** —— `total = 0` 写进 `for` 内会每轮清零，最后只剩最后一个元素；`counts[key] = counts[key] + 1` 在键不存在时抛 `KeyError`，要么先 `if key in counts`，要么用 `.get(key, 0)`。

## 任务清单

右边工作区按 `c1 → c4` 顺序执行，**通过一道才解锁下一道**；改了前面的格，后面的格会退回「待复核」。

**t1 创建列表并用 for 逐个打印**（`c2`）：`regions` 至少放 3 个区域名，用 `for` 逐个 `print`，并把打印次数累加进 `region_lines`（它应等于列表长度）。

**t2 在循环里累加与筛选**（`c3`）：用 `for` 把 `amounts` 累加进 `total_amount`（应为 `2118`），同时把大于 `200` 的金额按原顺序收进 `big_amounts`（应为 `[899, 240, 620]`）。

**t3 用 dict 做分组计数**（`c4`）：遍历 `region_log`，用 `if key in ...` 或 `.get(key, 0)` 把出现次数累加进 `region_counts`，最终 4 个键、计数依次是 3/2/1/1。

## 自检清单

- [ ] `len(regions) >= 3`，且 `region_lines` 与 `len(regions)` 相等（循环真的跑了）
- [ ] `total_amount` 是 `2118`，且等于 `sum(amounts)`
- [ ] `big_amounts` 只留下 `[899, 240, 620]`，顺序没被打乱
- [ ] `sum(region_counts.values()) == 7`，说明每个元素只数了一次

## 下一步建议

- 把 t3 的计数换成「统计每个区域的总金额」：`region_amount[key] = region_amount.get(key, 0) + amount`；随后进入数据分析主线，用 Polars 表达式一次性完成这些分组计算
