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
exercise:
  id: python-functions-add-bonus-v1
  title: 为成绩添加 bonus
  language: python
  starter_code: |
    def add_bonus(score):
        # TODO
        pass
    print(add_bonus(95))
  objective: 定义接收 score 的函数，返回加 5 后的值。
  hints:
    - 先把 score 放在函数参数中
    - 用 return 返回 score + 5
  validator:
    type: stdout_exact
    expected: "100"
# 改版 M4：多 cell 工作区（重放式，严格顺序）
workspace:
  cells:
    - id: c1
      kind: starter
      code: |
        # 起步：先看清「定义 → 调用 → 打印」三步怎么连起来
        def greet(name):
            return "你好，" + name

        print(greet("小明"))
    - id: c2
      kind: task
      task_id: t1
      code: |
        # TODO: add_bonus 返回「分数 + 5」，用 95 调用并存进 bonus_result
        def add_bonus(score):
            pass

        bonus_result = add_bonus(95)
        print(bonus_result)
    - id: c3
      kind: task
      task_id: t2
      code: |
        # TODO: 用 for 循环累加 scores，最后 return 总分（空列表返回 0）
        def total_scores(scores):
            pass

        score_list = [80, 92, 76]
        total_result = total_scores(score_list)
        print(total_result)
    - id: c4
      kind: task
      task_id: t3
      code: |
        # TODO: average_of 借用 total_scores 求平均（空列表 0.0）；grade_of 按 90/75 分档返回 A/B/C
        def average_of(scores):
            pass

        def grade_of(avg):
            pass

        avg_result = average_of([80, 92, 76])
        grade_result = grade_of(avg_result)
        print(avg_result, grade_result)
  tasks:
    - id: t1
      title: 定义带参数的函数并用 return 返回结果
      cell: c2
      objective: 定义 add_bonus(score) 返回 score + 5，用 95 调用并存进 bonus_result 后打印。
      assertions:
        - id: t1-return
          type: expr_true
          title: add_bonus(95) 返回 100
          expr: "add_bonus(95) == 100"
        - id: t1-param
          type: expr_true
          title: 换个数也对：add_bonus(0) == 5、add_bonus(72) == 77
          expr: "add_bonus(0) == 5 and add_bonus(72) == 77"
        - id: t1-variable
          type: expr_true
          title: bonus_result 接到了返回值 100
          expr: "bonus_result == 100"
    - id: t2
      title: 函数里用 for 循环处理列表
      cell: c3
      objective: 定义 total_scores(scores)，函数内用 for 循环累加并 return 总分，空列表返回 0。
      assertions:
        - id: t2-sum
          type: expr_true
          title: total_scores([80, 92, 76]) == 248
          expr: "total_scores([80, 92, 76]) == 248"
        - id: t2-other
          type: expr_true
          title: 换个列表也对：total_scores([1, 2, 3, 4]) == 10
          expr: "total_scores([1, 2, 3, 4]) == 10"
        - id: t2-empty
          type: expr_true
          title: 空列表返回 0（累加变量要先初始化）
          expr: "total_scores([]) == 0"
        - id: t2-variable
          type: expr_true
          title: total_result 接到了 248
          expr: "total_result == 248"
    - id: t3
      title: 把两个函数组合成一个小计算
      cell: c4
      objective: average_of 借用 total_scores 求平均（空列表 0.0），grade_of 按 90/75 分档，再把两者串起来打印。
      assertions:
        - id: t3-average
          type: expr_true
          title: average_of([80, 92, 76]) ≈ 82.667
          expr: "abs(average_of([80, 92, 76]) - 82.66666666666667) < 1e-3"
        - id: t3-empty
          type: expr_true
          title: average_of([]) 返回 0.0，没有除零报错
          expr: "average_of([]) == 0.0"
        - id: t3-grade
          type: expr_true
          title: 等级边界：91→A、76→B、60→C
          expr: "grade_of(91) == 'A' and grade_of(76) == 'B' and grade_of(60) == 'C'"
        - id: t3-print
          type: expr_true
          title: grade_result 是 'B'
          expr: "grade_result == 'B'"
---

# Python 函数入门

函数把重复逻辑封装成一个名字：给它参数，它执行步骤，然后把结果 `return` 给调用方。这一课只讲清三件事——**参数、`return`、调用**，但它们是后面写任何 Python 代码的地基。

## 这节课解决什么问题

要给一门课的每个分数都加 5 分：不封装只能写 `80 + 5`、`92 + 5`、`76 + 5`，规则一改就得逐处改；一百个分数就是一百处。函数把「规则」单独存成一个名字：改一处函数体，所有调用点自动跟着变。

## 函数的三个零件

```python:example
def double(number):
    return number * 2

print(double(21))
```

- `def double(number):` —— `def` 声明定义函数，`number` 是**参数**。
- `return number * 2` —— 把算好的值交回调用方。
- `double(21)` —— 一次**调用**：把 21 塞进 `number`，函数返回 42。

缺哪一件都不成立：没有参数就固定成一个值，没有 `return` 就交不回结果，没有调用则函数一行也不会执行。

## 参数：函数的输入通道

```python:example
def area(width, height):
    return width * height

print(area(3, 4))
print(area(10, 2))
```

- 定义时写几个参数，调用时就按顺序给几个值。
- 同一个函数可以被不同参数反复调用，结果各不相同；参数名只活在函数内部，外面想拿结果只能靠 `return`。
- 参数可以带默认值：`def greet(name, greeting="你好")`，调用 `greet("小明")` 时自动取 `"你好"`。

## return 与 print 的区别

```python:example
def show_bonus(score):
    print(score + 5)       # 只打印：函数返回 None

def calc_bonus(score):
    return score + 5       # 返回 100：结果能继续用

print(calc_bonus(95) * 2)  # 200
```

两条规则记住就够：①函数里没有 `return`，调用结果就是 `None`；②`return` 一执行函数立刻结束，写在它后面的语句不会跑。所以标准姿势是 `bonus_result = add_bonus(95)` 先接住返回值再 `print`——函数忘了 `return` 时，你会在这一行立刻看到 `None`。

## 在函数里用循环

```python:example
def count_passed(scores):
    passed = 0
    for score in scores:
        if score >= 60:
            passed = passed + 1
    return passed

print(count_passed([80, 55, 92, 40]))
```

累加变量 `passed = 0` 要写在循环**外面**，否则每轮都被清零；`return` 也要写在循环**外面**（和 `for` 同缩进），否则函数第一轮就返回了。

## 常见错误

**忘记 `return`** —— 函数体里算了 `score + 5` 却没交出去，调用结果是 `None`；用 `print` 代替 `return` 也一样，屏幕上有了 100 但函数的值仍是 `None`。另一个方向是定义时写了参数、调用时忘给：`add_bonus()` 直接抛 `TypeError: missing 1 required positional argument`。还有一种是把 `return` 写进循环里，只累加了第一个数就返回——要放到循环之后。

## 任务清单

右边工作区按 `c1 → c4` 顺序执行，**通过一道才解锁下一道**；改了前面的格，后面的格会退回「待复核」。

**t1 定义带参数的函数并用 return 返回结果**（`c2`）：定义 `add_bonus(score)` 返回 `score + 5`，用 `95` 调用，把结果存进 `bonus_result` 并打印（应为 `100`）。

**t2 函数里用 for 循环处理列表**（`c3`）：定义 `total_scores(scores)`，用 `for` 累加后 `return` 总分；空列表返回 `0`，`score_list = [80, 92, 76]` 的结果是 `248`。

**t3 把两个函数组合起来**（`c4`）：`average_of` 内部借用 `total_scores` 再除以个数（空列表返回 `0.0`）；`grade_of` 按 `>= 90` → `"A"`、`>= 75` → `"B"`、其余 `"C"`；串起来算出 `[80, 92, 76]` 的平均分与等级并打印。

> 断言直接按名字调用这四个函数，改名或只打印不返回都会判不通过。

## 自检清单

- [ ] `add_bonus(0)` 返回 `5`，说明参数真的被用上了，不是硬编码
- [ ] `total_scores([])` 返回 `0`，没有在循环前忘记初始化累加变量
- [ ] `average_of([80, 92, 76])` 是小数 `82.667` 而不是 `82`（要用 `/`），且能说清 `return` 与 `print` 的区别

## 下一步建议

- 把「加 5 分」改成「加 5 分但不超过 100 分」，练习 `min()` 与条件判断；下一课《Python 集合与循环》会把函数与 list、dict 配合起来做批量处理
