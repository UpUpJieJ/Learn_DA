# Agent 评测基线报告（2026-07）

> 阶段 ③ Task 3.2 产出。记录关键词路由 + 关键词检索在离线评测集上的基线数字，
> 作为阶段 ④ Function Calling 改造的对比锚点：④ 的验收要求是在同一评测集上
> **不低于且应显著优于**本基线。

## 运行方式

```bash
cd learn_da
python scripts/eval_agent.py              # 输出意图 + 检索两份报告（纯离线，无网络调用）
python scripts/eval_agent.py --verbose    # 额外列出每条错误用例
python scripts/eval_agent.py --with-embedding   # 可选：embedding 检索对比（需网络与 embedding 配置，手动步骤）
python scripts/eval_agent.py --fc         # 阶段 ④：FC 意图评测（需真实 LLM key，会产生计费，手动步骤）
```

- 数据集：`tests/eval/agent_intent_cases.yml`（41 条）、`tests/eval/agent_retrieval_cases.yml`（18 条）
- 数据集 schema 由 `tests/unit/test_eval_dataset.py` 单测门禁保护
- 输出为确定性结果，重复运行数字一致（已验证两次运行完全相同）

## 基线数字（2026-07-28，commit 阶段 ② 完成后）

### 意图路由（`AgentRouter.resolve()`，关键词规则）

| 指标 | 数值 |
| --- | --- |
| **总体准确率** | **18/41 = 43.9%** |

分 tag 明细：

| tag | 准确率 | 说明 |
| --- | --- | --- |
| chitchat | 5/7 = 71.4% | 闲聊类相对可靠（默认兜底 general_chat） |
| english | 4/6 = 66.7% | 英文关键词部分覆盖 |
| mixed | 2/5 = 40.0% | 中英混合 |
| natural_zh | 7/23 = 30.4% | 自然中文完整问句是最大弱项 |
| broad_keyword | 2/10 = 20.0% | 宽泛词（代码/函数/python/循环）大量误导路由 |
| conflict | 1/7 = 14.3% | 多意图关键词冲突时按规则顺序抢占，几乎全错 |

典型失败模式（`--verbose` 摘录）：

- **规则顺序抢占**："解释这个错误是什么意思" → fix_code（"错误"优先级高于"解释"）；"出一道关于常见报错排查的练习题" → fix_code
- **宽泛词误导**："循环学到一半，明天继续" → generate_example_code（命中"循环"）；"示例数据从哪里下载" → generate_example_code
- **同义词缺失**："给我推荐下一课" → general_chat（词表只有"下一步"）；"帮我 debug 一下这段 SQL" → general_chat；"写一个……的例子" → general_chat（词表只有"示例"）
- **无关键词的语义意图**："为什么我的 join 结果多出了很多行" → general_chat（实为 fix_code）

### 知识检索（`KnowledgeRetriever._keyword_search()`，hit@3）

| 指标 | 数值 |
| --- | --- |
| **总体 hit@3** | **7/18 = 38.9%** |

分 tag 明细：

| tag | hit@3 | 说明 |
| --- | --- | --- |
| cross_lesson | 3/4 = 75.0% | 含明确术语时表现尚可 |
| single_keyword | 3/5 = 60.0% | 术语在多课程复现时排序错误（如 with_columns 排到 polars-basics） |
| sentence_zh | 2/11 = 18.2% | 自然中文整句大面积零召回（连续中文串整体匹配失败） |

典型失败模式：

- **中文整句零召回**：tokenizer 把连续中文切成整段长串（如"我想给数据里每一行按条件打上不同的标签"），无法与 chunk 文本子串匹配 → 0 结果
- **同术语跨课程排序错**："with_columns" 前 3 全是 polars-basics，未命中 polars-expressions；"窗口函数" 前 3 全是 polars-groupby
- **口语与术语脱节**："把两张表按用户编号拼在一起"（join）、"缺失值和重复行"（cleaning）等口语表达零召回

## 阶段 ④ FC 评测结果（2026-07-28）

> Task 4.2 Step 2 门槛评测。FC 形态下意图理解由模型承担，评测口径为
> **强制 function calling 六选一分类**（`classify_intent` 工具 + 强制 tool_choice，
> temperature=0.0），与关键词基线同数据集（41 条）。model=step-3.7-flash，
> 首轮运行结果为 37/41 = 90.2%；本次收尾复核为 38/41 = 92.7%，均通过门槛。模型输出具有合理的非确定性，故不再声称两次结果完全一致。

### 意图分类（FC，`scripts/eval_agent.py --fc`）

| 指标 | FC | 关键词基线 |
| --- | --- | --- |
| **总体准确率** | **37/41 = 90.2%** | 18/41 = 43.9% |

分 tag 明细（括号内为关键词基线）：

| tag | FC 准确率 | 基线 |
| --- | --- | --- |
| chitchat | 7/7 = 100% | 71.4% |
| english | 6/6 = 100% | 66.7% |
| mixed | 5/5 = 100% | 40.0% |
| natural_zh | 19/23 = 82.6% | 30.4% |
| broad_keyword | 8/10 = 80.0% | 20.0% |
| conflict | 5/7 = 71.4% | 14.3% |

关键词路由的两大结构性缺陷（conflict 14.3%、broad_keyword 20.0%）在 FC 下分别提升到
71.4% 和 80.0%，剩余 4 条错误均为语义上确有歧义的边界用例（如"解释这个报错"在
explain_code / fix_code 之间摇摆），不属于系统性失败模式。


### 收尾复核（2026-07-28）

### 检索层说明

FC 路径的 `search_knowledge` 工具与旧路径共用同一 `KnowledgeRetriever.search()`
实现，检索质量由构造保证不劣化，故 hit@3 无需单独重测；sentence_zh 零召回的补救
路径仍是 embedding 检索（`--with-embedding` 手动对比）。

### 门槛判定

**通过。** FC 意图准确率 90.2% ≥ 关键词基线 43.9%（且显著优于），满足计划中
"允许默认开启"的量化门槛 → `AGENT_FC_ENABLED` 默认值已翻转为 `True`
（无 key 时仍确定性降级，行为不变）。

## 结论

1. 关键词路由总体 43.9%：**conflict（14.3%）与 broad_keyword（20.0%）证实规则顺序抢占和宽泛词是结构性缺陷**，词表扩充无法根治——这正是 ④ 用 FC 让模型自主判断意图的动机。
2. 关键词检索 hit@3 38.9%：**sentence_zh 18.2% 确认中文整句近似零召回**，与路线图"已知零召回场景"判断一致；embedding 检索（阶段 ① 已接好持久化缓存）是主要补救路径，可用 `--with-embedding` 手动对比。
3. ~~阶段 ④ 验收时在同一数据集重跑，FC 路径需显著高于本基线。~~ **已完成**：FC 意图 90.2% vs 基线 43.9%，门槛通过，FC 已默认开启（见上文"阶段 ④ FC 评测结果"）。
