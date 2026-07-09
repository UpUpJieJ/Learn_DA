# 平台定位文案更新：去除「迁移到 Polars/DuckDB」专属框架

**Date:** 2026-07-09
**Status:** 计划中，待执行
**Owner:** Learn DA
**起因:** 平台已不再专属 Polars / DuckDB（已新增 `programming` 主题与 Python 路径，未来可能加入 Pandas 等），首页与宣传文案中「从 Pandas / SQL 迁移到 Polars / DuckDB」的定位已不妥，需更新为「可扩展的数据分析与编程学习平台」。

---

## 0. 一句话结论

后端 `catalog.yml` 的平台定位已是通用的（`自由添加学习主题，边学边练，持续沉淀`），但**前端文案层 `learn_da_vue/src/lib/learningTracks.ts` 的 `platformCopy` 仍是旧的"迁移"专属定位，并作为导航/兜底直接展示**。本次任务把前端文案、Navbar、README、页面标题统一对齐到 catalog 的通用定位，保留课程内部的迁移类比作为教学手段（不作为平台身份）。

---

## 1. 现状盘点（两层文案模型）

平台文案实际有「后端驱动」+「前端兜底」两层：

| 层 | 来源 | 当前内容 | 状态 |
|---|---|---|---|
| 后端驱动（线上优先） | [catalog.yml:1-4](../../../../content/catalog.yml) | `name: Learn DA` / `title: 交互式学习平台` / `subtitle: 自由添加学习主题，边学边练，持续沉淀` | ✅ 已通用 |
| 前端兜底（API 失败时/部分组件直接用） | [learningTracks.ts:18-28](../../../../learn_da_vue/src/lib/learningTracks.ts) `platformCopy` | `title: "Pandas / SQL 迁移到 Polars / DuckDB"` 等一整套迁移文案 | ❌ 仍旧定位 |

**关键问题**: Navbar 直接读 `platformCopy`（不经 catalog），所以导航栏**始终**显示旧的迁移副标题，与首页 catalog 驱动的通用标题自相矛盾。

### 1.1 受影响位置清单

| # | 位置 | 问题文本 | 类型 |
|---|---|---|---|
| 1 | `learn_da_vue/src/lib/learningTracks.ts:20` | `title: "Pandas / SQL 迁移到 Polars / DuckDB"` | 核心文案 |
| 2 | `learn_da_vue/src/lib/learningTracks.ts:21` | `shortTitle: "迁移学习平台"` | 核心文案 |
| 3 | `learn_da_vue/src/lib/learningTracks.ts:22-23` | `heroTitle: "从 Pandas / SQL"` / `heroTitleHighlight: "迁移到 Polars / DuckDB"` | 首页 Hero |
| 4 | `learn_da_vue/src/lib/learningTracks.ts:24-25` | `heroSubtitle: "...把熟悉的分析习惯迁移到 Polars / DuckDB。"` | 首页 Hero |
| 5 | `learn_da_vue/src/lib/learningTracks.ts:26` | `currentScope: "当前版本聚焦 11 节核心课程与 3 条迁移路径"` | **过期数据**（实为 13 课/4 路径）+ 迁移措辞 |
| 6 | `learn_da_vue/src/lib/learningTracks.ts:27` | `expansionHint: "后续可扩展更多数据分析迁移方向。"` | 迁移措辞 |
| 7 | `learn_da_vue/src/lib/learningTracks.ts:33,38` | polars 轨道 `label: "Pandas -> Polars"` / `targetAudience: "有 Pandas 基础，想迁移到..."` | 轨道文案 |
| 8 | `learn_da_vue/src/lib/learningTracks.ts:49,54` | duckdb 轨道 `label: "SQL -> DuckDB"` / `targetAudience: "有 SQL 基础..."` | 轨道文案 |
| 9 | `learn_da_vue/src/components/layout/Navbar.vue:96,99` | 直接渲染 `platformCopy.name` + `platformCopy.title` → 导航栏显示迁移副标题 | **始终可见** |
| 10 | `README.md:1` | `# Learn DA -- Polars + DuckDB 交互式学习平台` | 项目门面 |
| 11 | `README.md:3` | `专注解决 Polars 和 DuckDB 入门、进阶与实战痛点` | 项目简介 |
| 12 | `README.md:13` | `覆盖 Polars 专项、DuckDB 专项、Polars + DuckDB 联用实战...` | 特性描述 |
| 13 | `learn_da_vue/index.html:6` | `<title>Vite App</title>` | 顺手修正（品牌/SEO） |
| 14 | `learn_da/content/catalog.yml:8` | `data-analysis` 主题描述 `Polars、DuckDB 与现代数据分析工作流` | 可加 Pandas 前瞻 |

### 1.2 明确不改动项（保留为教学手段，非平台身份）

- 课程内部迁移类比：`content/lessons/01-polars-basics.md`「从 Pandas 迁移的直觉对照」、`03-polars-groupby.md`「把 Pandas 的 groupby 迁移到 Polars」。在 Polars 课内用 Pandas 做对照是合理教学法，**保留**。
- Agent 面板在 polars/duckdb/combined 课内出现的「迁移到 Polars/DuckDB」快捷动作（[AgentPanel.vue:140-155](../../../../learn_da_vue/src/components/agent/AgentPanel.vue)）：作为**课程上下文内的学习辅助**可保留，但建议弱化措辞（见任务 T5）。

---

## 2. 新定位方向

与 `catalog.yml` 已有定位一致，不再以"迁移"为身份：

> **Learn DA —— 可扩展的交互式数据分析与编程学习平台**
> 围绕数据分析与现代编程，用课程、练习、Playground 和学习教练，把概念理解落到可运行的代码上。主题与路径可按需扩展，不再绑定某一组技术栈。

设计原则：
- ✅ 平台身份 = 通用学习平台（数据分析 + 编程），不绑定具体技术栈
- ✅ "迁移"仅作为 polars/duckdb 等具体课程内的教学对照手段
- ✅ 文案中提及技术栈时用「等」做开放式列举（为 Pandas 等未来主题留口子）
- ❌ 不再把"从 Pandas/SQL 迁移到 Polars/DuckDB"作为平台 slogan
- ❌ 不在平台层文案做排他性技术栈承诺

---

## 3. 任务清单

优先级：P0 = 用户直接可见的定位偏差；P1 = 过期数据/品牌一致性；P2 = 锦上添花。

### T1【P0】重写 `platformCopy` 为通用定位
**文件**: `learn_da_vue/src/lib/learningTracks.ts:18-28`
**动作**: 把 `platformCopy` 整体替换为通用文案（建议如下，可调整）：
```ts
export const platformCopy = {
  name: "Learn DA",
  title: "交互式数据分析学习平台",
  shortTitle: "学习平台",
  heroTitle: "边学边练",
  heroTitleHighlight: "数据分析与编程实战",
  heroSubtitle:
    "围绕数据分析与现代编程的学习平台，用课程、练习、Playground 和学习教练，把概念理解落到可运行的代码上。",
  currentScope: "持续更新的课程与学习路径",   // 避免硬编码数字再次过期
  expansionHint: "可按需扩展更多数据分析与编程主题。",
};
```
**验收**: Navbar 副标题不再出现"迁移"字样；首页 Hero 在 catalog 未加载时也显示通用文案。

### T2【P0】去除 `learningTracks` 轨道文案的迁移措辞
**文件**: `learn_da_vue/src/lib/learningTracks.ts:30-79`
**动作**:
- polars 轨道 `label: "Pandas -> Polars"` → `"Polars 基础"`（与 catalog 轨道 label 对齐）
- polars `targetAudience` 去掉"有 Pandas 基础，想迁移"→ `"想学习高性能 DataFrame 的学习者"`
- duckdb 轨道 `label: "SQL -> DuckDB"` → `"DuckDB 基础"`
- duckdb `targetAudience` → `"想在 Python 环境中直接跑分析查询的学习者"`
- 顺手补齐 python 轨道到兜底列表（catalog 已有 `python_basics`，兜底缺它），或评估直接移除 legacy 兜底（见 T6）。
**验收**: catalog API 失败时首页轨道卡片不出现"->"迁移式标题。

### T3【P0】修正 README 门面文案
**文件**: `README.md:1,3,13`
**动作**:
- L1: `# Learn DA -- Polars + DuckDB 交互式学习平台` → `# Learn DA -- 交互式数据分析学习平台`
- L3: `专注解决 Polars 和 DuckDB 入门、进阶与实战痛点` → `覆盖 Polars、DuckDB 等现代数据分析工具与编程基础，从入门到实战`
- L13: `覆盖 Polars 专项、DuckDB 专项、Polars + DuckDB 联用实战与常见问题汇总` → `覆盖 Polars、DuckDB、组合实战与 Python 编程基础等主题，课程列表支持专题、难度与关键词过滤`
**验收**: README 首屏不再以 Polars/DuckDB 专属自居。

### T4【P1】修正页面标题与 catalog 主题描述
**文件**: `learn_da_vue/index.html:6`、`learn_da/content/catalog.yml:8`
**动作**:
- `index.html`: `<title>Vite App</title>` → `<title>Learn DA - 交互式数据分析学习平台</title>`
- `catalog.yml` data-analysis 主题: `Polars、DuckDB 与现代数据分析工作流` → `Polars、DuckDB、Pandas 等现代数据分析工作流`（为 Pandas 留口子）
**验收**: 浏览器标签页显示 Learn DA；主题描述含开放式列举。

### T5【P2】弱化 Agent 面板的"迁移"措辞（保留功能）
**文件**: `learn_da_vue/src/components/agent/AgentPanel.vue:60-61,140-155`
**动作**:
- `isDataMigrationContext` 重命名为 `supportsMigrationAnalogy`（去身份化命名）
- 快捷动作 label `"迁移到 Polars"` → `"Pandas 对照"`、`"迁移到 DuckDB"` → `"SQL 对照"`（保留 prompt 逻辑，仅弱化措辞）
**验收**: polars/duckdb 课内仍出现对照快捷动作，但文案不再以"迁移"为框架。

### T6【P2·可选】评估移除 `learningTracks` legacy 兜底
**背景**: catalog 已是唯一事实源，legacy 兜底仅为 catalog API 失败时兜底，且易与 catalog 漂移（如本次）。
**动作**: 评估 Home.vue 是否可在 catalog 失败时直接展示静态通用文案，移除 `learningTracks` 数组与 `legacyPaths` 分支，降低长期维护成本。
**验收**: 决策记录在本计划；若移除，Home.vue 在 catalog 失败时仍能渲染通用首页。

---

## 4. 下一步行动（执行顺序）

```
第 1 步（立即可做，低风险）: T1 + T2 + T3 + T4
   └─ 纯文案改动，前后端不涉及逻辑变更
   └─ 改完本地 `npm run dev` 跑一遍首页/导航，核对 Hero、Navbar、轨道卡片
   └─ 提交一次：「更新平台定位文案，去除 Polars/DuckDB 迁移专属框架」

第 2 步（视反馈）: T5
   └─ Agent 面板措辞弱化，需在 polars/duckdb 课内手测快捷动作仍可用

第 3 步（架构性，单独评估）: T6
   └─ 是否移除 legacy 兜底，单独决策与实施
```

### 4.1 验收总览
- [ ] Navbar 副标题、首页 Hero 全程无"迁移"字样
- [ ] catalog API 失败兜底文案也通用化
- [ ] README 首屏、浏览器标题与平台定位一致
- [ ] 课程内部 Pandas/SQL 对照教学保留不变
- [ ] Agent 在 polars/duckdb 课内对照功能仍可用（若执行 T5）

---

## 5. 风险与回滚

- **风险**: `platformCopy` 字段被多处引用，改值不删字段，避免破坏引用。
- **回滚**: 文案改动均为纯文本，git revert 单提交即可。
- **注意**: T6 涉及删代码分支，单独评估、单独提交，便于回滚。

---

## 6. 范围之外（明确排除）

- 不新增 Pandas 课程内容（仅文案为未来主题留口子）
- 不重构首页布局或视觉风格
- 不改动 Agent 核心逻辑（仅 T5 弱化措辞）
- 不动课程 Markdown 内的教学性迁移类比
