# Data Analysis Platform Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition the frontend from a Polars/DuckDB-specific site into a data analysis learning platform while keeping Polars, DuckDB, and combined practice as the currently supported tracks.

**Architecture:** Keep backend categories unchanged for now (`polars`, `duckdb`, `combined`) to avoid broad data-model churn. Add a small frontend track configuration module so labels, icons, colors, descriptions, and supported-track messaging live in one place, then update Home, Navbar, Learning, Agent, Playground, and router title to use platform-level wording.

**Tech Stack:** Vue 3, TypeScript, Vite, existing Tailwind utility classes, current FastAPI-backed lesson categories.

---

## File Structure

- Create `learn_da_vue/src/lib/learningTracks.ts`: source of truth for current learning tracks and platform copy.
- Modify `learn_da_vue/src/types/api.ts`: keep `LessonCategory` unchanged in this phase.
- Modify `learn_da_vue/src/views/Home.vue`: change hero/platform positioning and use track config.
- Modify `learn_da_vue/src/views/Learning.vue`: use track config for category tabs/grouping, update page description.
- Modify `learn_da_vue/src/components/layout/Navbar.vue`: change brand from Polars+DuckDB to data analysis platform.
- Modify `learn_da_vue/src/router/index.ts`: change default site title.
- Modify `learn_da_vue/src/components/agent/AgentPanel.vue`: change visible positioning from "Polars · DuckDB 专家" to "数据分析助教", while quick questions can remain Polars/DuckDB-focused.
- Modify `learn_da_vue/src/views/Playground.vue` and `learn_da_vue/src/components/playground/TutorialSidebar.vue`: replace hardcoded category labels with track config where practical.

## Task 1: Add Frontend Learning Track Config

**Files:**
- Create: `learn_da_vue/src/lib/learningTracks.ts`
- Test: `learn_da_vue/src/views/Learning.vue`

- [ ] **Step 1: Write a failing import usage**

In `learn_da_vue/src/views/Learning.vue`, add this import near the existing imports:

```ts
import { currentTrackKeys, learningTrackMeta } from "@/lib/learningTracks";
```

Then replace the hardcoded grouped lesson key list:

```ts
return (["polars", "duckdb", "combined"] as LessonCategory[])
```

with:

```ts
return currentTrackKeys
```

Run:

```bash
npm run type-check
```

Expected: FAIL with `Cannot find module '@/lib/learningTracks'`.

- [ ] **Step 2: Create track config**

Create `learn_da_vue/src/lib/learningTracks.ts`:

```ts
import type { LessonCategory } from "@/types/api";

export interface LearningTrackMeta {
  key: LessonCategory;
  label: string;
  shortLabel: string;
  icon: string;
  subtitle: string;
  description: string;
  tags: string[];
  color: "blue" | "yellow" | "purple";
  route: string;
  lessonCount: number;
}

export const platformCopy = {
  name: "Learn DA",
  title: "数据分析学习平台",
  shortTitle: "数据分析平台",
  currentScope: "当前已开放 Polars、DuckDB 与组合实战专题",
  expansionHint: "后续可扩展 Pandas、SQL 基础、数据可视化、特征工程等方向。",
};

export const learningTracks: LearningTrackMeta[] = [
  {
    key: "polars",
    label: "Polars",
    shortLabel: "Polars",
    icon: "P",
    subtitle: "现代 DataFrame 库",
    description:
      "首批开放专题。学习高性能 DataFrame 数据处理、表达式系统、惰性执行与分组聚合。",
    tags: ["DataFrame", "惰性执行", "高性能", "Python"],
    color: "blue",
    route: "/learn?category=polars",
    lessonCount: 12,
  },
  {
    key: "duckdb",
    label: "DuckDB",
    shortLabel: "DuckDB",
    icon: "D",
    subtitle: "嵌入式分析数据库",
    description:
      "首批开放专题。学习在本地进程中用 SQL 查询 CSV、Parquet 与内存数据集。",
    tags: ["SQL", "OLAP", "零配置", "文件分析"],
    color: "yellow",
    route: "/learn?category=duckdb",
    lessonCount: 10,
  },
  {
    key: "combined",
    label: "组合实战",
    shortLabel: "实战",
    icon: "C",
    subtitle: "数据分析工作流",
    description:
      "把 Polars 与 DuckDB 放进完整分析流程，练习数据读取、转换、查询和结果输出。",
    tags: ["数据管道", "综合案例", "工作流"],
    color: "purple",
    route: "/learn?category=combined",
    lessonCount: 8,
  },
];

export const currentTrackKeys = learningTracks.map((track) => track.key);

export const learningTrackMeta = Object.fromEntries(
  learningTracks.map((track) => [track.key, track]),
) as Record<LessonCategory, LearningTrackMeta>;
```

- [ ] **Step 3: Verify module compiles**

Run:

```bash
npm run type-check
```

Expected: PASS after the remaining hardcoded Learning imports are still valid.

## Task 2: Update Learning Center to Use Track Config

**Files:**
- Modify: `learn_da_vue/src/views/Learning.vue`

- [ ] **Step 1: Replace category config**

Replace the `categories` constant with:

```ts
const categories: {
    key: LessonCategory | "all";
    label: string;
    icon: string;
}[] = [
    { key: "all", label: "全部专题", icon: "All" },
    ...currentTrackKeys.map((key) => ({
        key,
        label: learningTrackMeta[key].label,
        icon: learningTrackMeta[key].icon,
    })),
];
```

Replace `categoryIcon` with:

```ts
const categoryIcon: Record<LessonCategory, string> = Object.fromEntries(
    currentTrackKeys.map((key) => [key, learningTrackMeta[key].icon]),
) as Record<LessonCategory, string>;
```

Keep `categoryColor` unchanged for now because it maps existing Tailwind classes.

- [ ] **Step 2: Replace query category allowlist**

Replace:

```ts
["polars", "duckdb", "combined"].includes(queryCategory)
```

with:

```ts
currentTrackKeys.includes(queryCategory)
```

- [ ] **Step 3: Update visible Learning page copy**

In the page header area, add a short subtitle under `学习中心`:

```vue
<p class="hidden md:block text-xs text-slate-500 mt-0.5">
    按专题学习数据分析工具与方法，当前支持 Polars / DuckDB。
</p>
```

Change search placeholder from:

```vue
placeholder="搜索课程..."
```

to:

```vue
placeholder="搜索课程或专题..."
```

- [ ] **Step 4: Verify Learning compiles**

Run:

```bash
npm run type-check
```

Expected: PASS.

## Task 3: Update Home Page Positioning

**Files:**
- Modify: `learn_da_vue/src/views/Home.vue`

- [ ] **Step 1: Import platform and track config**

Add:

```ts
import { learningTracks, platformCopy } from "@/lib/learningTracks";
```

Replace the hardcoded `learningPaths` array with:

```ts
const learningPaths = learningTracks.map((track) => ({
  id: track.key,
  icon: track.icon,
  title: track.label,
  subtitle: track.subtitle,
  description: track.description,
  tags: track.tags,
  color: track.color,
  slug: track.route,
  lessonCount: track.lessonCount,
}));
```

- [ ] **Step 2: Replace platform-level hero copy**

Change the badge text:

```vue
交互式数据分析学习平台
```

to:

```vue
{{ platformCopy.title }}
```

Change hero title from toolchain-specific wording to:

```vue
系统学习
<span class="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">数据分析</span>
<br />
<span class="text-white/90">实战技能</span>
```

Change the subtitle paragraph to:

```vue
从数据读取、清洗、查询到结果验证，在浏览器里完成可运行的练习。
当前开放 <code class="px-1.5 py-0.5 rounded bg-white/10 text-blue-300 font-mono text-base">Polars</code>
与
<code class="px-1.5 py-0.5 rounded bg-white/10 text-yellow-300 font-mono text-base">DuckDB</code>
专题，后续持续扩展更多数据分析方向。
```

- [ ] **Step 3: Update section copy**

Change "选择你的学习路径" description to:

```vue
先从当前开放专题入手，逐步扩展到更完整的数据分析技能体系。
```

Change feature "一键运行沙箱" description to:

```ts
desc: "代码在安全隔离的沙箱中执行，当前支持 Polars、DuckDB 相关练习。",
```

- [ ] **Step 4: Verify Home compiles**

Run:

```bash
npm run type-check
```

Expected: PASS.

## Task 4: Update Navbar and Router Title

**Files:**
- Modify: `learn_da_vue/src/components/layout/Navbar.vue`
- Modify: `learn_da_vue/src/router/index.ts`

- [ ] **Step 1: Update Navbar brand**

In `Navbar.vue`, import:

```ts
import { platformCopy } from '@/lib/learningTracks'
```

Replace the visible brand text:

```vue
Polars
<span class="text-blue-500">+</span>
DuckDB
```

with:

```vue
{{ platformCopy.name }}
```

Replace the subtitle:

```vue
交互式学习平台
```

with:

```vue
{{ platformCopy.title }}
```

- [ ] **Step 2: Update default document title**

In `learn_da_vue/src/router/index.ts`, replace:

```ts
const siteTitle = import.meta.env.VITE_APP_TITLE ?? 'Polars+DuckDB 学习平台'
```

with:

```ts
const siteTitle = import.meta.env.VITE_APP_TITLE ?? '数据分析学习平台'
```

- [ ] **Step 3: Verify app title compiles**

Run:

```bash
npm run type-check
```

Expected: PASS.

## Task 5: Update Agent and Playground Visible Positioning

**Files:**
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`
- Modify: `learn_da_vue/src/views/Playground.vue`
- Modify: `learn_da_vue/src/components/playground/TutorialSidebar.vue`

- [ ] **Step 1: Update Agent welcome and status text**

In `AgentPanel.vue`, change welcome content from:

```ts
"你好！我是你的 **AI 学习助手** 🤖\n\n我可以帮你：\n- 解释 Polars / DuckDB 的概念和 API\n- 分析并修复代码中的错误\n- 生成示例代码\n- 回答数据分析相关问题\n\n有什么问题尽管问吧！"
```

to:

```ts
"你好！我是你的 **AI 数据分析助教**\n\n我可以帮你：\n- 解释当前开放专题中的概念和 API\n- 分析并修复 Playground 代码错误\n- 生成可运行的数据分析示例\n- 回答 Polars / DuckDB 等数据分析相关问题\n\n有什么问题尽管问吧！"
```

Change the header subtitle from:

```vue
: "Polars · DuckDB 专家"
```

to:

```vue
: "数据分析助教"
```

- [ ] **Step 2: Keep quick questions focused**

Do not remove Polars/DuckDB quick questions yet. They accurately reflect current supported content and should be revisited when more tracks are added.

- [ ] **Step 3: Update Playground labels only where they imply global scope**

In `Playground.vue`, keep language/tool labels such as `Polars` and `DuckDB SQL` because they describe current runtime modes. Replace broad copy such as "支持 Polars、DuckDB 全部 API" with "当前支持 Polars、DuckDB 相关练习" if present.

In `TutorialSidebar.vue`, keep category labels because they map current lessons.

- [ ] **Step 4: Verify frontend type-check**

Run:

```bash
npm run type-check
```

Expected: PASS.

## Task 6: Final Verification

**Files:**
- Test only.

- [ ] **Step 1: Run frontend type-check**

Run:

```bash
npm run type-check
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm run build
```

Expected: PASS. Existing Vite chunk warnings are acceptable if no errors occur.

- [ ] **Step 3: Run backend smoke tests**

Run:

```bash
uv run pytest tests/test_health.py -q
```

from `learn_da`.

Expected: PASS. Backend behavior should not change in this phase.

## Self-Review

- Spec coverage: The plan changes product positioning, keeps current supported topics visible, and introduces a frontend track configuration for later expansion.
- Placeholder scan: No placeholders remain; implementation steps include concrete code snippets and exact commands.
- Type consistency: `LessonCategory` remains unchanged; new `learningTracks` config is typed against existing categories.

