# Learn DA 学习工作区大重构审查报告

> **2026-10-31 更新**：本文原始发现描述 10-26 基线，勿直接当作当前状态。判定迁到后端、13 课结构化断言迁移、workspace 并发/幂等/限流/学习事件、SSE 终态与切课保存已修复；详见 [收口记录](refactor-closeout-2026-10-31.md)。原始 PoC 和统计保留为历史证据。

> 审查日期：2026-10-26
> 审查基线：`main` / `b0ee3d5`（E3 SSE 流式）
> 审查范围：`248528c^..b0ee3d5`，即 2026-10-21 ~ 2026-10-25 的 23 个提交
> 变更规模：**225 文件，+28,707 / −13,575**（新增 105、删除 32、修改 88）
> 相关设计稿：[`learning-workspace-redesign-2026-10-21.md`](learning-workspace-redesign-2026-10-21.md)
> 前次全量审查：[`project-review-2026-07-14.md`](project-review-2026-07-14.md)

---

## 1. 执行摘要

这轮重构是项目自 2026-07 阶段 0–4 以来**最大的一次结构性改动**：把「教程 + 手工勾选 + 一次性 Playground」改成了「确定性数据集 + 多 cell 顺序重放 + 服务端断言判定 + 证据驱动 AI 助手」的工作区模型，并顺手下线了整套旧练习体系（64 文件 / −5,288 行）。方向判断正确，实现质量在工程细节上明显高于上一轮：服务端权威、fail-closed 校验、幂等、路径安全、字节级可复现这些坑基本都提前踩过并留了测试。

但从**「判定结果是否可信」**这个最核心的问题看，这一轮还差最后一层没封死：判定发生在学员代码的同一个 Python 进程里，参考结果和断言运行时都落在学员可读的工作目录中。我在本机用五条最小 PoC 实测确认，**学员可以用 3 行代码把「断言失败」改写成「通过」，并直接读到全部参考结果**。这直接冲击本轮重构的核心承诺（"任务判定只有断言 DSL v2"、"参考结果服务端内存注入、不落用户可见路径"）。

成熟度判断：**内部 Alpha 站得住，公开 Beta 还差一个「判定不可伪造」的隔离层**。其余问题以并发幂等、限流缺口、前端流式状态机为主，属于可控的工程债。

补审 UI 层（5.5）之后还有一条值得单独说明：**页面重构把旧页面删掉时带走了整条 `/analytics/track` 上报链路**（P1-22）。前端现在没有任何地方调 `trackEvent`，于是 `lesson_start`/`lesson_complete`/`code_run` 四类事件全部断供，推荐系统的三条回补信号恒假、顶栏「已完成 N 课」永久为空。这不是文案问题，是**功能性缺失**，而且 507 个后端测试和 143 个前端测试都没发现——因为测的都是"函数被调用时行为正确"，没测"还有没有人调用它"。

### 五条最该先做的事

1. **把判定搬出学员进程**（P0-1/2/3，方案见附录 A）：这是本轮唯一的安全级缺陷。注意**不是**"参考结果不进沙箱目录 + 运行时提前加载 + 回传加 nonce"这类局部补丁——这三条我都实测过，全部无效（学员可 `sys._getframe` 爬栈、可 `import __main__` 改模块属性）。唯一有效的是进程隔离。
2. **改造 `expr_true`**（P0-6）：87 条断言里有 71% 是 `expr_true`，它本质是"在学员可控命名空间里求布尔表达式"，鸭子类型即可绕过，且**进程隔离也救不了它**。其中 66 条（数据课）可迁到 `frame_equal`/`schema`，21 条（纯 Python 课）需改成"固定输入调用函数"的结构化断言。详见附录 A.3。
3. **补幂等键与限流**（P0-4、P1-3）：`(visitor_id, request_id)` 不足以区分 run/submit/session；workspace 8 个端点完全没有限流，而它们是最贵的（直连 Runner）。
4. **修前端流式终态语义**（P0-5）：`error(partial)` 后紧跟的 `done` 会把学员已经看到的整段回答换成「AI 助手暂时不可用」，这是本轮最容易被用户直接看见的回归。
5. **把 `/analytics/track` 的写入责任挪到服务端**（P1-22）：页面重构删旧页面时把上报链路一起删了，推荐与顶栏进度已经静默失效两周。最省事的修法是 `submit_task` 成功时由服务端直接落 `LearningRecord`，别再依赖前端上报。

---

## 2. 这轮重构做了什么

### 2.1 提交序列（新 → 旧）

| 提交 | 日期 | 主题 |
| --- | --- | --- |
| `b0ee3d5` | 10-25 | E3 对话改为真 SSE 流式，中断不丢已生成内容 |
| `f781aae` | 10-25 | 接通断言预期结果管线（refs），20 条手抄魔数换成逐行比对 |
| `ff4b325` | 10-25 | E2 分级提示：层级按真实失败次数算，读真实报错 |
| `1fbecf7` | 10-24 | 工作区重放超时配置 + 数据集预算对齐 |
| `9717ae1` | 10-24 | **下线旧练习体系**（breaking） |
| `fc862c7` | 10-24 | 改名「AI 助手」、去掉「下一步该练什么」引导 |
| `5a2cf29` | 10-24 | E1 助手接进工作区右栏 |
| `54fda02` | 10-23 | 证据链改读工作区任务提交（breaking） |
| `8640c2d` | 10-22 | 首页重构为「今日」 |
| `3b9dc66` | 10-22 | docs：M4 与页面重构记录 |
| `d35e044` | 10-22 | 页面重构 P1/P3/P4，下线旧页（breaking） |
| `bf56fdc` | 10-22 | 课程进度与学习报告接口 |
| `b888fb6` | 10-22 | 13 门课全部迁到工作区格式（breaking） |
| `45671d9` | 10-22 | M3 前端三栏工作区 |
| `f733ad7` | 10-22 | M1+M2 后端工作区 + Runner 会话执行 |
| `27300d1` | 10-21 | 数据集禁用行尾转换 |
| `7fa60bc` | 10-21 | M0 确定性数据集 + v2 断言 DSL 骨架（breaking） |
| `c45b86a` | 10-21 | 语义设计 token + 基础组件层 + ui_lint |
| `0103a4b` | 10-21 | 改版设计稿 |
| `74cd27f` | 10-21 | 移除误提交的 `.pytest_tmp` |
| `74ea621` | 10-21 | 删 FALLBACK_LLM_*，让 RATE_LIMIT_ENABLED 真正关掉限流（breaking） |
| `773f72c` | 10-21 | 锁定 polars/duckdb 版本 |
| `248528c` | 10-21 | Runner 新增 local 执行后端 |

### 2.2 变更分布

| 区域 | 文件数 | 增/删 |
| --- | --- | --- |
| `learn_da_vue/src` | 65 | +5,992 / −7,654 |
| `learn_da/app` | 38 | +4,233 / −1,871 |
| `learn_da/content` | 29 | +9,576 / −1,268 |
| `learn_da/tests` | 33 | +3,703 / −2,497 |
| `learn_da/scripts` | 18 | +1,279 / −2 |
| `learn_da/migrations` | 3 | +274 / −0 |
| `learn_da_runner/runner` | 8 | +877 / −9 |
| `learn_da_runner/tests` | 2 | +312 / −0 |
| `deploy/acceptance.sh` | 1 | +361 / −132 |

新增核心模块行数：`app/workspace/service.py` 579、`hints.py` 366、`progress.py` 345、`content.py` 344、`repository.py` 304、`router.py` 170、`models.py` 155、`schemas.py` 111；`app/practice/assertion_runtime.py` 316、`assertions.py` 305；`app/agent/llm_client.py` 441、`service.py` 1035、`evidence.py` 310。

前端 41 个源文件（不含 spec）共 5,657 行，本轮新增/重写的页面：`Home.vue` 711、`LessonWorkspace.vue` 532、`Lab.vue` 417、`Report.vue` 370、`CourseMap.vue` 221，`src/components/ui/` 8 组件 572 行。

### 2.3 内容侧产出（实测统计）

13 门课共 **51 个 cell / 38 个任务 / 122 条断言**：

- 类型分布：`expr_true` **87**、`schema` **25**、`frame_equal` **10**、`sql_rows` **0**
- 参考结果：`content/expected/` 下 **10 个 parquet**，覆盖 8 门课（01/02/03/06/07/08/10/11），04/05/09/12/13 无 ref
- 数据集：`content/datasets/ecommerce/` 5 个 CSV + `manifest.json` + README（seed 20251021，`--check` 校验 sha256）
- 逐课明细：01 4c/3t/10a、02 4/3/7、03 3/2/5、04 4/3/12、05 4/3/12、06 4/3/9、07 4/3/8、08 4/3/10、09 4/3/9、10 4/3/10、11 4/3/9、12 4/3/11、13 4/3/10

---

## 3. 架构评价

### 3.1 新的判定链路

```
浏览器（LessonWorkspace.vue + stores/workspace.ts）
   │  800ms 去抖 PUT /cells/{id}          POST /cells/{id}/run | /tasks/{id}/submit
   ▼
FastAPI（app/workspace/router.py，prefix=/workspace）
   │  WorkspaceService：visitor 隔离 / 幂等 / TaskAttempt 落库 / 状态机
   ▼
RunnerClient（app/sandbox/client.py）── POST /v1/sessions（X-Runner-Token）
   ▼
learn_da_runner（provider=docker）
   │  prepare_workspace：driver.py + assertion_runtime.py + plan.json + data/
   │  Docker：network=none / read_only / uid 65532 / cap_drop ALL / mem 256m / pids 64
   ▼
session_driver.py：按 position 顺序 exec → 失败 break → 断言求值 → print(MARKER+json)
```

这条链路的**分层是对的**：判定规则在 Python（`assertion_runtime.py`），LLM 只负责表达（`app/agent/prompts.py` + `service.py`），前端只负责呈现。这与上一轮「模型自己决定说什么」相比是实质进步。

### 3.2 三个结构性判断

**① 用「整段重放」代替「单格执行」是对的，但代价被低估了。**
顺序重放让「改上游代码 → 下游失效」变成天然的语义（`service.py:245-260` 只置 `stale`，不删历史 `TaskAttempt`），这比上一轮"练习 validator 只看单次 stdout"强得多。代价是每次 run/submit 都要重跑最多 40 个 cell（`content.py` `MAX_CELLS=40`），而 Runner 侧 `RUNNER_SESSION_TIMEOUT_SECONDS=20` 是**整段**预算（`learn_da_runner/runner/settings.py`）。当前 13 课最多 4 个 cell 没问题，但 `MAX_CELLS=40` 与 20 秒的组合在内容规模化后会先撞墙。

**② refs 走「请求体内联 base64」是正确选择，但注入点选错了层。**
`content.py:332-337` `refs_payload()` 从服务端读，execute 请求体只有 cells/requestId —— 客户端**无法**伪造 ref（这点做得很干净，`tests/unit/test_workspace_refs.py:77-97` 守着路径安全）。但 refs 从后端到沙箱的路径是 `service.py:_run` → plan 的 `refs` 字段 → `session.py:83-95` 写进 `<work>/plan.json` → driver 以 `work` 为 cwd 读取。**「客户端不可伪造」和「沙箱内不可读」是两件事**，本轮只做到了前者，而设计稿 §207/§232/§387/§559 宣称的是后者（"服务端内存注入，不落用户可见路径"）。这是文档与实现的直接矛盾，也是 P0-3 的来源。

**③ 分级提示的「层级只由服务端算」是这轮最干净的设计。**
`hints.py:102-106` `compute_level(failures_since_last_hint, hints_used) = min(3, 1 + hints_used + failures//2)`，客户端不传层级（`router.py:153` hint 端点无请求体），越层请求天然无效。配合 `request_hint` 读单元格真实 stderr（`service.py:298-330` `_latest_run_failure` → `hints.normalize_error` 折叠重复异常前缀 → 把 `valid columns` 列给学习者），"不能把断言未求值当诊断结论"这条约束真的落到了代码里。**唯一瑕疵是公式在 `repository.py:222-232` 的 docstring 里写错了**（写成 `1 + failures + hints_used`，缺 `//2`），后人照注释改代码就会破坏层级节奏。

---

## 4. 做得好的部分

这一轮有大量值得保留的工程习惯，列出来是为了**下次别退化**：

1. **服务端权威贯彻到底**。refs 从服务端读（`content.py:332-337`）、层级服务端算（`hints.py:102`）、证据只读 `task_attempts`（`evidence.py`）、`teachingFeedback` 的 state/nextAction 服务端决定。客户端自报的 stdout/stderr 不作为事实来源。
2. **fail-closed 而不是 fail-silent**。内容 frontmatter 坏 YAML 阻断启动（`content_loader.py`）、`catalog.yml` 损坏阻断、prerequisites 环检测阻断、L7 缺 expected 阻断、`ENABLED_APP_MODULES` 漏配直接 404（而非半可用）。
3. **字节级可复现**。`build_datasets.py --check` 比对 sha256、`build_expected.py --check` 比对参考结果、`.gitattributes` 对 `datasets/`、`expected/` 设 `-text`、固定 `POLARS_MAX_THREADS=1`（否则分组聚合浮点末位不稳）。`tests/test_build_datasets.py` 守着。
4. **路径安全做了两层**。`content.py:148-166` `_resolve_expected_path`（只校验路径/扩展名）+ `:169-178` `_safe_expected_path`（额外要求 `is_file` 且 ≤ 200KB），有单测。Runner 侧 `session.py:43-54` `_safe_relative` 挡 `/`、`\`、`..`（Windows drive 逃逸漏了，见 P1-2，但方向是对的）。
5. **缓存按 (mtime_ns, size) 失效**。`content.py:303-340` `_cached_payload`，避免热路径反复读盘又不会读到陈旧数据，有单测。
6. **事务兼容测试外层事务**。`service.py:67-72` `_commit()` 在 `db.info["external_transaction"]` 下只 `flush()`，不炸 "closed transaction"。这个细节很容易漏。
7. **访客隔离每一层都过滤**。`service.py:94-97` `_session`、`_cached_run`、`repository.py` `latest_run_payload` 全部带 `visitor_id`，跨访客越权在验收脚本 A9 里有专门场景。
8. **超时对齐有测试守护**。后端 `RUNNER_SESSION_TIMEOUT_SECONDS=30` > Runner 20（`config/settings.py:70`），`tests/test_dependency_pins.py:135-157` 守着不让它反过来。
9. **SSE 已吐字后不重试**。`llm_client.py:157-270` 用 `emitted` 门控，中断走 `interrupted=True` + `partial` 收尾，不会让学员看到重复开头。这是流式最容易做错的地方。
10. **验收脚本随链路重写**。`deploy/acceptance.sh` A1–A13 覆盖真实执行、起步必失败、参考解必过、幂等、进度、证据、失效传播、track 幂等、分级提示、SSE，29 项断言。
11. **UI 规范可执行（但有洞）**。语义 token + `src/components/ui/` 基础层 + `ui_lint.baseline.json` 只拦新增违规，基线从 558 处收敛到 14 处。**但规则本身有三个盲区**（漏 `slate/gray/zinc/neutral/stone` 整套中性色、"UI 组件零容忍"跨平台不一致、`--update-baseline` 可一次性固化），且 `ui_lint` 无单测 —— 详见 5.5.1。
12. **下线做得干净**。`9717ae1` 全仓 grep `practice.repository/service/validator/router/schemas`、`PracticeService`、`VerificationResult`、`ALLOWED_VALIDATOR_TYPES` 零命中；`exercise_attempts` 表冻结只读（仅 `model_registry.py:19` 登记给 Alembic，无写入点）；Alembic 单头；旧端点前后端与验收脚本均无残留。
13. **组件层有真无障碍意识**（虽然还没做完）。`AppInput` 用 `useId()` 关联 label 并带 `aria-invalid`；`ToastHost` 有 `role="status" aria-live="polite"`；`EmptyState` 把 `cta` 设为必填 prop，从组件层面强制"空态带下一步"；`ConfirmDialog` 打开时焦点落取消按钮、`onBeforeUnmount` 移除监听。缺的部分（焦点陷阱、`aria-live` 播报输出、对比度）见 5.5.4 的 C-1/C-5/C-11。

---

## 5. 问题清单

严重度定义：**P0** = 判定可被绕过 / 数据可丢失 / 用户可见的明显错误；**P1** = 安全或一致性有实质缺口，但需要特定条件触发；**P2** = 性能、可维护性、边界情形；**P3** = 注释漂移、文案、可复现性细节。

### 5.1 P0 —— 判定可伪造（本轮唯一安全级缺陷）

**P0-1、P0-2、P0-3、P0-6 同源**：判定与学员代码共享同一个进程、同一个工作目录。前三项是"绕过判定机制"，P0-6 是"判定机制本身的表达能力不足以判定"。四项都有本机 PoC，可直接转成回归测试。P0-4（幂等键）与 P0-5（前端终态）是另外两类：一个会丢证据，一个会把学员读到的回答换掉。

#### P0-1 学员可以伪造 driver 回传的 marker 行

`learn_da_runner/runner/session.py:98-106`

```python
def parse_driver_output(stdout_text: str, marker: str) -> dict[str, Any] | None:
    for line in reversed(stdout_text.splitlines()):
        if line.startswith(marker):
            ...
```

只认"最后一行 MARKER"。而 driver 是 `print(MARKER + json.dumps(payload))` 写到被重定向的 stdout，学员代码可以在自己这一格里注册 `atexit.register(lambda: print(MARKER + fake))`，驱动打印之后 atexit 再补一行，反向扫描取到的就是伪造结果。

**实测（本机 PoC）**：构造一个断言真实失败的 plan，学员格里加 3 行 atexit 伪造，`parse_driver_output` 返回 `verdict: "passed"`。stdout 里确实出现两行 marker，取到的是后一行。

**注意**：单靠"MARKER 掺 nonce"挡不住这个攻击。nonce 若随 plan 下发就落在 `plan.json` 里，学员 `json.load(open('plan.json'))` 就能读到并原样打印（P0-3 已实测 plan 可读）；即使 nonce 不经磁盘传递，也能用 `sys._getframe` 从 `run_plan` 的局部变量里爬出来（见下方 P0-2 的 frame 爬取实测）。**nonce 只能挡住"盲打印固定串"的随手伪造，挡不住有心读取的学员。**

真正有效的方向是把**判定结论**移出学员进程（详见附录 A）：driver 不再自己算 verdict，只回传变量值，由宿主持有 refs 并判定；这样学员无论怎么伪造 stdout，伪造的都只是自己的输出，不是判定。

#### P0-2 学员可以在同进程内替换断言运行时

`learn_da_runner/runner/session_driver.py:167` 在**所有 cell 执行完之后**才按 cwd 加载 `assertion_runtime.py`：

```python
runtime = _load_assertion_runtime(root / runtime_file)
```

而 `_load_assertion_runtime` 是通过 `__main__` 上的函数名解析的（driver 自身即 `__main__`）。学员格只要写：

```python
import __main__
__main__._load_assertion_runtime = lambda path: FakeRuntime()
```

**实测**：全部断言被判 `passed`，`verdict: "passed"`。更隐蔽的变体是猴子补丁 `importlib.util.spec_from_file_location` + `importlib.util.module_from_spec`，同样能换掉 runtime。

**并且"提前加载 runtime 并完成闭包绑定"这个直觉改法也堵不住**。真实 driver 里 `_load_assertion_runtime` 是模块级函数、通过全局名字查找，所以"改上层帧局部变量"这个变体实测**不成立**；但学员格写

```python
import __main__
__main__._load_assertion_runtime = lambda path: FakeRuntime
```

直接改模块属性，**实测成立**。同理 `sys._getframe(2).f_locals['plan']` 能读到 `run_plan` 的完整 `plan`（含 `refs`），**实测成立**（见 PoC-2b）。

**结论：只要学员代码与判定逻辑同进程，任何"加载顺序"或"闭包绑定"层面的加固都不成立。** 这是 P0-1/2/3 的共同根因，必须用进程隔离（附录 A）解决，不能用局部补丁。

> 附：这五条 PoC 已整理成可复现脚本 `learn_da_runner/scripts/poc_judgement_bypass.py`（见附录 A.5），在真实 `session_driver.py` 上 5/5 全部成立。

#### P0-3 参考结果（refs）落在学员可读的工作目录

`learn_da_runner/runner/session.py:83-95` 把 refs 的 base64 写进 `<work>/plan.json`，driver 以 `work` 为 cwd。

**实测**：学员格 `json.load(open('plan.json'))` 直接读到 `['assertions','cells','refs','runtimeFile','stopAt']`，以及 `plan['refs'].keys()`（如 `expected/groupby.parquet`）。拿到参考结果后赋值给断言检查的变量，`frame_equal` 必然通过。

这与三处文档宣称直接矛盾：
- `app/practice/assertions.py:7-8` 模块 docstring："参考结果内存注入：ref 以 base64 内联，学员的沙箱目录里看不到 `expected/`"
- `scripts/build_expected.py` 文档
- 设计稿 `learning-workspace-redesign-2026-10-21.md:207`（"服务端内存注入，不落用户可见路径"）、`:232`（"弱保证说明"）、`:387`（"不读 expected/（内存注入）"）、`:559`（"内存注入不落盘"）

设计稿 `:232` 只承认"弱保证：断言与学员代码同进程，理论上可读父进程内存"——**但 plan.json 不是父进程内存，是一个明文文件**，这个降级说明掩盖了实际暴露面。

**即使 refs 不落盘，也挡不住**。实测：学员格 `sys._getframe(2).f_locals['plan']` 直接拿到 `run_plan` 的 `plan` 局部变量，其中 `refs` 键完整可读（`['expected/secret.parquet']`）。**把 refs 改成 stdin/fd 传入只能抬高成本，不能消除暴露**——只要它在判定进程的内存里，同进程的学员代码就能沿栈爬到。

建议（按有效性排序）：
1. **进程隔离（唯一有效，见附录 A）**：refs 与判定都在宿主进程，学员容器只回传变量值。实测该方案下学员 `json.load(open('plan.json'))` 只看到 `['assertionVars','cells','nonce']`，`has refs? False`。
2. 若短期不做进程隔离，**至少改文档**，把"不落用户可见路径"改成"落在工作目录且可被同进程读取，属已知弱保证"，不要让设计稿继续宣称做不到的事。
3. 单靠"refs 改 stdin 传递"不足以修复，不要把它当成解决方案。

#### P0-4 幂等键不足：run 与 submit 混用会跳过 TaskAttempt 落库

`learn_da/app/workspace/service.py:411-413`

```python
cached = await self._cached_run(visitor_id, request_id)
if cached is not None:
    return RunResponse.model_validate(cached)
```

`_cached_run` 只按 `(visitor_id, request_id)` 命中，而 `run_events` 的唯一约束也是 `uq_run_visitor_request`（`models.py`）。幂等命中的返回发生在**任何校验之前**，因此：

- 同一 requestId 先 `run`（`record_attempt=False`）再 `submit`（`record_attempt=True`）→ 第二次直接返回缓存，**`TaskAttempt` 不落库**，学员提交了但没有证据。
- 同一 requestId 用在另一个 session/cell 上 → 返回**别的会话**的结果（虽然 visitor 相同，但 `session_id`/`cell_id` 都对不上）。
- `RunResponse` 里带 `session_id`，返回体本身会暴露这种错配。

建议：幂等键补 `(session_id, cell_id, task_id, record_attempt)`，不一致时返回 409 而不是静默还原；或者给 `run_events` 加 `kind` 列参与唯一约束。

#### P0-5 前端用 `done` 的降级文案覆盖学员已看到的回答

后端 `learn_da/app/agent/service.py:541-556`：

```python
if streamed_chars:
    # 已经吐过字，不能再补一段「不可用」的假回答盖上去
    yield {"type": "error", "reason": fallback_reason, "partial": True}
    data = AgentChatData(content=fallback_content, ...)   # ← 降级文案
    yield {"type": "done", "data": data.model_dump(by_alias=True)}
```

注释说不盖，但 `done.data.content` 就是 `_fallback_chat_content(tool_name)`。前端 `learn_da_vue/src/composables/useAgentConversation.ts:104-108`：

```ts
onDone: (fullReply, ...) => {
  if (msg) {
    msg.content = fullReply || msg.content;   // ← 整段替换
```

于是**学员已经读完的半段回答被替换成「AI 助手暂时不可用」**，`onError(partial)` 刚补上的"（不完整）"提示也被吞掉。

同一根因还有两处：`service.py:435` interrupted 分支只回填本轮 `text`，若中断发生在第 2 轮，第 1 轮工具轮的前言被覆盖；前端 `learn_da_vue/src/api/agent.ts:153-155` 用户点「停止」时抛 `CancelledError` 但不带 `partial`，`useAgentConversation.ts:118-127` 走 else 分支整段替换成失败文案，把"已吐文本 +（已停止生成）"覆盖掉。

建议：① 后端 `done.data.content` 在 partial 场景下发**跨轮累积全文**，不要下发降级文案；② 前端在 `interrupted`/`partial` 时不覆盖，只追加提示；③ `onError` 区分 `CancelledError`。

#### P0-6 `expr_true` 判定的是「学员自己给的对象」，鸭子类型即可绕过

`learn_da/app/practice/assertion_runtime.py:197-204`：

```python
value = eval(expr, {"__builtins__": _SAFE_BUILTINS}, dict(namespace))
passed = bool(value)
```

`_SAFE_BUILTINS`（`:30-36`）限制了可用内建，`assertions.py:92-95` 也拦了 `__` 双下划线。但这些都在拦"表达式能调用什么"，没有拦"**表达式比较的是什么**"——`namespace` 里的变量完全由学员赋值。

**实测（本机 PoC）**：学员格里定义

```python
class Always:
    def __getattr__(self, name): return Always()
    def __eq__(self, other): return True
    def __ne__(self, other): return False
    def __hash__(self): return 0
region_stats = Always()
```

则真实断言 `expr: "region_stats.height == 4"`（`polars-groupby` 的 `t1-rows`）被判 **`passed`**。因为 `region_stats.height` 返回 `Always()`，`Always() == 4` 命中自定义 `__eq__` 返回 True。

同一 PoC 里 `expr: "region_stats['revenue'].to_list() == sorted(...)"` 报 `TypeError: 'Always' object is not subscriptable` —— 只是因为这个假类还没实现 `__getitem__`，补上即绕过。

**这一项比 P0-1/2/3 更根本**：前三个是"绕过判定机制"，这一项是"判定机制本身不成立"。`expr_true` 的语义是"在学员可控的命名空间里求一段布尔表达式"，只要被比较的对象由学员定义，比较结果就由学员决定。**即便按附录 A 把判定搬到宿主进程，`expr_true` 依然可伪造**——因为它需要学员定义的函数与对象参与运算（实测 87 条 `expr_true` 里有 `add_bonus(95) == 100`、`total_scores([80,92,76]) == 248`、`grade_of(91) == 'A'`，这些函数无法序列化到宿主）。

当前内容实测分布：**`expr_true` 87 条 / `schema` 25 条 / `frame_equal` 10 条**（共 122 条）。也就是说 71% 的断言落在这一类。

建议（两条并行，见附录 A.3）：
1. **短期**：`expr_true` 只在"被比较对象是宿主可校验的结构"时才可信。把课程内容里"比较 DataFrame 形状/内容"的 `expr_true` 逐步迁移到 `frame_equal`/`schema`（这类断言本就该用结构化类型表达）。
2. **中期**：给 `expr_true` 加**类型契约**——断言声明被比较变量的期望类型（如 `var: region_stats, expect_type: polars.DataFrame`），运行时先 `isinstance` 校验再求值；对 `polars.DataFrame` 强制走 `frame_equal` 而不再允许任意表达式。纯 Python 课（12/13）的函数类断言则改造成"用固定输入调用函数并比对返回值"，即把 `expr_true: add_bonus(95) == 100` 换成结构化断言 `call: add_bonus(95), expect: 100`，由宿主侧用**已知输入**调用并比对，学员无法在中间插入对象。

### 5.2 P1

| # | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| P1-1 | `learn_da/app/practice/assertion_runtime.py:301-308` | `sql_rows` **只比行数不比列数**：`if len(got_rows) != len(ref_rows)` 之后用 `zip(row, want)` 逐列比，行长不等时静默取短。学员多选或少选列，只要前 N 个对上就 `passed`。`_check_sql_rows` 完全忽略 `_RefTable.columns`。`frame_equal` 无此问题（`:218` 先查列数） | 逐行 `len(row) != len(want)` 即 failed，并把 ref 的 columns 作为列名断言 |
| P1-2 | `learn_da_runner/runner/session.py:43-54` | `_safe_relative` 只挡前导 `/`、`\`、`is_absolute()`、`..`；**实测 `_safe_relative('D:evil.csv')` 与 `'C:evil.csv'` 都原样返回**，`work/'data'/rel` 变成 `D:evil.csv` / `C:evil.csv` —— 盘符前缀把路径锚定到该盘的当前目录，**脱离 `work` 目录**。docker 下 `/work` 只读 + 容器内无 C/D 盘会挡住，但 local provider 与 dev 环境不挡 | 追加 `if PureWindowsPath(name).drive: raise` |
| P1-3 | `learn_da/app/workspace/router.py:39/48/57/74/89/109/131/153` | **workspace 8 个端点全部没有 `@limiter.limit`**。全仓只有 5 处限流：agent chat（`agent/router.py:73,95`）、analytics（`analytics/router.py:26`）、learner_state（`learner_state/router.py:27`）、playground（`playground/router.py:28`）。而 `app/utils/limiter.py:30` 构造 `Limiter` 时**没传 `default_limits`**，`RATE_LIMIT_GLOBAL_IP`（200/min）与 `RATE_LIMIT_DEFAULT`（60/min）在 `config/settings.py:32-33` 定义但全仓无引用 → 全局兜底限流实际不存在 | workspace 的 run/submit/hint 必须挂限流（它们直连 Runner，是最贵的端点）；给 `Limiter` 补 `default_limits`，让两个配置真的生效 |
| P1-4 | `learn_da/app/workspace/service.py:123-145` | `get_or_create` 并发首次建会话撞 `uq_session_visitor_lesson`，`_commit()` 抛 `IntegrityError` → 500（同一学员双标签页首开同一课即可触发） | 捕获 `IntegrityError` 后回查并复用，或先 `INSERT ... ON CONFLICT DO NOTHING` |
| P1-5 | `learn_da/app/workspace/service.py:529-542` | `run_events` 有 `uq_run_visitor_request` 但插入前不判重，并发同 requestId 第二个 `_commit` 抛 `IntegrityError`，**连带已 add 的 TaskAttempt 一起回滚** → 提交证据丢失 | 先查后插 + 捕获 IntegrityError 走缓存还原；或把 RunEvent 插入放到 TaskAttempt 之后独立提交 |
| P1-6 | `learn_da/app/workspace/service.py:348-371` | `request_hint` 无幂等键，`hint_usages` 无唯一约束（迁移 `b9c2e5a17f03` 只建表+索引）。双击并发各写一条 `level=1`，`hints_used` 永久多算一层，层级节奏被破坏 | 请求体加 `request_id`（或复用 `X-Request-ID`），`hint_usages` 加 `(visitor_id, request_id)` 唯一约束 |
| P1-7 | `learn_da/app/workspace/service.py:468-474` | 回写格子状态用的是 **Runner 调用前**的 `cells` 快照。期间 PUT 改码后仍按旧结论置 `ok`（覆盖 `stale`）；上游格失败时下游旧的 `ok` 也不失效 | 执行结束后重读 cells；未出现在 `cell_results` 的格一律 `stale` |
| P1-8 | `learn_da/app/agent/llm_client.py:300` | `slot["name"] += name` 对工具名做字符串累加。vLLM 每片重发同一 `name` 会拼成 `get_task_summaryget_task_summary` | name 首次非空即定值，只有 `arguments` 累加 |
| P1-9 | `learn_da/app/agent/llm_client.py:193-207` | 流循环**从不读 `finish_reason`**（全仓 grep 无命中）。上游断连或 `finish_reason="length"` 被截断时按 `error_reason=None` 下发 `done`，上层当完整回答（`used_fallback=False`） | 非 `stop`/`tool_calls` 一律 `interrupted=True` + `error_reason="truncated"` |
| P1-10 | `learn_da/app/agent/llm_client.py:186` | `async with asyncio.timeout(self.timeout_seconds)` 包住**整个流**而非单次读。思考模式首字约 5.8s，长讲解必撞总时长，正常回答被截成半截 | 改为逐迭代重置的空闲超时 |
| P1-11 | `learn_da/app/agent/evidence.py:179-186` | `_guess_task` 固定 `return spec.tasks[0].task_id`。学员已过 task1、正在做 task3 时注入 task1 的旧提交，与算出的 `current_task_id` 自相矛盾 | 无 `task_id` 时用 latest attempt（不限任务），或直接用已算出的 current_task |
| P1-12 | `learn_da/app/agent/prompts.py:63`、`:179` | `build_recent_runs_block` 把 `run.stderr_first_line[:200]` 原样拼进 **system 层**；`actual` 同理。两者都是 Runner 捕获的学员 `print` 输出 → 学员可在 stderr 写「忽略以上指令」，提升提示注入成功率 | 不可信数据加定界符 + 过滤行首 `#`/`system`/`assistant` 标记；或把 recent_runs 降级进 user 消息 |
| P1-13 | `learn_da/app/agent/service.py:190`、`:338` | 两处 `RecommendationService(repository=LearningRepository(), ...)` **没传 `workspace_repo`**（只有 `app/learning/router.py:36-42` 传了）→ `recommendation.py:595` 与 `:684` 的"失败回补"信号在 Agent 路径恒跳过，Agent 与 /learning 的推荐口径分叉 | 统一在一处构造并注入 |
| P1-14 | `learn_da_runner/runner/provider.py:290-304` | `_split_logs` 恒 `return text, ""`。`container.logs(stdout=True, stderr=True)` 在非 TTY 下 SDK 已按 8 字节头拆包再 `sep.join`，stderr 实际混在同一串里 → `driver_protocol_error` 分支的 `(stderr_text or stdout_text)` 永远只有混合流，**分级提示读到的"真实 stderr"在 docker 下其实是混合输出** | `logs(demux=True)`，或明确改契约并在 `hints.normalize_error` 侧适配 |
| P1-15 | `learn_da_vue/src/stores/workspace.ts:194` | `reset()` 只清状态、不隔离在途请求。切课后旧 `runCell`/`submitTask`/`flush` 的响应写回 `snapshot`/`runs`，`finally` 还把新课程刚占的 `runningCellId`/`submittingTaskId` 置 null → 新课程可以连点重复执行 | store 内加 `epoch`/`sessionToken`，每次响应回来先比对，不匹配直接丢弃 |
| P1-16 | `learn_da_vue/src/views/LessonWorkspace.vue:528-530` | `void store.flushAll(); store.reset();` —— 不 `await` 就 reset，在途保存晚到会把旧课程快照写进新课程 | `onBeforeUnmount` 里改为 `store.destroy()`，内部 await 完再 reset 并置 token 失效 |
| P1-17 | `learn_da_vue/src/stores/workspace.ts:100` | `flush` 用 `updateCell` 返回的**整份快照**替换 `snapshot`，回滚其他格正在编辑的本地文本（光标跳到别处） | 只合并被更新的那一格，或比较 `updatedAt` |
| P1-18 | `learn_da_vue/src/components/workspace/WorkspaceAssistant.vue:295-299` | 切任务/切格只 `clearMessages`，**不停流、卸载也不 abort**（全仓 `src/composables/`、`src/components/workspace/` grep `onScopeDispose\|onUnmounted` 零命中）。旧 SSE 继续消耗 token 并写进已清空的列表 | `useAgentConversation` 里加 `onScopeDispose(() => abortController?.abort())`；切上下文先 `stopStreaming()` |
| P1-19 | `learn_da_runner/runner/main.py:42-48` + `docker-compose.runner.yml:16-25` + `deploy/runner.env.example` | production 拒绝 local 后端是 **fail-open**：guard 读 `RUNNER_ENV or APP_ENV`，而 runner 容器只加载 `deploy/runner.env`，`runner.env.example` **没有 `RUNNER_ENV`**，compose 的 `environment:` 也没有 → 两者皆空即放行。同一处还漏了 `RUNNER_SESSION_TIMEOUT_SECONDS` 与 `RUNNER_SESSION_MAX_DATASET_BYTES`（走 settings 默认值，能跑但运维不可见） | 白名单化：`environment` 不在 `{development, test}` 即拒绝 local；compose 显式注入 `RUNNER_ENV=production` 与两个 session 配置 |
| P1-20 | `learn_da_runner/runner/local_provider.py:219-221` | 会话异常分支只 `proc.kill()` 不 `wait()`（timeout 分支 `:203-209` 有 `proc.wait(timeout=5)`），Windows 上句柄泄漏 | 补 `proc.wait(timeout=5)` |
| P1-21 | `learn_da_vue/src/composables/useAgentConversation.ts:89` | 调 `sendChatMessage` **不传 `requestId`**，注释宣称的"稳定 requestId 幂等"实际不生效（每次 `randomId()`）→ 重复提问重复计入 `ai_help`，`_reserve_interaction` 的幂等短路永远不触发 | 每次用户发问生成一个 requestId 并在重试时复用 |
| P1-22 | `learn_da_vue/src/stores/learnerState.ts:118/123/128` | **`/analytics/track` 全链路断供**。三个写方法（`completeLesson`/`uncompleteLesson`/`recordLessonStart`）与 `isLessonCompleted` 在 `src/` 内**零调用点**——它们唯一的调用者 `useLessonSession.ts` / `usePlaygroundSession.ts` 被 `d35e044` 删除，而 `Lab.vue` / `LessonWorkspace.vue` grep `trackEvent\|analytics` 均为 0 命中。后果：`lesson_start`/`lesson_complete`/`lesson_uncomplete`/`code_run` 四类事件**前端再无上报路径**，`analytics/service.py:85-96` 的 LearnerState 联动成死代码，`LearnerLessonProgress` 表不再被写 | 工作区提交任务成功、Lab 运行成功时应由服务端（而非前端）直接落 `LearningRecord`，或在前端两个新页面补回上报；顺带修 `Navbar.vue:68-71` 与 `:217` 的永久空态（见 5.5） |

### 5.3 P2

| # | 位置 | 问题 |
| --- | --- | --- |
| P2-1 | `learn_da/app/workspace/service.py:245-260` + `repository.py:289-297` | 每次 800ms 去抖 PUT 都跑完整 `snapshot`：`update_cell` 重查 session/cells，`hint_states` 先 3 条 group_by 再逐任务 `failures_since`（N+1）。打字时每个停顿一次全量查询 |
| P2-2 | `learn_da/app/workspace/service.py:438` | `await self.runner.execute_session()` 数秒期间占着 DB 连接（SQLite 单写者下并发排队）。建议在调用前释放或改用独立 session |
| P2-3 | `learn_da/app/workspace/service.py:488-527` | `attempt_no = COUNT(*)+1` 且 `task_attempts` **无唯一约束**，并发会重号；`TaskAttempt.code` 用的是 Runner 前的 `cells[index].code` 快照，与学员实际提交的代码可能不一致 |
| P2-4 | `learn_da/app/practice/assertion_runtime.py:124-132` `_cell_equal` | ① str 与数值跨型相等（`"1" == 1`）；② `NaN != NaN` 使含 float nan 的参考单元格**永远失败** |
| P2-5 | `learn_da/scripts/build_expected.py:104-111` | `_plain()` 把 `datetime`/`date` 转成 str 写入 json ref，运行时侧拿到的是 `datetime` 对象，`_cell_equal` 为 False。当前 10 个 ref 全是 parquet 未触发，一旦有人加 json ref 就必挂 |
| P2-6 | `learn_da/app/practice/assertions.py:101-102,134-135` | `atol` 默认 0（`rtol=1e-6`）。期望值接近 0 时 rtol-only 容差不够，建议默认 `atol=1e-9` |
| P2-7 | `learn_da/app/workspace/progress.py` | 全文 grep `SessionCell\|session_cells` **0 命中** —— 进度/报告只看 `task_attempts`，不看格子状态。所以"代码改过、待复核"的 `todo` 不影响进度统计，`/workspace/progress` 的完成数与 `snapshot` 的视图状态会分叉 |
| P2-8 | `learn_da/app/agent/router.py:127` | 流内非 `CancelledError` 异常只补 `error` 事件、**不发 `done`**，且异常穿透使 `_persist_interaction` 不执行 → 审计丢失，前端拿不到 `teachingFeedback`/`interactionId` |
| P2-9 | `learn_da/app/agent/service.py:393` | 每轮都 `async with self._llm()`，3 轮工具调用新建 3 个 `AsyncOpenAI`。建议上移到 `for` 外层 |
| P2-10 | `learn_da/app/agent/routing.py:36` + `app/agent/tools.py:32` | 「练习/出题」仍路由 `generate_exercise`，但 `fc_tools.py:37-79` 的 `FC_TOOLS` 只有 search_knowledge/get_learner_progress/get_recommendation/get_task_summary，`AGENT_TOOLS` 仅测试引用 → 死代码 |
| P2-11 | `learn_da/app/core/content_loader.py:105-106` + `content_schemas.py:44-45` + `learn_da_vue/src/types/api.ts:67` | 旧练习元数据 `practice_objective`/`completion_criteria` 仍贯穿 loader → repository → schema → 前端类型，13 课 frontmatter 也留着（如 `content/lessons/01-polars-basics.md:13`） |
| P2-12 | `learn_da_vue/src/api/agent.ts:109-135` | 只按 `\n\n` 切分且结束时**不 flush `TextDecoder`**：CRLF（`\r\n\r\n`）事件切不开、被 chunk 切断的多字节字符丢尾字 |
| P2-13 | `learn_da_vue/src/api/index.ts:149-152` | `cancelAllRequests()` 只 abort axios 内部 controller map，**不含 fetch SSE 的 AbortController** → 路由切换不会中断进行中的流式对话 |

### 5.4 P3

- `learn_da/scripts/build_expected.py:40` 用 `os.environ.setdefault("POLARS_MAX_THREADS", "1")`：环境里已有该变量时静默失去字节可复现性，建议直接赋值或显式校验。
- `build_expected.py --check` 与 `content_lint.py` L7 **不检测孤儿 expected 文件**（删掉课程断言后旧 parquet 会一直留在仓库）。
- parquet 内嵌 polars `created_by` 版本串，升级 polars 即全量 drift —— 锁版本（`773f72c`）能挡住，但升级时需一次性重生成全部 10 个 ref。
- `learn_da/app/core/content_loader.py:226` L7 触发条件用**字符串相等**比较 `content_dir`（`if content_dir == Path(__file__).parent.parent.parent / "content"`），传相对路径时 L7 被静默跳过。
- `learn_da/app/workspace/repository.py:222-232` `hint_state` docstring 公式漂移：写的是 `min(3, 1 + failures_since_last_hint + hints_used)`，真实实现是 `1 + hints_used + failures//2`。
- `learn_da_vue/src/lib/learningTracks.ts:29` 首页副标题仍写「用课程、练习、Playground 和 AI 助手」，Playground 已下线。
- `learn_da_vue/src/components/workspace/WorkspaceAssistant.vue:249` 仍有 `get_recommendation` 工具提示文案；`src/types/api.ts:316-317` 注释提到已不用的 `/api/v1/recommendations`。
- `learn_da_runner/runner/settings.py:20` 镜像 tag 是 `polars-duckdb-sandbox:latest`（`docker-compose.runner.yml:19,47`、`deploy/runner.env.example:7` 同）：pip 版本已精确锁死（`773f72c`），但镜像用可变 tag → **判定环境实际不可复现**，与锁版本的意图矛盾。

### 5.5 UI 层与前端死代码（`c45b86a` / `d35e044` / `8640c2d` 三个提交的逐文件审查）

前面 5.1–5.4 的结论集中在后端与 Runner，UI 层三个提交没有逐文件审。补审之后发现：**新写的 4 个页面质量不差，但"页面重构"把旧页面删掉时带走了整条数据上报链路，留下了若干"看着能用、实际不动"的控件。**

#### 5.5.1 `ui_lint` 三个盲区（"UI 规范可执行"这条要打折）

| # | 位置 | 问题 |
| --- | --- | --- |
| U-1 | `learn_da_vue/scripts/ui_lint.mjs:37-42` | palette 正则**漏掉整套中性色**：只列 `blue\|emerald\|red\|orange\|indigo\|green\|amber\|violet\|purple\|pink\|teal\|cyan\|lime\|rose\|yellow\|sky\|fuchsia`，**没有 `gray\|slate\|zinc\|neutral\|stone`**。`src/views/NotFound.vue` 有 **14 处** `slate-*`（50/100/200/300/400/500/600/700/800）全部逃检；该文件被命中的只有 `:36` 的 `blue-*` 与 `:59` 的 `emerald-500` 共 4 处，正好等于 baseline 里 `"palette": 4` |
| U-2 | `ui_lint.mjs:31` + `:97` + `:149` | "UI 组件零容忍"**跨平台不一致**：`const UI_DIR = path.join("src","components","ui")` 在 Windows 得 `src\components\ui`，而排除判断 `rel.startsWith(\`${UI_DIR}/\`)` 用 `/` 拼 → Windows 上恒 false（UI 组件进 counts、靠 baseline 豁免）；Linux 上排除生效 → `counts` 不含 UI 组件、`touched` 不含它 → **UI 组件违规在 Linux 上永远不报告**。当前 `src/components/ui/AppButton.vue:47,53` 的 `shadow-sm` 两处正是 baseline `"src/components/ui/AppButton.vue": {"shadow": 2}` 的来源，两条路都放过 |
| U-3 | `ui_lint.mjs:116-126` | `writeBaseline(counts)` 把当前 counts **全量**写成新基线（注释只写"只允许减少"，代码不校验）→ 任何人跑 `node scripts/ui_lint.mjs --update-baseline` 就能把违规一次性合法化 |

`npm run lint:ui` 输出的"扫描 60 个文件，3 条规则 / 通过：没有新增视觉规范违规"是**真的**，但它的覆盖面比字面窄。基线本身在持续收敛（`c45b86a` 12 文件 558 处 → `d35e044` 8/225 → `8640c2d` 7/167 → `5a2cf29` 3/14 → HEAD 3/14），方向对，只是守门规则有洞。**`ui_lint` 无任何单测**（`scripts/` 下只有 `ui_lint.mjs` 与 `ui_lint.baseline.json`）。

#### 5.5.2 死代码与装饰性控件（"看着能用、实际不动"）

| # | 位置 | 问题 |
| --- | --- | --- |
| U-4 | `src/stores/learnerState.ts:118/123/128` + `src/components/layout/Navbar.vue:68-71,217` | 见 P1-22。连带两处用户可见后果：顶栏 `progressText` 读 `totalCompleted` **永远为 null**；`:217` 移动端提示条依赖 `lastVisitedSlug` 也永远为 null → **整条提示条永不渲染**，`:224` 的 `progressText ?? '开始学习'` 是死分支 |
| U-5 | `src/components/layout/Navbar.vue:161-167` + `src/stores/localState.ts` | **主题切换按钮是纯装饰**：点 `toggleEditorTheme()` 只改 `preferences.editorTheme` 字符串并切太阳/月亮图标，全仓**无任何代码把它应用到 DOM**（`App.vue` 43 行无 `classList`/`data-theme`，无 `tailwind.config.*`，`vite.config.ts` 无 `darkMode`）→ 页面配色完全不变 |
| U-6 | `src/components/layout/Navbar.vue:196-207` | **侧边栏切换按钮无对象**：按钮 `v-if="route.path.startsWith('/lesson/')"`，但 `LessonWorkspace.vue` 三栏是固定 grid，全仓无元素读 `isSidebarOpen` → 点了没反应，而 `:title` 文案还会在"收起/展开"间来回变，给人"生效了"的错觉 |
| U-7 | `src/stores/localState.ts`（179 行） | 大部分成员无消费者：`Navbar.vue` 只用 `editorTheme` 与 `isSidebarOpen`；`editorFontSize`/`uiLanguage`/`setLanguage`/`increaseFontSize`/`decreaseFontSize`/`resetPreferences`/`setEditorTheme`/`setSidebarOpen` **全仓零引用** |
| U-8 | `src/components/ui/status.ts:6 态` | **`needs_review` 是死状态**：`app/workspace/service.py:197-207` 任务态只产 `todo/passed/failed/skipped`——`attempt.status=="passed"` 但格非 ok 时**显式回落 `todo`**（`:201-203` 注释「代码改过 → 结论需复核，回到 todo」），后端从不发 `needs_review`。前端它只在 `status.ts` 定义 + `StatusPill.spec.ts` 里出现，业务零使用 → 「需复核」药丸永不显示，学员只看到「未开始」 |
| U-9 | `src/lib/learningTracks.ts`（101 行） | 只剩 `platformCopy.name`/`.title` 活着（`Navbar.vue:6,98,101`）。`heroTitle`/`heroTitleHighlight`/`heroSubtitle`/`shortTitle`/`currentScope`/`expansionHint` 六个字段 **0 命中**（含 `:29` 那句仍写「Playground」的副标题）；`learningTracks`/`currentTrackKeys`/`learningTrackMeta` 三个导出也无消费者（基线时被已删的 `Home.vue` 与 `Learning.vue` 用） |
| U-10 | `src/lib/visitorId.ts`（29 行） | **整个文件死**：`getVisitorId` 零 import。身份已改由签名 cookie 承担（`src/api/index.ts:24` `withCredentials: true`），`src/api/learnerState.ts:12` 注释也写明"不需要传 visitorId" |
| U-11 | `src/api/learning.ts`（59 行） | 4 个导出只有 `fetchLessonBySlug` 活着（`LessonWorkspace.vue:314,519`，纯为展示课程标题）；`fetchLessons`/`fetchCatalog`/`fetchCategoryStats` **零消费者** |
| U-12 | `src/types/api.ts`（319 行） | 11 个类型除定义处外零引用：`CatalogTopic`、`CatalogTrack`、`LessonNav`、`ExecutionSource`、`ExecuteResultType`、`DataFrameResult`、`MessageRole`、`TeachingNextAction`、`CodeRunStatus`、`LessonProgressDetail`、`DataFrameCell` |
| U-13 | `app/learning/router.py:69/89/96/114` + `app/analytics/router.py:43/57/70/81/92/103` | 后端有 10 个端点无前端消费者：`/lessons/all`、`/lessons/categories`、`/catalog`、`/recommendations`，以及 analytics 的 `learning-progress`/`home-stats`/`user-profile`/`user-lesson-stats`/`daily-trend`/`category-progress`。其中 analytics 六个是 `d35e044` 删掉 Dashboard 取数函数后遗留的孤儿 |

#### 5.5.3 `src/components/ui/` 8 组件（572 行）读后结论

基础组件层整体是这轮做得最扎实的前端产出，**8 个组件都有明确职责、没有第二套实现**：`AppButton`（三档 variant + danger，`isDisabled = disabled || loading` 且 `onNativeClick` 里再挡一次）、`AppCard`（唯一来源 `rounded-card border-line bg-surface-card shadow-card`）、`AppInput`（`useId()` 关联 label + `aria-invalid` + `aria-describedby`）、`CodeOutput`、`StatusPill`、`ToastHost`（`role="status" aria-live="polite"`）、`EmptyState`（`cta` 为**必填** prop，强制空态带下一步）、`ConfirmDialog`。

三处需要修的细节（详见 5.5.4 的 C-1/C-3/C-11）：

- `ConfirmDialog.vue`（85 行）**无 focus trap、无滚动锁、无 `aria-labelledby` 指向标题元素**（用 `aria-label` 传字符串）→ 多按钮对话框按 Tab 会跑出层外。ESC 与点遮罩取消、打开时焦点落取消按钮、`onBeforeUnmount` 移除监听这些都做对了。
- `CodeOutput.vue:42` 复制走 `navigator.clipboard.writeText`：生产 `PUBLIC_SCHEME=http`（`deploy/app.env.example:6`、`docker-compose.app.yml:47` 默认 http），**明文 HTTP 非安全上下文下 clipboard 不可用**，catch 里有 toast 兜底但功能实际失效（与 AGENTS.md 已知坑 6 同类）。
- `AppButton.vue:47,53` 的 `shadow-sm` 违反自家"阴影只用 `shadow-card|pop`"规则，靠 baseline 豁免（见 U-2）。

#### 5.5.4 组件级细节（第二路审查，13 条已逐条复核）

5.5.3 是自读结论；这一节是第二路审查（子代理 `cb4e34de`）跑出来的组件级问题，我逐条复核过代码与数字。**已确认无问题的边界**：`AppInput` 的 `modelValue`/`update:modelValue` 无滞后也无默认值陷阱；`ToastHost` 的 `aria-live="polite"` + `role="status"` 与 `:key="item.id"`（自增 seq）稳定；`main.css` 无重名 token、无重复 `@theme` 键。

| # | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| C-1 | `src/components/ui/ConfirmDialog.vue:29-34,55-65` | 无焦点陷阱（Tab 可跑到底层页面）、打开不锁 body 滚动、关闭不还焦点；`window` 监听上的 `stopPropagation` 挡不住同节点其他监听 | Tab 循环 + `document.body.style.overflow` 锁定 + 关闭时 `focus` 回原触发器，ESC 改 `stopImmediatePropagation` |
| C-2 | `src/components/ui/AppInput.vue:29-34,60-61` | `hint` 与 `error` 并存时 `describedBy` 同时引用两个 ID，但模板 `v-if="error"` / `v-else-if="hint"` 只渲染其一 → **悬空 ID 引用** | `describedBy` 改为 `error ? error-id : hint-id` 二选一 |
| C-3 | `src/components/ui/CodeOutput.vue:42` | 明文 HTTP 下 `navigator.clipboard` 为 `undefined`，「复制」在生产必失败（AGENTS.md 坑 6） | 加 textarea + `execCommand` 兜底，或先判 `window.isSecureContext` |
| C-4 | `src/components/ui/CodeOutput.vue:37` | `stderr` 非空时 **stdout 被整体丢弃**，`Lab.vue:326` 只能靠 `[notice, stderr].join("\n\n")` 拼字符串绕过 | 改成分段渲染 stdout/stderr 两块 |
| C-5 | `src/components/ui/CodeOutput.vue:73-76` | `<pre>` 无 `aria-label`、无 `aria-live`：输出更新与「失败」状态都不播报 | 加 `role="log"` + `aria-live="polite"` + `aria-label="执行输出"` |
| C-6 | `src/components/ui/ConfirmDialog.vue:70-80` | 组件自身不防重复 confirm/cancel，防连点全靠父传 `loading`；loading 期间 ESC 与遮罩点击仍能取消 | emit 前内部加 `busy` 门闩，loading 时忽略 cancel |
| C-7 | `src/components/ui/ToastHost.vue:26-31` + `src/composables/useToast.ts:49` | 无堆叠上限、无 `max-height`/`overflow`（连发多条铺满屏）；队列无界；定时器在模块级 Map，`ToastHost` 卸载不清理；`durationMs` 存了但从未消费 | `show()` 保留最近 N 条 + 容器加 `max-h-[40vh] overflow-auto` |
| C-8 | `src/components/ui/AppInput.vue:46-59` | 无 `inheritAttrs:false` + `v-bind="$attrs"`：`autocomplete`/`@blur`/aria 落到外层 `div`，而 **blur 不冒泡 → 监听不触发** | 透传到 `input`，并补 `autocomplete`/`name` prop |
| C-9 | `src/components/ui/AppButton.vue:43,80` | loading 用原生 `disabled`：提交后按钮被移出 tab 序，键盘焦点掉回 body | loading 改 `aria-disabled` + 拦截点击，保留焦点 |
| C-10 | `src/components/ui/StatusPill.vue:12` | `status: string` 而非 `TaskStatusKind`，拼错的状态**静默降级**为「未开始」（配合 U-8 的 `needs_review` 死状态，问题会互相掩盖） | 收窄为 `TaskStatusKind`，未知值由调用方显式断言 |
| C-11 | `src/assets/styles/main.css:42` | **`--color-ink-300: #cbd5e1` 作正文色对比度仅 1.48:1**（WCAG AA 要求 4.5:1），却是全站 **33 处 `text-ink-300`**（实测逐文件：LessonWorkspace 12、WorkspaceAssistant 6、TaskHintPanel 4、Lab 4、CourseMap 2、Report 2、Navbar 1、AppInput 1、Home 1），含 11px 说明文字 | muted 文本改用 `ink-500`（**实测 4.76:1**，已过 AA）；`ink-300` 只留边框/图标与 `placeholder` |
| C-12 | `learn_da_vue/scripts/ui_lint.mjs:62,146-157` | 只扫 `.vue`/`.ts`（**漏 `src/**/*.css` 与 `index.html`**），却把 `__tests__/*.spec.ts` 计入预算；且按文件**净计数**比较，「加一处删一处」可互相抵消 | 排除 `__tests__`、补 `.css` 扫描、按行号集合而非计数比较 |
| C-13 | `src/assets/styles/main.css:11,14,21,27,29,33` | 孤儿 token：`brand-100`/`brand-400`/`ok-100`/`warn-100`/`warn-600`/`err-100` 定义后零引用；`ink` 只定义了 300/500/700/900，色阶断档 | 删孤儿或补齐色阶（配合 C-11 一并处理） |

其中 C-11 是本轮 UI 层**唯一影响可读性**的问题，也是最容易修的一条（改一个 token + 批量替换）。C-1/C-3/C-5/C-9 属无障碍与生产可用性，建议与 C-11 一起在下一批处理。

#### 5.5.5 新页面（`CourseMap` / `Lab` / `Report` / `Home`）读后结论

这 4 个页面是 `d35e044` 与 `8640c2d` 的主体（CourseMap 221 + Lab 417 + Report 370 + Home 297 行；Home 的 711 是 diff 行数，含大量改写），质量明显高于被删的旧页面：

- **三态齐全**。`Report.vue:186` loading skeleton 带 `aria-busy`、`:203` error + `retry` 按钮、`:218` empty 用 `EmptyState` + `cta="去课程地图"`；`Home.vue:160-165` 空态也用 `EmptyState` + CTA。符合 AGENTS.md「空态必须带 CTA」的约定。
- **口径不在前端重算**。`CourseMap.vue` 的 `pillStatus`/`ctaLabel`/`ratio` 全部读后端 `lessonProgress`（passedTasks/totalTasks/currentTaskId/lastActivityAt），没有前端自算通过判定 → 与 `progress.py` 一致，不会产生 P2-7 那类分叉。
- **防连点正确**。`Lab.vue:309-310` `isRunning`/`canRun` + `:88-89` 按钮 `:loading`/`:disabled`，`run()` 里 `:363` 先 `if (!canRun.value) return` 再置 running；`requestId: randomId()` 走 `@/lib/uuid`（符合坑 6）。503 → `UNAVAILABLE_MESSAGE`，fail-closed 语义与后端一致。
- **竞态处理正确**。`useAsyncState.ts`（95 行）`run()` 里 `const current = ++requestId`，回来 `if (current !== requestId) return null` 丢弃过期响应，`reset()` 也 `requestId++` 让在途失效 —— **这比 `workspace` store 的 `reset()` 强**（对照 P1-15）。
- **`ContinueStrip.vue` 是加完又删的返工**：`d35e044` 新增 76 行，`8640c2d`（同一天）整文件删除 76 行，`src/components/home/` 目录现已不存在。`components/` 只剩 `layout/ ui/ workspace/`，旧的 `agent/` 也随 `AgentPanel.vue` 一起删了。

#### 5.5.6 新页面细节（第三路审查，16 条已逐条复核）

前两路给的是"整体质量"判断；这一节是逐行复核后发现的**具体数字错、口径互斥、字段名错配**一类问题。已核实无问题的角度：raw palette / 非标准阴影在 4 个存活文件零命中且 `node scripts/ui_lint.mjs` 实测通过；`window.confirm` 与 `crypto.randomUUID` 零命中（`Lab.vue:374` 的 `requestId: randomId()` 走 `lib/uuid`）；Home/CourseMap/Report 三态齐全、错误态均有重试 CTA、空态均带 CTA；`Lab.vue` 硬编码的 4 个数据集体量与列名和 `content/datasets/ecommerce/manifest.json` 完全一致；`CourseMap` 的 `ratio` 只用于展示、`Report` 的 `trackPercent` 自算（未误乘后端 0–1 的 `ratio`）。

| # | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| N-1 | `src/views/Lab.vue:311` + `:360-407` | **清空输出可绕过运行中互斥**：`canClear = phase !== "idle"` 在 running 时仍为 true，点「清空输出」→ `clearOutput()` 置 idle → `canRun` 复活可再点运行；而 `run()` **无请求序号守卫**，先发后到的响应会覆盖新一次运行的视图状态。`useInlineSample()`（`:413-416`）同样在 running 时 `clearOutput()` | 加 `let seq = 0`，响应回来校验 `if (current !== seq) return`（对齐 `stores/workspace.ts:122` 的先占位模式） |
| N-2 | `src/views/Report.vue:66-73` | **一次通过率分母系统性偏小**：`attemptedTasks = tasksPassed + 去重(errorPatterns 的 lessonSlug::taskId)`，但后端 `progress.py:187` 是 `return rows[:ERROR_PATTERN_LIMIT]`（限 8 条，且按 lesson+task+**assertion** 分桶，同一任务可占多条）→「只失败过、未通过」的任务大多不进分母，通过率被高估。而 `:120` 的 sub 文案却写「含只失败过的任务，同一任务只计一次」 | 让后端 `summary` 直接给「已尝试任务数」，或按 assertions 全量去重 |
| N-3 | `src/views/Home.vue:67-71` vs `Report.vue:66-73` | **两页一次通过率口径互斥**：Home 用 `Math.min(tasksFirstTry, tasksPassed) / tasksPassed`（分母=已通过），Report 用 `tasksFirstTry / attemptedTasks`（分母=已尝试）。同一学习者同一天两页显示不同数字（例：20 个任务全通过、其中 15 个一次过、另有 10 个只失败过 → Home 75%，Report ≈58%） | 抽到一个 `lib/metrics.ts` 统一口径 |
| N-4 | `src/views/Lab.vue:394` | **字段名错配，耗时永不显示**：读 `response.executionTime`，但后端 `ExecuteCodeResponse.model_dump(by_alias=True)` 输出的是 `durationMs`（实测 `{'durationMs': 42}`；`validation_alias=AliasChoices(...)` 只作用于**入参**，不影响序列化）→ `CodeOutput` 的 `durationMs` 恒 null | 改读 `response.durationMs`（前端类型 `types/api.ts:111` 的 `executionTime` 也要同步改） |
| N-5 | `src/views/Lab.vue:108-114` | **丢弃后端结构化结果**：后端 `playground/service.py` 专门注入 dataframe 探针并把 marker 行从 stdout 剥离，响应含 `resultType`/`dataframe`/`outputTruncated`，但 `Lab.vue` 对这三个字段**零引用** → 不 `print` 的 `df` 学习者什么都看不到，输出被截断也无提示 | 至少渲染 dataframe 预览并提示输出已截断 |
| N-6 | `src/views/Report.vue:161-163` | `goLesson(slug)` 只 `router.push(\`/lesson/${slug}\`)`，**丢掉 `pattern.taskId`**，与 `:20` 注释「卡点整条可点 → 回对应课程工作区」不符；`Home.vue:124-126` 与 `CourseMap.vue:80-86` 都带 `?task=`，三页行为不一致 | 给 `goLesson` 加可选 `taskId` 并传 `pattern.taskId` |
| N-7 | `src/views/Report.vue:177-180` | **「统计窗口：最近 N 天」误导**：后端 `windowDays = (today - min(days)).days + 1`（`progress.py:338`）只是首条记录到今天的跨度，`_attempts`（`progress.py:53-59`）**无时间过滤**，所有指标都是全量历史 | 文案改「最早记录距今 N 天」，或后端真加窗口过滤 |
| N-8 | `src/views/CourseMap.vue:171` | 全新访客看到「0/3 任务 · 最近学习 **还没开始**」：`lastSeen()`（`:88-91`）无 `lastActivityAt` 时返回「还没开始」 | 无时间戳时整段隐藏 |
| N-9 | `src/views/CourseMap.vue:33` | 全部完成后 `lessons.find(status !== "completed") ?? null` 返回 null，「继续上次」卡片整块消失、**无复习入口**（`Home.vue:38` 有 `?? lessons.value[0] ?? null` 兜底） | 补同样的兜底 |
| N-10 | `src/views/Report.vue:210` | 重试 `AppButton` **无 `:loading`**，可连点（`Home.vue:153`、`CourseMap.vue:123` 都有 `:loading`） | 加 `:loading="status === 'loading'"` |
| N-11 | `src/views/Home.vue:180,182,263,264`、`CourseMap.vue:195,197`、`Report.vue:258,266` | 进度条用 `rounded-full`（8 处），违反 AGENTS.md「圆角仅 `rounded-card\|control\|pill`」；`ui_lint.mjs` 的 radius 规则只禁 `sm\|md\|lg\|xl\|2xl\|3xl`，**放行 `rounded-full`** | 改 `rounded-pill`，并把 `rounded-full` 纳入 lint 白名单校验 |
| N-12 | `src/views/Lab.vue:2` | `min-h-screen bg-surface-page` 与 Navbar（在 `App.vue` 的 `main` 之外）叠加 → 页面恒比视口高一屏，出现无意义滚动条；其余三页只用 `py-8` | 去掉 `min-h-screen` |
| N-13 | `src/views/Report.vue:283` | 把后端截断包装成「上限」：`:meta="errorPatterns.length ? \`最多 ${ERROR_PATTERN_LIMIT} 条\` : undefined"` → 用户看不到第 9 条以后的卡点 | 改「按失败次数排序，仅显示前 8 条」 |
| N-14 | `src/views/Report.vue:333-336` | 表格 `<th>` **无 `scope="col"`**（4 处），屏幕阅读器无法关联列 | 补 `scope="col"`（输出面板的 `aria-live` 见 C-5） |
| N-15 | `learn_da/app/workspace/progress.py:262-264` + `src/views/Report.vue:129-136` | **UTC 计日 vs 本地显示**：后端 `days.append(stamp.astimezone(timezone.utc).date())` 决定 `activeDays`/`streakDays`/`daysSinceActive`，而前端 `Intl.DateTimeFormat("zh-CN", {...})` **无 `timeZone` 选项**按本地渲染 → UTC+8 用户「今早提交」会被算成昨天，`Home.vue:63` 的「已经 N 天没练了」同样偏移一天 | 后端按访客时区计日，或前端显式标注 UTC |
| N-16 | `src/components/home/ContinueStrip.vue:58-60`（`d35e044` 历史版本，HEAD 已删） | **三态缺失**：`<!-- 加载中和失败都直接隐藏 -->` + `v-if="target"`，loading/error 均无任何 UI、无重试 CTA | 已随 `8640c2d` 删除；此处记录为"返工前的教训"——新页面统一走 `useAsyncState` 的三态，别再写"加载中就隐藏" |

其中 **N-2 与 N-3 是同一条链路上的两处口径分叉**，值得优先修：它们让「一次通过率」这个首页与报告页的核心指标在同一天出现两个不同数字，而学员会先看到 Home 再点进 Report。**N-4 是纯字段名错配**（后端 `durationMs` vs 前端 `executionTime`），一改就生效，属低成本高收益。

---

## 6. 工程验证结果

### 6.1 实测基线（本次审查重跑）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 后端测试 | `cd learn_da && .venv/Scripts/python.exe -m pytest -q` | **507 passed**（多次重跑 16–19s） |
| 前端测试 | `cd learn_da_vue && npm test -- --run` | **143 passed**（18 文件） |
| Runner 测试 | `cd learn_da_runner && .venv/Scripts/python.exe -m pytest -q` | **39 passed**，3.5s |
| 前端类型 | `npm run type-check`（vue-tsc --build） | 通过 |
| 视觉规范 | `npm run lint:ui` | 60 文件，无新增违规 |
| 内容校验 | `scripts/content_lint.py` | 课程数与 catalog 一致 |
| 数据集 | `scripts/build_datasets.py --check` | 5 文件，seed 20251021 |
| 预期结果 | `scripts/build_expected.py --check` | 8 门课 |

说明：本机无 `pytest-timeout`（加 `--timeout=300` 会报 unrecognized arguments）；`npm run build` 在本机被 esbuild 临时文件权限拦截（环境问题，见 AGENTS.md 已知坑 9）。

### 6.2 测试覆盖的盲区（新增测试 16 个文件，但下面这些没测）

- **`test_workspace_api.py`（10 条）的幂等只测「同 requestId 同 run 端点」**（`:223 test_same_request_id_is_idempotent`），未测 run→submit 混用、跨 session 重放（即 P0-4）。
- **`test_session.py`（8 条：full_replay / assertion_failure / failed_cell_stops / stop_at / leak / escape / oversized / missing_runtime）没有 refs 相关测试** —— 也就是本轮新增的 10 个参考结果在 Runner 侧零覆盖，全靠后端 `test_workspace_refs.py` 与验收脚本兜。
- **`test_agent_stream_endpoint.py`（4 条）只测传输层**（SSE 头、每事件一行 data、空消息 422、异常时 error 事件），**没有测 `error` → `done` 顺序下 `done.data.content` 的语义**，因此 P0-5 一路绿灯。
- 前端 `useAgentConversation.spec.ts` 4 条（stopStreaming abort / clearMessages / partial error / 非 partial error）与 `workspace.spec.ts` 13 条（load / editCell / flush / submitTask / runCell 并发 / hint / reset）**均未覆盖"partial error 后 done 覆盖"与"reset 后在途响应"**。
- 无并发测试（P1-4/5/6 的三处 `IntegrityError` 都只有单线程测试）。
- `sql_rows` 类型零使用（122 条断言里 0 条），**属未验证路径**，而它恰好有 P1-1 的列数缺陷。
- **`ui_lint` 零单测**：`learn_da_vue/scripts/` 只有 `ui_lint.mjs` 与 `ui_lint.baseline.json`，三个盲区（5.5.1）都没有测试守着；`Home.spec.ts`（296 行）测的是页面渲染，不覆盖视觉规范规则。
- **UI 层新增页面只有 3 个测试文件**（`Home.spec.ts` 296 行、`Lab.spec.ts`、`Report.spec.ts`），`CourseMap.vue`（221 行）与 `LessonWorkspace.vue`（532 行，本轮最复杂的页面）**没有页面级测试**，工作区交互只靠 `stores/__tests__/workspace.spec.ts` 的 13 条 store 测试间接覆盖。
- **`/analytics/track` 全链路断供无测试发现**（P1-22）：后端 `analytics/service.py` 的分派逻辑有测试，但没有任何测试断言"前端存在调用方"；这类"删页面带走链路"的回归只能靠端到端脚本，而验收脚本 A11 是自己 `curl` 打 `/analytics/track`，**不经过前端**。

### 6.3 验收脚本

`deploy/acceptance.sh` 已重写为工作区链路，A1–A13 共 29 项，覆盖真实 Runner 执行、起步代码必判失败、参考解逐格通过、提交幂等、进度与报告、Agent 三场景（no_evidence / passed_unconfirmed / 跨访客隔离）、改上游代码下游失效、`/analytics/track` 幂等、分级提示、SSE。**它测不到 P0-1/2/3/6**（验收脚本扮演的是"诚实的学员"），所以五条越权 PoC 目前没有任何自动化防线。

---

## 7. 成熟度判断

| 维度 | 评价 | 依据 |
| --- | --- | --- |
| 产品闭环 | **好** | 5 个路由 + 三栏工作区 + 任务判定 + 分级提示 + 报告，链路完整可演示 |
| 架构分层 | **好** | 判定在 Python、表达在 LLM、呈现在前端，边界清晰 |
| 判定可信度 | **不足（唯一阻塞项）** | 5 条越权 PoC 全部成功（含 `expr_true` 鸭子类型绕过）；判定与学员代码同进程同目录 |
| 并发正确性 | **不足** | 幂等键不足 + 三处未捕获 `IntegrityError` + hint 无幂等 |
| 限流与成本 | **不足** | 最贵的 8 个端点零限流，全局 default_limits 配置是死的 |
| 前端状态机 | **中** | 流式终态语义有 P0 回归；切课/卸载无请求隔离；但 `useAsyncState` 的 requestId 竞态处理是对的 |
| 内容可复现 | **好** | 数据集与参考结果都字节级可校验，有 `--check` 与测试（但 Runner 镜像 tag 用 `latest`，见 5.4） |
| 工程门禁 | **中** | 507/39/143 全绿、验收 29 项；但 CI 仍暂缓（GitHub 账单），靠人工本地跑；`ui_lint` 无单测且三个盲区 |
| 文档一致性 | **中** | 设计稿宣称的"内存注入不落盘"与实现矛盾；注释公式漂移；Playground 文案残留 |
| **数据上报链路** | **不足** | `/analytics/track` 前端零调用（P1-22）：`lesson_start`/`lesson_complete`/`code_run` 四类事件断供，推荐的三条回补信号恒假，`Navbar` 进度文案永久为空 |
| 无障碍与可读性 | **中** | 组件层有 `useId`/`aria-live`/`aria-invalid` 意识，但 `ink-300` 作正文色只有 1.48:1（33 处）、`ConfirmDialog` 无焦点陷阱、输出区无播报 |

**结论：内部 Alpha 合格，公开 Beta 需要先关掉 P0 四项。** 判定可伪造对一个"以任务判定为教学证据核心"的平台是根本性的——如果学员能伪造 `passed`，那么推荐、报告、Agent 证据链全部建立在不可信数据上，而这套证据链正是这轮重构最重要的产出。

判定可信度一栏的判断依据是：**五条越权 PoC 全部在本机跑通**（atexit 伪造 marker / 替换断言运行时 / frame 爬取 plan.refs / 读 plan.json 拿 refs / 鸭子类型绕过 expr_true），且验收脚本扮演的是"诚实学员"，对五者均无防线。

**这份报告对 23 个提交的覆盖程度**：23 个提交全部在范围内（`248528c^..b0ee3d5`，与 `git log --since/--until` 双向比对一致），其中 **19 个有逐文件代码审查，4 个是轻提交只做内容核对**（`74cd27f` 删 `.pytest_tmp` 4 个产物 + `.gitignore` 一行、`3b9dc66` 纯文档 3 文件、`0103a4b` 纯设计稿 1 文件、`27300d1` 八行 `.gitattributes`——后者已实测 `git check-attr` 确认 datasets/expected 两目录均为 `text: unset`，覆盖正确）。

`74ea621`（删 `FALLBACK_LLM_*`、让 `RATE_LIMIT_ENABLED` 真正关掉限流）虽然只有 +80/−53 行，但它正是 P1-3 那条的上下文：修复只做到"开关同步到 `limiter.enabled`"，没顺手补 `Limiter(default_limits=...)`，于是 `RATE_LIMIT_GLOBAL_IP`/`RATE_LIMIT_DEFAULT` 至今全仓无引用。所以它算实质性审查。

UI 层三个大提交（`c45b86a`/`d35e044`/`8640c2d`）在第一版报告里只列进了提交表，**是补审 5.5 之后才有逐文件结论的**——这一节的 42 条（U-1…U-13、C-1…C-13、N-1…N-16）就是补审的产出，也是本报告改动最大的一处。

---

## 8. 修复优先级建议

### 第一批（Beta 前必须，估 2–3 天）

1. **判定隔离**（P0-1/2/3，方案见附录 A）：不是"加载顺序 + nonce"这种局部补丁（已被实证推翻），而是把判定移出学员进程。同时补三条回归测试：学员格读 `plan.json` 拿不到 refs、替换 `_load_assertion_runtime` 无效、atexit 伪造 marker 无效。
2. **`expr_true` 可信度**（P0-6，见附录 A.3）：短期把 DataFrame 型 `expr_true` 迁到 `frame_equal`/`schema`，纯 Python 课改造成"固定输入调用函数"的结构化断言；中期加类型契约。补一条鸭子类型 PoC 的回归测试。
3. **幂等键与并发**（P0-4、P1-4/5/6）：幂等键补 session/cell/task/kind；三处 `IntegrityError` 捕获；`hint_usages` 加唯一约束 + 请求带 requestId。补两个并发测试。
4. **前端流式终态**（P0-5）：后端 partial 场景下发跨轮累积全文；前端 `interrupted`/`partial` 不覆盖；`CancelledError` 单独分支。加一条"partial error 后 done 不覆盖已渲染文本"的前端测试。

### 第二批（Beta 前应做，估 2 天）

5. **限流**（P1-3）：workspace run/submit/hint 挂限流；`Limiter` 补 `default_limits`，让 `RATE_LIMIT_GLOBAL_IP`/`RATE_LIMIT_DEFAULT` 生效。
6. **`/analytics/track` 断供**（P1-22）：决定学习事实的写入点。最省事的做法是**服务端在 `submit_task` 成功时直接落 `LearningRecord`**（`code_run` + `lesson_complete`），不依赖前端上报；同时删掉 `learnerState.ts` 的死写方法、`localState.ts` 的死成员、`visitorId.ts` 整文件，并修 `Navbar` 两处永久空态。
7. **sql_rows 列数**（P1-1）+ 至少一门课真的用上 `sql_rows`（当前零覆盖，等于没验证）。
8. **RUNNER_ENV 白名单化**（P1-19）+ compose 注入三个 session 配置。
9. **格子状态回写用旧快照**（P1-7）+ `_safe_relative` drive 检查（P1-2）。
10. **前端切课/卸载隔离**（P1-15/16/17/18）：store 加 epoch token，`onScopeDispose` abort 流。

### 第三批（可排期，估 3–5 天）

11. `llm_client` 三处（工具名累加、`finish_reason`、整体超时）——P1-8/9/10。
12. 提示注入加固（P1-12）：不可信数据定界。
13. 性能（P2-1/2）：snapshot 增量、Runner 调用期间释放连接。
14. **`ui_lint` 三个盲区**（U-1/2/3 + C-12）：palette 正则补 `slate/gray/zinc/neutral/stone` 与 `bg-white/text-white/bg-black`、路径判断改用与 `path.sep` 无关的比较（`UI_DIR` 直接写 `"src/components/ui"`，且 UI 组件改为"不进基线但仍进 counts"）、`--update-baseline` 先算违规有新增就 `exit 1` 拒绝写盘；排除 `__tests__`、补 `.css` 扫描；补一组规则单测。顺带清 `NotFound.vue` 的 14 处 `slate-*`。
15. **`ink-300` 对比度**（C-11 + C-13）：全站 33 处 `text-ink-300`（含 11px 说明文字）对比度只有 **1.48:1**（AA 要求 4.5:1）。改 `ink-500`（实测 4.76:1）即可，`ink-300` 只留边框/图标/`placeholder`；同时清掉 6 个孤儿 token。
16. **组件无障碍与生产可用性**（C-1/C-3/C-5/C-9）：`ConfirmDialog` 焦点陷阱 + 滚动锁 + 关闭还焦点；`CodeOutput` 剪贴板兜底（明文 HTTP 下 `navigator.clipboard` 为 undefined）与 `role="log"` + `aria-live`；`AppButton` loading 改 `aria-disabled` 保焦点。
17. **一次通过率口径统一**（N-2 + N-3）：两页目前算的是两个不同的数（分母一个是"已通过任务"，一个是"已尝试任务"），同一天同一学员会看到两个数字；且 Report 的分母受后端 `ERROR_PATTERN_LIMIT=8` 截断影响而系统性偏小。抽一个 `lib/metrics.ts`，并让后端 `summary` 直接给「已尝试任务数」。
18. **`Lab` 的字段错配与结果丢弃**（N-4 + N-5）：`response.executionTime` 应读 `durationMs`（后端 `model_dump(by_alias=True)` 实测输出 `durationMs`），耗时现在永不显示；后端专为 Lab 注入的 `resultType`/`dataframe`/`outputTruncated` 三个字段前端零引用。
19. **装饰性控件与死代码**（U-4…U-13 + C-2/C-4/C-6/C-7/C-8/C-10）：主题切换与侧边栏切换二选一——要么真的接上 DOM/布局，要么删掉按钮；`needs_review` 状态要么后端产出、要么前端删掉；清理 `learningTracks.ts`/`visitorId.ts`/`api/learning.ts` 与 11 个死类型、10 个无消费者端点；`AppInput` 的 `describedBy` 二选一与 `$attrs` 透传、`CodeOutput` 分段渲染、`ToastHost` 堆叠上限。
20. **新页面细节**（N-1/N-6…N-16）：`Lab` 加请求序号守卫（清空输出可绕过运行中互斥）；`goLesson` 带 `taskId`；`rounded-full` 改 `rounded-pill` 并纳入 lint；`<th scope="col">`；`Lab` 去掉 `min-h-screen`；`CourseMap` 全完成后补复习入口；`Report` 重试按钮加 `:loading`、窗口文案改口径；UTC 计日与本地显示对齐。
21. 文档与文案（P3 全部）：设计稿改口径、`hint_state` 公式、Playground 残留文案。
22. 旧练习元数据清理（P2-11）、死代码（P2-10）。

---

## 附录 A：判定隔离的具体改法（含实测验证）

本节的所有结论都来自本机 PoC，**不是设计推演**。写这一节的直接原因是：我在第一版报告里给的三条建议（refs 改 stdin 传递、runtime 提前加载并绑定闭包、marker 掺 nonce）**被自己的实测逐条推翻**，必须换成经过验证的方案。

### A.1 为什么进程内加固全部无效

三个攻击面各自对应一条被推翻的建议：

| 原建议 | 实测结果（均在真实 `session_driver.py` 上复现） |
| --- | --- |
| refs 不写进 `work`，改 stdin/fd 传入 | 学员格 `sys._getframe(2).f_locals['plan']` 直接拿到 `run_plan` 的 `plan`，实测输出「爬到 plan 于深度 2，refs= ['expected/frame_secret.parquet']」。**refs 只要在判定进程内存里，就爬得到** |
| runtime 在 exec 学员代码**之前**加载并绑定闭包 | 真实 driver 里 `_load_assertion_runtime` 是模块级函数、走全局查找，改上层帧的局部变量无效（实测该变体**不成立**，`verdict=assertion_failed`）；但 `import __main__` 直接改模块属性**成立**（PoC-2）。也就是说"提前加载"堵不住 `import __main__` 这条路 |
| MARKER 掺每请求 nonce | nonce 若随 plan 下发则学员可读；若只存在内存则可 frame 爬取。只能挡盲打印，挡不住有心读取 |

共同根因：`session_driver.py:167` 用 `exec(code, namespace)` 在**自己进程内**执行学员代码，学员代码与判定逻辑共享调用栈、模块表、`__main__`。`sys._getframe` 能沿栈读任意上层帧的局部变量，`import __main__` 能改任意模块属性。**任何"同进程内的先后顺序"安排都不构成边界。**

> 诚实说明：我最初把"提前加载 + 闭包绑定"列为有效改法，是拿自己的原型验证的；在真实 driver 上该攻击变体其实不成立（因为加载器走全局查找）。但结论方向没变——`import __main__`（PoC-2）与 frame 爬取（PoC-2b）这两条真实路径仍然成立，所以"提前加载"依然不是修复方案，只是堵住了其中一条。

### A.2 有效方案：判定移出学员进程

结构改为两段：

```
后端 ──refs（仅宿主侧持有）──▶ 宿主判定进程
                                    ▲
                                    │ 只回传「变量值」，不回传任何判定结论
                                    │
学员容器 ──exec 学员代码──▶ 序列化 assertionVars ──┘
```

要点：

1. **容器侧 driver 不再算 verdict**。只做：读 plan（含 `cells`/`stopAt`/`assertionVars`/`nonce`）→ 顺序 exec 学员代码 → 把 `assertionVars` 里声明的变量序列化回传。**plan 里没有 refs**。
2. **序列化用 Arrow IPC**（`polars.DataFrame.write_ipc` → base64）。**本机对全部 10 个真实参考结果做了往返实测，10/10 无损**（`equals=True` 且 `schema` 完全一致）：

   | ref | 行×列 | IPC 字节 | base64 字节 |
   | --- | --- | --- | --- |
   | 07-t1-filtered-orders | 3722×3 | 90,699 | 120,932 |
   | 01-t3-top-orders | 10×4 | 1,659 | 2,212 |
   | 03-t2-region-share | 4×4 | 1,193 | 1,592 |
   | 11-t3-category-stats | 5×3 | 1,063 | 1,420 |
   | 08-t2-category-stats | 5×3 | 1,035 | 1,380 |
   | 07-t2-channels / 02-t2-region-stats / 06-t2-segment-stats / 10-t2-region-stats | 4×3 | ~985 | ~1,318 |
   | 02-t3-top-orders | 5×2 | 827 | 1,104 |

   即 9 个 ref 都在 2 KB 以内，只有 `07-t1`（3722 行明细）到 120 KB。
3. **宿主持有 refs 并判定**。实测 `frame_equal` 正确判 passed；`expr_true: df.height == 2` passed、`df.height == 99` failed。
4. **marker 用 nonce 前缀校验**，但 nonce 的语义变了：伪造 marker 只能伪造"自己的输出"，判定结论已不在学员进程里，伪造不到。

实测收窄后的攻击面：学员 `json.load(open('plan.json'))` 只看到 `['assertionVars','cells','nonce']`，**`has refs? False`**；容器回传的是 `vars: {"df": {"kind":"repr","value":"None"}}` 这类值，不含任何 `passed`/`failed`。

**可行性前提已核实**：
- `learn_da_runner` 宿主 venv **没有** polars/duckdb/pyarrow（依赖只有 fastapi/uvicorn/pydantic-settings/docker/anyio），所以宿主判定进程不能放在 Runner 里。
- `learn_da` 后端 venv **有** polars 1.39.3 / duckdb 1.5.1 / pyarrow 25.0.1，且 `pyproject.toml:27-28` 已精确锁定版本、注释说明"判定与沙箱执行版本必须一致"。
- 因此**宿主判定进程应放在 `learn_da` 后端**，Runner 退化为"只执行、只回传变量值"。这也顺带解决了 P1-14（`_split_logs` 把 stderr 混进 stdout）与 P1-19（`RUNNER_ENV` fail-open）的一部分影响面：Runner 不再产出任何教学结论。

代价与权衡：
- 每次判定多一次 Arrow IPC 序列化/传输。**实测真实数据量级**（本机 polars 1.39.3，base64 后）：10 个参考结果里 9 个 ≤ 2.2 KB，最大 `07-t1-filtered-orders`（3722×3）为 **120.9 KB**；若学员提交整表 `orders ⋈ customers`（5000×16）则达 **1.39 MB**。仍在 `RUNNER_SESSION_MAX_DATASET_BYTES=2_000_000` 的同一量级，但**必须显式加一个回传上限**（建议复用该配置或新增 `ASSERTION_VAR_MAX_BYTES`），否则学员可以在 `assertionVars` 里声明一个巨大 DataFrame 把链路撑爆。若担心大表，可在容器侧先 `select` 出断言真正需要的列，或对 `frame_equal` 只回传 `hash` + `height` + `columns`（精度降到"整表指纹相等"，但对"是否与参考一致"这个语义足够）。
- `schema`/`sql_rows` 同样可走宿主判定（`schema` 只需列名/类型；`sql_rows` 只需 rows+columns，回传量远小于 DataFrame）。
- **`expr_true` 不适用**，见 A.3。

### A.3 `expr_true` 单独处理：它无法靠进程隔离修复

实测 87 条 `expr_true` 按「被比较的对象由谁定义」分两类（逐条清点，合计 87 = 66 + 21）：

- **数据课型（66 条，01–11 共 11 门）**：比较对象是 DataFrame/Series/标量/list/str，例如 `region_stats.height == 4`（`polars-groupby` t1）、`sorted(big_channels['channel'].to_list()) == ['app','web']`、`abs(filtered['list_amount'].sum() - 5373637.19) < 0.05`（`polars-lazy-pipeline` t1）、`order_count == 5000`（`duckdb-analytics` t1）、`'FILTER' in plan_text.upper()`（`polars-lazy-pipeline` t3）。这类**本就不该用自由表达式表达**——它们断言的是 DataFrame 的形状/内容或标量值，`frame_equal`/`schema` 能表达得更精确，且可搬到宿主判定。
- **纯 Python 课型（21 条，`python-functions` 11 条 + `python-collections` 10 条）**：比较对象是学员自己定义的函数返回值或容器，例如 `add_bonus(95) == 100`（`python-functions` t1）、`total_scores([]) == 0`（t2）、`grade_of(91) == 'A' and grade_of(76) == 'B' and grade_of(60) == 'C'`（t3）、`big_amounts == [899, 240, 620]`（`python-collections` t2）、`len(region_counts) == 4`（t3）。这类**必须让学员的对象参与运算**，无法序列化到宿主 → 只能靠"限制表达式能力"而非进程隔离。

对应的两步改法：

1. **短期（内容侧，无需改运行时）**：把 DataFrame 型 `expr_true` 逐条改写成 `frame_equal`（有 ref 的）或 `schema` + `frame_equal` 组合。`expr_true` 只保留纯 Python 函数型。
2. **中期（运行时侧）**：给断言加类型契约 ——
   ```yaml
   - id: t1-bonus          # python-functions t1 的现有断言
     type: call
     call: add_bonus(95)   # 固定输入，学员无法在中间插入对象
     expect: 100
   ```
   由运行时用**断言自带的固定输入**调用学员函数并比对返回值。学员仍然可以让函数返回固定值，但那是"函数实现了期望行为"的正常情形，不再有"传入万能对象让 `==` 恒真"的绕过路径。

3. **可选的纵深防御**：`expr_true` 保留时，运行时对 `namespace` 中参与比较的对象做 `isinstance` 白名单校验（只允许 `int/float/str/bool/list/tuple/dict/set/NoneType` 与 `polars.DataFrame/Series`），自定义类一律判 `error`。这能挡住鸭子类型 PoC，但挡不住"用白名单类型包装的伪造"（如返回一个恒为期望值的 list），所以只是纵深防御，不是根治。

### A.4 落地顺序建议

1. 先加**回归测试**（用本报告的五条 PoC），让当前实现红掉——否则改完无法证明修好了。
2. 再改结构（A.2），让 P0-1/2/3 三条测试转绿。
3. 再迁内容（A.3 第 1 步），把 DataFrame 型 `expr_true` 换成结构化断言，同步重跑 `build_expected.py` 生成 refs。
4. 最后加类型契约（A.3 第 2 步），让 P0-6 测试转绿。

**不要把第 2 步和第 3 步合并**：先改结构再迁内容，中间态（`expr_true` 仍在容器内求值）可以接受，因为此时至少 `frame_equal`/`schema` 已经不可伪造；反过来先迁内容再改结构，中间的 `frame_equal` 仍然可被 frame 爬取 refs 绕过，等于没修。

### A.5 可复现脚本

五条 PoC 已整理为 `learn_da_runner/scripts/poc_judgement_bypass.py`，它直接复制**仓库里真实的** `runner/session_driver.py` 与 `learn_da/app/practice/assertion_runtime.py` 到临时目录运行，不是模拟：

```bash
cd learn_da_runner
.venv/Scripts/python.exe scripts/poc_judgement_bypass.py
```

当前输出（5/5 全部成立）：

```
[PoC-1] atexit 伪造 driver marker        verdict='passed'  assertions=['passed']   -> 越权成立
[PoC-2] 同进程替换断言运行时               verdict='passed'  assertions=['passed']   -> 越权成立
[PoC-2b] frame 爬取 run_plan 的 plan      爬到 plan 于深度 2，refs=['expected/frame_secret.parquet'] -> 拿到 refs
[PoC-3] 读 plan.json 拿 refs              keys=['assertions','cells','refs','runtimeFile','stopAt'] -> refs 泄漏
[PoC-4] 鸭子类型绕过 expr_true            verdict='passed'  assertions=['passed']   -> 越权成立
```

这个脚本的解析逻辑与 `learn_da_runner/runner/session.py:98-106` 的 `parse_driver_output` 一致（反向扫描 marker 行），因此复现的是**真实解析路径**。

建议直接把五个用例改写成 `learn_da_runner/tests/test_session.py` 的 pytest 用例：每个用例断言"越权**不**成立"（`verdict != "passed"`、refs 不可读、`assertions` 不含 passed）。这样修完之后测试从红转绿，构成回归防线；`poc_judgement_bypass.py` 则可保留为"改完后应该输出 0/5"的验收脚本。

---

## 9. 最终结论

这轮重构把一个"看起来像学习平台"的产品改成了一个"真的会判定学习结果"的产品，方向、分层、内容工程化程度都比上一轮明显更高：13 课 51 个 cell 全部迁到工作区格式、122 条断言由 DSL 统一求值、10 个参考结果字节级可复现、分级提示的层级只由服务端算、证据链只读真实任务提交。这些都是**结构性**的进步，不是加功能。

同时，它把"判定是否可信"这个问题的边界推到了最后一米却没有跨过去：判定与学员代码共享进程和目录，五条最小 PoC 就能把"失败"改写成"通过"。在一个把 `TaskAttempt` 当教学证据核心、把证据喂给推荐与 AI 助手的系统里，这一米决定了上面所有分析的可信度。

需要说明的是，这一米**不能靠局部补丁跨过去**。我最初给的三条建议（refs 改 stdin、runtime 提前加载、marker 掺 nonce）都在本机实测中被自己的 PoC 逐条推翻——因为学员代码与判定逻辑同进程时，`sys._getframe` 和 `import __main__` 就是无界的能力。有效方案只有一个：**把判定移出学员进程**（附录 A.2），并承认 `expr_true` 这类"在学员命名空间里求表达式"的断言需要单独改造（附录 A.3）。

好消息是这条路不需要重新设计架构：`learn_da` 后端已经有锁定版本的 polars/duckdb/pyarrow，Arrow IPC 序列化往返实测无损，Runner 只需退化成"只执行、只回传变量值"。**按附录 A.4 的顺序（先补回归测试、再改结构、再迁内容、最后加类型契约）做完，加上幂等与限流的补齐，这个项目就可以从内部 Alpha 推到小范围公开 Beta。**
