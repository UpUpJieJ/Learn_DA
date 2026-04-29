<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { fetchLessonBySlug } from "@/api/learning";
import type { LessonDetail, LessonDifficulty } from "@/types/api";
import { useUserStore } from "@/stores/user";
import { usePlaygroundStore } from "@/stores/playground";

// =====================================================
// Props
// =====================================================

const props = defineProps<{
    slug: string;
}>();

// =====================================================
// 依赖
// =====================================================

const router = useRouter();
const userStore = useUserStore();
const playgroundStore = usePlaygroundStore();

// =====================================================
// 状态
// =====================================================

const lesson = ref<LessonDetail | null>(null);
const isLoading = ref(false);
const errorMsg = ref<string | null>(null);

// 目录锚点
const activeAnchor = ref("");
const tocItems = ref<{ id: string; text: string; level: number }[]>([]);

// 代码块复制状态
const copiedBlockId = ref<string | null>(null);

// =====================================================
// 配置映射
// =====================================================

const difficultyLabel: Record<LessonDifficulty, string> = {
    beginner: "入门",
    intermediate: "进阶",
    advanced: "高级",
};

const difficultyColor: Record<LessonDifficulty, string> = {
    beginner: "bg-emerald-100 text-emerald-700 border-emerald-200",
    intermediate: "bg-blue-100 text-blue-700 border-blue-200",
    advanced: "bg-purple-100 text-purple-700 border-purple-200",
};

const categoryLabel: Record<string, string> = {
    polars: "🐻‍❄️ Polars",
    duckdb: "🦆 DuckDB",
    combined: "⚡ 组合实战",
};

// =====================================================
// 数据加载
// =====================================================

async function loadLesson(slug: string) {
    isLoading.value = true;
    errorMsg.value = null;
    lesson.value = null;
    tocItems.value = [];
    activeAnchor.value = "";

    try {
        lesson.value = await fetchLessonBySlug(slug);
        userStore.setLastVisitedLesson(slug);

        // 等 DOM 渲染后提取目录
        await nextTick();
        extractToc();
        setupScrollSpy();
    } catch (err) {
        errorMsg.value =
            err instanceof Error ? err.message : "课程内容加载失败，请稍后重试";
        // 开发期间注入 mock 数据
        lesson.value = generateMockLesson(slug);
        await nextTick();
        extractToc();
        setupScrollSpy();
    } finally {
        isLoading.value = false;
    }
}

// slug 变化时重新加载
watch(() => props.slug, loadLesson, { immediate: false });
onMounted(() => loadLesson(props.slug));

// =====================================================
// 目录（TOC）提取
// =====================================================

function extractToc() {
    const container = document.getElementById("lesson-content");
    if (!container) return;

    const headings = container.querySelectorAll("h2, h3");
    tocItems.value = Array.from(headings).map((el, idx) => {
        const id = el.id || `heading-${idx}`;
        el.id = id;
        return {
            id,
            text: el.textContent ?? "",
            level: parseInt(el.tagName[1] ?? "2"),
        };
    });
}

// 滚动监听，高亮当前目录项
let scrollCleanup: (() => void) | null = null;

function setupScrollSpy() {
    if (scrollCleanup) scrollCleanup();

    const handler = () => {
        const headings = tocItems.value
            .map((item) => document.getElementById(item.id))
            .filter(Boolean) as HTMLElement[];

        const scrollY = window.scrollY + 120;

        let current = headings[0]?.id ?? "";
        for (const el of headings) {
            if (el.offsetTop <= scrollY) {
                current = el.id;
            }
        }
        activeAnchor.value = current;
    };

    window.addEventListener("scroll", handler, { passive: true });
    scrollCleanup = () => window.removeEventListener("scroll", handler);
}

// =====================================================
// 完成标记
// =====================================================

const isCompleted = computed(() =>
    lesson.value ? userStore.isLessonCompleted(lesson.value.slug) : false,
);

function toggleCompleted() {
    if (!lesson.value) return;
    userStore.toggleLessonCompleted(lesson.value.slug);
}

// =====================================================
// 在 Playground 中打开示例代码
// =====================================================

function openInPlayground(code?: string) {
    const target = code ?? lesson.value?.codeExample ?? "";
    if (!target.trim()) return;

    playgroundStore.setCode(target);
    router.push(`/playground/${lesson.value?.slug ?? ''}`);
}

// =====================================================
// 代码块复制
// =====================================================

async function copyCode(code: string, blockId: string) {
    try {
        await navigator.clipboard.writeText(code);
        copiedBlockId.value = blockId;
        setTimeout(() => {
            if (copiedBlockId.value === blockId) {
                copiedBlockId.value = null;
            }
        }, 2000);
    } catch {
        console.warn("复制失败，请手动复制");
    }
}

// =====================================================
// 导航
// =====================================================

function scrollToAnchor(id: string) {
    const el = document.getElementById(id);
    if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function goToLesson(slug: string) {
    router.push(`/learn/${slug}`);
}

// =====================================================
// nextTick 兼容（script setup 中需显式导入）
// =====================================================

import { nextTick } from "vue";

// =====================================================
// 简易 Markdown 渲染（无外部依赖，后续可替换为 marked/markdown-it）
// =====================================================

function renderMarkdown(md: string): string {
    if (!md) return "";

    let html = md
        // 转义 HTML 特殊字符（仅在代码块外）
        // 代码块（```lang ... ```）
        .replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
            const escaped = code
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
            const langClass = lang ? ` class="language-${lang}"` : "";
            return `<pre class="code-block" data-lang="${lang || "text"}"><code${langClass}>${escaped}</code></pre>`;
        })
        // 行内代码
        .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
        // 标题 h1-h4
        .replace(/^#### (.+)$/gm, "<h4>$1</h4>")
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        // 粗体 / 斜体
        .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        // 无序列表
        .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
        .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, "<ul>$&</ul>")
        // 有序列表
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
        // 水平线
        .replace(/^---+$/gm, "<hr />")
        // 引用块
        .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
        // 链接
        .replace(
            /\[([^\]]+)\]\(([^)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener">$1</a>',
        )
        // 段落（连续空行分段）
        .replace(/\n{2,}/g, "</p><p>");

    return `<p>${html}</p>`;
}

// =====================================================
// Mock 数据（后端未就绪时使用）
// =====================================================

function generateMockLesson(slug: string): LessonDetail {
    return {
        id: 1,
        slug,
        title: "Polars 快速入门",
        description:
            "5 分钟掌握 Polars 基本用法，创建 DataFrame、查询数据、基础变换。",
        category: "polars",
        difficulty: "beginner",
        estimatedMinutes: 15,
        order: 1,
        tags: ["DataFrame", "入门", "基础操作"],
        content: `## 什么是 Polars？

Polars 是一个基于 **Rust** 构建的高性能 DataFrame 库，提供 Python 和 Rust 两种 API。
与 Pandas 相比，Polars 具有以下核心优势：

- **速度极快**：基于 Apache Arrow 内存格式，原生支持 SIMD 向量化运算
- **惰性求值**：通过 \`LazyFrame\` 构建查询计划，自动优化执行路径
- **并行计算**：自动利用多核 CPU，无需手动配置
- **内存高效**：零拷贝读写，显著降低内存占用
- **类型安全**：强类型系统，运行前即可发现错误

## 安装

\`\`\`bash
pip install polars
\`\`\`

## 创建 DataFrame

Polars 支持从多种数据源创建 DataFrame：

\`\`\`python
import polars as pl

# 从字典创建
df = pl.DataFrame({
    "name": ["Alice", "Bob", "Charlie", "Diana"],
    "age": [25, 30, 35, 28],
    "city": ["北京", "上海", "深圳", "广州"],
    "score": [88.5, 92.0, 78.3, 95.1],
})

print(df)
print(f"\\n形状: {df.shape}")
print(f"列名: {df.columns}")
print(f"数据类型:\\n{df.dtypes}")
\`\`\`

## 基础查询

### 选择列

\`\`\`python
# 选择单列（返回 Series）
ages = df["age"]

# 选择多列（返回 DataFrame）
subset = df.select(["name", "score"])

# 使用表达式选择
result = df.select(
    pl.col("name"),
    pl.col("score").alias("成绩"),
)
\`\`\`

### 过滤行

\`\`\`python
# 简单过滤
high_scorers = df.filter(pl.col("score") > 90)

# 复合条件
result = df.filter(
    (pl.col("age") >= 28) & (pl.col("score") > 85)
)
\`\`\`

### 排序

\`\`\`python
# 按单列排序（降序）
sorted_df = df.sort("score", descending=True)

# 多列排序
sorted_df = df.sort(["age", "score"], descending=[False, True])
\`\`\`

## 数据变换

\`\`\`python
# 添加新列
df_with_grade = df.with_columns(
    pl.when(pl.col("score") >= 90)
    .then(pl.lit("A"))
    .when(pl.col("score") >= 80)
    .then(pl.lit("B"))
    .otherwise(pl.lit("C"))
    .alias("grade")
)

print(df_with_grade)
\`\`\`

## 聚合统计

\`\`\`python
# 全局统计
summary = df.select([
    pl.col("score").mean().alias("平均分"),
    pl.col("score").max().alias("最高分"),
    pl.col("score").min().alias("最低分"),
    pl.col("score").std().alias("标准差"),
])

# 分组聚合
city_stats = df.group_by("city").agg([
    pl.col("score").mean().alias("avg_score"),
    pl.col("name").count().alias("人数"),
]).sort("avg_score", descending=True)

print(city_stats)
\`\`\`

## 小结

本节我们学习了 Polars 的基本用法，包括：

1. 创建 DataFrame
2. 选择列与过滤行
3. 数据排序与变换
4. 聚合统计操作

下一节将深入学习 **Polars 表达式系统**，这是 Polars 最核心也最强大的特性。
`,
        codeExample: `import polars as pl

# 创建示例 DataFrame
df = pl.DataFrame({
    "name": ["Alice", "Bob", "Charlie", "Diana"],
    "age": [25, 30, 35, 28],
    "city": ["北京", "上海", "深圳", "广州"],
    "score": [88.5, 92.0, 78.3, 95.1],
})

print("原始数据：")
print(df)

# 过滤：成绩 > 85 的同学
high_scorers = df.filter(pl.col("score") > 85)
print("\\n成绩 > 85：")
print(high_scorers)

# 添加等级列
result = df.with_columns(
    pl.when(pl.col("score") >= 90)
    .then(pl.lit("A"))
    .when(pl.col("score") >= 80)
    .then(pl.lit("B"))
    .otherwise(pl.lit("C"))
    .alias("grade")
).sort("score", descending=True)

print("\\n带等级排序后：")
print(result)
`,
        prevLesson: null,
        nextLesson: {
            slug: "polars-expressions",
            title: "Polars 表达式系统",
        },
    };
}
</script>

<template>
    <div class="min-h-screen bg-slate-50">
        <!-- ================================================
         加载状态
    ================================================= -->
        <div
            v-if="isLoading"
            class="flex flex-col items-center justify-center min-h-screen gap-4"
        >
            <div
                class="w-10 h-10 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin"
            />
            <p class="text-sm text-slate-500">正在加载课程内容…</p>
        </div>

        <!-- ================================================
         错误状态
    ================================================= -->
        <div
            v-else-if="errorMsg && !lesson"
            class="flex flex-col items-center justify-center min-h-screen gap-4 px-6"
        >
            <div class="text-5xl">😵</div>
            <h2 class="text-xl font-bold text-slate-700">课程加载失败</h2>
            <p class="text-sm text-slate-500 text-center max-w-sm">
                {{ errorMsg }}
            </p>
            <div class="flex gap-3">
                <button
                    class="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                    @click="loadLesson(props.slug)"
                >
                    重新加载
                </button>
                <button
                    class="px-5 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-colors"
                    @click="router.push('/learn')"
                >
                    返回课程列表
                </button>
            </div>
        </div>

        <!-- ================================================
         正常内容
    ================================================= -->
        <template v-else-if="lesson">
            <!-- 顶部导航面包屑 -->
            <div class="bg-white border-b border-slate-100 sticky top-0 z-20">
                <div
                    class="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between gap-4"
                >
                    <!-- 面包屑 -->
                    <nav class="flex items-center gap-1.5 text-sm min-w-0">
                        <button
                            class="text-slate-400 hover:text-slate-600 transition-colors shrink-0"
                            @click="router.push('/learn')"
                        >
                            学习中心
                        </button>
                        <svg
                            class="w-4 h-4 text-slate-300 shrink-0"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                stroke-width="2"
                                d="M9 5l7 7-7 7"
                            />
                        </svg>
                        <span class="text-slate-500 truncate">{{
                            lesson.title
                        }}</span>
                    </nav>

                    <!-- 右侧操作区 -->
                    <div class="flex items-center gap-2 shrink-0">
                        <!-- 在 Playground 打开 -->
                        <button
                            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-700 text-white text-xs font-medium transition-colors"
                            @click="openInPlayground()"
                        >
                            <svg
                                class="w-3.5 h-3.5 text-emerald-400"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                                <path
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    stroke-width="2"
                                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                                />
                                <path
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    stroke-width="2"
                                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                />
                            </svg>
                            在 Playground 中运行
                        </button>

                        <!-- 标记完成 -->
                        <button
                            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium border transition-all duration-150"
                            :class="
                                isCompleted
                                    ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                                    : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300 hover:text-slate-800'
                            "
                            @click="toggleCompleted"
                        >
                            <svg
                                class="w-3.5 h-3.5"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                                <path
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                    stroke-width="2"
                                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                />
                            </svg>
                            {{ isCompleted ? "已完成" : "标记完成" }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- 主体布局 -->
            <div class="max-w-7xl mx-auto px-6 py-8 flex gap-8">
                <!-- ================================================
             主内容区
        ================================================= -->
                <main class="flex-1 min-w-0">
                    <!-- 课程头部信息 -->
                    <header class="mb-8">
                        <!-- 分类 + 难度 + 耗时 -->
                        <div class="flex flex-wrap items-center gap-2 mb-4">
                            <span
                                class="px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-medium"
                            >
                                {{
                                    categoryLabel[lesson.category] ??
                                    lesson.category
                                }}
                            </span>
                            <span
                                class="px-2.5 py-1 rounded-full text-xs font-medium border"
                                :class="difficultyColor[lesson.difficulty]"
                            >
                                {{ difficultyLabel[lesson.difficulty] }}
                            </span>
                            <span
                                class="flex items-center gap-1 text-xs text-slate-400"
                            >
                                <svg
                                    class="w-3.5 h-3.5"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                                    />
                                </svg>
                                约 {{ lesson.estimatedMinutes }} 分钟
                            </span>
                        </div>

                        <!-- 标题 -->
                        <h1
                            class="text-3xl font-bold text-slate-900 mb-3 leading-tight"
                        >
                            {{ lesson.title }}
                        </h1>

                        <!-- 描述 -->
                        <p
                            class="text-base text-slate-500 leading-relaxed mb-4"
                        >
                            {{ lesson.description }}
                        </p>

                        <!-- 标签 -->
                        <div class="flex flex-wrap gap-2">
                            <span
                                v-for="tag in lesson.tags"
                                :key="tag"
                                class="px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 text-xs font-medium"
                            >
                                # {{ tag }}
                            </span>
                        </div>

                        <!-- 分割线 -->
                        <div class="mt-6 border-t border-slate-100" />
                    </header>

                    <!-- ================================================
               Markdown 正文内容
          ================================================= -->
                    <div
                        id="lesson-content"
                        class="lesson-content prose prose-slate max-w-none"
                        v-html="renderMarkdown(lesson.content)"
                    />

                    <!-- ================================================
               示例代码卡片
          ================================================= -->
                    <div
                        v-if="lesson.codeExample"
                        class="mt-10 rounded-2xl overflow-hidden border border-slate-200 shadow-sm"
                    >
                        <!-- 卡片头 -->
                        <div
                            class="flex items-center justify-between px-5 py-3.5 bg-[#2d2d2d] border-b border-slate-700"
                        >
                            <div class="flex items-center gap-3">
                                <div class="flex gap-1.5">
                                    <span
                                        class="w-3 h-3 rounded-full bg-red-500/80"
                                    />
                                    <span
                                        class="w-3 h-3 rounded-full bg-yellow-500/80"
                                    />
                                    <span
                                        class="w-3 h-3 rounded-full bg-emerald-500/80"
                                    />
                                </div>
                                <span class="text-sm font-medium text-slate-300"
                                    >完整示例代码</span
                                >
                                <span
                                    class="px-2 py-0.5 rounded text-xs bg-blue-600/30 text-blue-300 font-mono"
                                >
                                    Python
                                </span>
                            </div>

                            <div class="flex items-center gap-2">
                                <!-- 复制按钮 -->
                                <button
                                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                                    :class="
                                        copiedBlockId === 'example'
                                            ? 'bg-emerald-600/20 text-emerald-400'
                                            : 'bg-white/10 text-slate-300 hover:bg-white/20'
                                    "
                                    @click="
                                        copyCode(lesson!.codeExample, 'example')
                                    "
                                >
                                    <svg
                                        v-if="copiedBlockId !== 'example'"
                                        class="w-3.5 h-3.5"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                                        />
                                    </svg>
                                    <svg
                                        v-else
                                        class="w-3.5 h-3.5"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M5 13l4 4L19 7"
                                        />
                                    </svg>
                                    {{
                                        copiedBlockId === "example"
                                            ? "已复制！"
                                            : "复制代码"
                                    }}
                                </button>

                                <!-- 在 Playground 打开 -->
                                <button
                                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/80 hover:bg-blue-600 text-white text-xs font-medium transition-all"
                                    @click="
                                        openInPlayground(lesson!.codeExample)
                                    "
                                >
                                    <svg
                                        class="w-3.5 h-3.5"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                                        />
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                        />
                                    </svg>
                                    运行此代码
                                </button>
                            </div>
                        </div>

                        <!-- 代码内容 -->
                        <pre
                            class="bg-[#1e1e1e] text-slate-200 text-sm font-mono leading-relaxed p-5 overflow-x-auto m-0"
                            >{{ lesson.codeExample }}</pre
                        >
                    </div>

                    <!-- ================================================
               上一节 / 下一节导航
          ================================================= -->
                    <div class="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <!-- 上一节 -->
                        <button
                            v-if="lesson.prevLesson"
                            class="group flex items-center gap-3 p-5 rounded-2xl bg-white border border-slate-100 text-left hover:border-blue-200 hover:shadow-md transition-all duration-200"
                            @click="goToLesson(lesson.prevLesson!.slug)"
                        >
                            <div
                                class="w-10 h-10 rounded-xl bg-slate-100 group-hover:bg-blue-50 flex items-center justify-center shrink-0 transition-colors"
                            >
                                <svg
                                    class="w-5 h-5 text-slate-400 group-hover:text-blue-500 transition-colors"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M15 19l-7-7 7-7"
                                    />
                                </svg>
                            </div>
                            <div class="min-w-0">
                                <p class="text-xs text-slate-400 mb-1">
                                    上一节
                                </p>
                                <p
                                    class="text-sm font-semibold text-slate-700 group-hover:text-blue-600 transition-colors truncate"
                                >
                                    {{ lesson.prevLesson.title }}
                                </p>
                            </div>
                        </button>
                        <div v-else />

                        <!-- 下一节 -->
                        <button
                            v-if="lesson.nextLesson"
                            class="group flex items-center justify-end gap-3 p-5 rounded-2xl bg-white border border-slate-100 text-right hover:border-blue-200 hover:shadow-md transition-all duration-200"
                            @click="goToLesson(lesson.nextLesson!.slug)"
                        >
                            <div class="min-w-0">
                                <p class="text-xs text-slate-400 mb-1">
                                    下一节
                                </p>
                                <p
                                    class="text-sm font-semibold text-slate-700 group-hover:text-blue-600 transition-colors truncate"
                                >
                                    {{ lesson.nextLesson.title }}
                                </p>
                            </div>
                            <div
                                class="w-10 h-10 rounded-xl bg-slate-100 group-hover:bg-blue-50 flex items-center justify-center shrink-0 transition-colors"
                            >
                                <svg
                                    class="w-5 h-5 text-slate-400 group-hover:text-blue-500 transition-colors"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                >
                                    <path
                                        stroke-linecap="round"
                                        stroke-linejoin="round"
                                        stroke-width="2"
                                        d="M9 5l7 7-7 7"
                                    />
                                </svg>
                            </div>
                        </button>
                    </div>
                </main>

                <!-- ================================================
             右侧边栏：目录 TOC（仅桌面端显示）
        ================================================= -->
                <aside class="hidden lg:block w-56 xl:w-64 shrink-0">
                    <div class="sticky top-24">
                        <!-- 目录 -->
                        <div
                            v-if="tocItems.length"
                            class="rounded-2xl bg-white border border-slate-100 p-5 mb-4"
                        >
                            <h3
                                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4"
                            >
                                本节目录
                            </h3>
                            <nav class="space-y-1">
                                <button
                                    v-for="item in tocItems"
                                    :key="item.id"
                                    class="block w-full text-left text-sm transition-colors duration-150 truncate"
                                    :class="[
                                        item.level === 3 ? 'pl-4' : 'pl-0',
                                        activeAnchor === item.id
                                            ? 'text-blue-600 font-medium'
                                            : 'text-slate-500 hover:text-slate-800',
                                    ]"
                                    @click="scrollToAnchor(item.id)"
                                >
                                    <span
                                        v-if="activeAnchor === item.id"
                                        class="inline-block w-1 h-1 rounded-full bg-blue-500 mr-1.5 align-middle"
                                    />
                                    {{ item.text }}
                                </button>
                            </nav>
                        </div>

                        <!-- 课程信息卡 -->
                        <div
                            class="rounded-2xl bg-white border border-slate-100 p-5"
                        >
                            <h3
                                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-4"
                            >
                                课程信息
                            </h3>
                            <ul class="space-y-3 text-sm">
                                <li class="flex items-center justify-between">
                                    <span class="text-slate-500">难度</span>
                                    <span
                                        class="px-2 py-0.5 rounded-full text-xs font-medium border"
                                        :class="
                                            difficultyColor[lesson.difficulty]
                                        "
                                    >
                                        {{ difficultyLabel[lesson.difficulty] }}
                                    </span>
                                </li>
                                <li class="flex items-center justify-between">
                                    <span class="text-slate-500">预计时长</span>
                                    <span class="text-slate-700 font-medium"
                                        >{{
                                            lesson.estimatedMinutes
                                        }}
                                        分钟</span
                                    >
                                </li>
                                <li class="flex items-center justify-between">
                                    <span class="text-slate-500">完成状态</span>
                                    <span
                                        class="flex items-center gap-1 text-xs font-medium"
                                        :class="
                                            isCompleted
                                                ? 'text-emerald-600'
                                                : 'text-slate-400'
                                        "
                                    >
                                        <svg
                                            class="w-3.5 h-3.5"
                                            fill="none"
                                            stroke="currentColor"
                                            viewBox="0 0 24 24"
                                        >
                                            <path
                                                stroke-linecap="round"
                                                stroke-linejoin="round"
                                                stroke-width="2"
                                                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                            />
                                        </svg>
                                        {{ isCompleted ? "已完成" : "未完成" }}
                                    </span>
                                </li>
                            </ul>

                            <!-- 操作按钮 -->
                            <div class="mt-5 space-y-2">
                                <button
                                    class="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-700 text-white text-sm font-medium transition-colors"
                                    @click="openInPlayground()"
                                >
                                    <svg
                                        class="w-3.5 h-3.5 text-emerald-400"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                                        />
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                                        />
                                    </svg>
                                    在 Playground 运行
                                </button>
                                <button
                                    class="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl border text-sm font-medium transition-all"
                                    :class="
                                        isCompleted
                                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-800'
                                    "
                                    @click="toggleCompleted"
                                >
                                    <svg
                                        class="w-3.5 h-3.5"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                    >
                                        <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            stroke-width="2"
                                            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                        />
                                    </svg>
                                    {{
                                        isCompleted
                                            ? "取消完成标记"
                                            : "标记为已完成"
                                    }}
                                </button>
                            </div>
                        </div>
                    </div>
                </aside>
            </div>
        </template>
    </div>
</template>

<style scoped>
/* =====================================================
   Markdown 正文排版样式
===================================================== */
.lesson-content :deep(h1),
.lesson-content :deep(h2),
.lesson-content :deep(h3),
.lesson-content :deep(h4) {
    font-weight: 700;
    color: #1e293b;
    line-height: 1.3;
    margin-top: 2rem;
    margin-bottom: 0.75rem;
    scroll-margin-top: 80px;
}

.lesson-content :deep(h1) {
    font-size: 1.75rem;
}
.lesson-content :deep(h2) {
    font-size: 1.375rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}
.lesson-content :deep(h3) {
    font-size: 1.125rem;
}
.lesson-content :deep(h4) {
    font-size: 1rem;
    color: #475569;
}

.lesson-content :deep(p) {
    color: #374151;
    line-height: 1.8;
    margin-bottom: 1rem;
}

.lesson-content :deep(ul),
.lesson-content :deep(ol) {
    padding-left: 1.5rem;
    margin-bottom: 1rem;
    color: #374151;
}

.lesson-content :deep(li) {
    margin-bottom: 0.4rem;
    line-height: 1.7;
}

.lesson-content :deep(ul) {
    list-style-type: disc;
}

.lesson-content :deep(ol) {
    list-style-type: decimal;
}

.lesson-content :deep(ul li::marker) {
    color: #3b82f6;
}

.lesson-content :deep(strong) {
    font-weight: 700;
    color: #1e293b;
}

.lesson-content :deep(em) {
    font-style: italic;
    color: #475569;
}

.lesson-content :deep(a) {
    color: #2563eb;
    text-decoration: underline;
    text-underline-offset: 2px;
}

.lesson-content :deep(a:hover) {
    color: #1d4ed8;
}

.lesson-content :deep(blockquote) {
    border-left: 4px solid #3b82f6;
    padding: 0.75rem 1rem;
    margin: 1.25rem 0;
    background: #eff6ff;
    border-radius: 0 0.5rem 0.5rem 0;
    color: #1e40af;
    font-style: italic;
}

.lesson-content :deep(hr) {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 2rem 0;
}

/* 行内代码 */
.lesson-content :deep(.inline-code) {
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 0.875em;
    background: #f1f5f9;
    color: #be185d;
    padding: 0.15em 0.45em;
    border-radius: 0.3rem;
    border: 1px solid #e2e8f0;
}

/* 代码块 */
.lesson-content :deep(.code-block) {
    position: relative;
    background: #1e1e1e;
    border-radius: 0.75rem;
    margin: 1.25rem 0;
    overflow: hidden;
    border: 1px solid #374151;
}

.lesson-content :deep(.code-block)::before {
    content: attr(data-lang);
    position: absolute;
    top: 0.6rem;
    right: 0.75rem;
    font-size: 0.7rem;
    font-family: monospace;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.lesson-content :deep(.code-block code) {
    display: block;
    padding: 1.25rem;
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 0.875rem;
    line-height: 1.65;
    color: #e2e8f0;
    overflow-x: auto;
    white-space: pre;
}
</style>
