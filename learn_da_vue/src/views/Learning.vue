<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { CancelledError } from "@/api";
import { fetchAllLessons, fetchCategoryStats } from "@/api/learning";
import type {
    LessonSummary,
    LessonCategory,
    LessonDifficulty,
} from "@/types/api";
import { useLocalStateStore } from "@/stores/localState";
import { currentTrackKeys, learningTrackMeta } from "@/lib/learningTracks";

const router = useRouter();
const route = useRoute();
const localStateStore = useLocalStateStore();

// =====================================================
// 状态
// =====================================================

const lessons = ref<LessonSummary[]>([]);
const isLoading = ref(false);
const errorMsg = ref<string | null>(null);

const categoryCounts = ref<Record<string, number>>({
    polars: 0,
    duckdb: 0,
    combined: 0,
});

// ---- 筛选状态 ----
const activeCategory = ref<LessonCategory | "all">("all");
const activeDifficulty = ref<LessonDifficulty | "all">("all");
const searchKeyword = ref("");
let latestLessonRequestId = 0;

// =====================================================
// 分类 / 难度配置
// =====================================================

const categories: {
    key: LessonCategory | "all";
    label: string;
}[] = [
    { key: "all", label: "全部专题" },
    ...currentTrackKeys.map((key) => ({
        key,
        label: learningTrackMeta[key].label,
    })),
];

const difficulties: {
    key: LessonDifficulty | "all";
    label: string;
    color: string;
}[] = [
    { key: "all", label: "全部难度", color: "slate" },
    { key: "beginner", label: "入门", color: "emerald" },
    { key: "intermediate", label: "进阶", color: "blue" },
    { key: "advanced", label: "高级", color: "purple" },
];

const difficultyLabel: Record<LessonDifficulty, string> = {
    beginner: "入门",
    intermediate: "进阶",
    advanced: "高级",
};

const difficultyColor: Record<LessonDifficulty, string> = {
    beginner: "bg-emerald-100 text-emerald-700",
    intermediate: "bg-blue-100 text-blue-700",
    advanced: "bg-purple-100 text-purple-700",
};

const categoryColor: Record<LessonCategory, string> = {
    polars: "bg-blue-100 text-blue-700",
    duckdb: "bg-yellow-100 text-yellow-700",
    combined: "bg-purple-100 text-purple-700",
};

// =====================================================
// 数据加载
// =====================================================

function normalizeCategoryQuery(
    value: unknown,
): LessonCategory | "all" {
    const category = Array.isArray(value) ? value[0] : value;
    return typeof category === "string" &&
        currentTrackKeys.includes(category as LessonCategory)
        ? (category as LessonCategory)
        : "all";
}

async function loadLessons(category: LessonCategory | "all" = activeCategory.value) {
    const requestId = ++latestLessonRequestId;
    isLoading.value = true;
    errorMsg.value = null;

    try {
        const requestCategory = category === "all" ? undefined : category;

        const [allLessons, stats] = await Promise.all([
            fetchAllLessons(requestCategory),
            fetchCategoryStats(),
        ]);

        if (requestId !== latestLessonRequestId) return;

        lessons.value = allLessons;

        // 更新分类计数
        stats.forEach((s) => {
            categoryCounts.value[s.category] = s.count;
        });
    } catch (err) {
        if (requestId !== latestLessonRequestId) return;
        if (err instanceof CancelledError) return;

        errorMsg.value =
            err instanceof Error ? err.message : "加载课程列表失败，请稍后重试";
        // 开发期间使用 mock 数据
        lessons.value = generateMockLessons();
    } finally {
        if (requestId === latestLessonRequestId) {
            isLoading.value = false;
        }
    }
}

// =====================================================
// 过滤 + 搜索（纯前端处理）
// =====================================================

const filteredLessons = computed(() => {
    let result = lessons.value;

    // 按分类过滤
    if (activeCategory.value !== "all") {
        result = result.filter((l) => l.category === activeCategory.value);
    }

    // 按难度过滤
    if (activeDifficulty.value !== "all") {
        result = result.filter((l) => l.difficulty === activeDifficulty.value);
    }

    // 按关键词搜索（标题 + 描述 + tags）
    const kw = searchKeyword.value.trim().toLowerCase();
    if (kw) {
        result = result.filter(
            (l) =>
                l.title.toLowerCase().includes(kw) ||
                l.description.toLowerCase().includes(kw) ||
                l.tags.some((t) => t.toLowerCase().includes(kw)),
        );
    }

    // 按 order 排序
    return [...result].sort((a, b) => a.order - b.order);
});

const totalCount = computed(() => filteredLessons.value.length);
const completedCount = computed(
    () =>
        filteredLessons.value.filter((l) => localStateStore.isLessonCompleted(l.slug))
            .length,
);

// =====================================================
// 分组展示（按 category 分组，仅在「全部」模式下）
// =====================================================

const groupedLessons = computed<
    {
        category: LessonCategory;
        label: string;
        items: LessonSummary[];
    }[]
>(() => {
    if (activeCategory.value !== "all") return [];

    const groups: Record<string, LessonSummary[]> = {};
    filteredLessons.value.forEach((l) => {
        if (!groups[l.category]) groups[l.category] = [];
        groups[l.category]!.push(l);
    });

    return currentTrackKeys
        .filter((c) => (groups[c]?.length ?? 0) > 0)
        .map((c) => ({
            category: c,
            label: categories.find((cat) => cat.key === c)?.label ?? c,
            items: groups[c] ?? [],
        }));
});

// =====================================================
// URL query 是专题入口的唯一同步来源，避免点击与路由更新互相抢状态。
// =====================================================

watch(
    () => route.query.category,
    (categoryQuery) => {
        const nextCategory = normalizeCategoryQuery(categoryQuery);
        activeCategory.value = nextCategory;
        void loadLessons(nextCategory);
    },
    { immediate: true },
);

// =====================================================
// 操作
// =====================================================

function goToLesson(slug: string) {
    router.push(`/learn/${slug}`);
}

function selectCategory(category: LessonCategory | "all") {
    activeCategory.value = category;

    const query = { ...route.query };
    if (category === "all") {
        delete query.category;
    } else {
        query.category = category;
    }

    void router.replace({ query });
}

function clearFilters() {
    selectCategory("all");
    activeDifficulty.value = "all";
    searchKeyword.value = "";
}

// =====================================================
// Mock 数据（后端未就绪时使用）
// =====================================================

function generateMockLessons(): LessonSummary[] {
    return [
        {
            id: 1,
            slug: "polars-quickstart",
            title: "Polars 快速入门",
            description:
                "5分钟掌握 Polars 基本用法，创建 DataFrame、查询数据、基础变换。",
            category: "polars",
            difficulty: "beginner",
            estimatedMinutes: 15,
            order: 1,
            tags: ["DataFrame", "入门", "基础操作"],
        },
        {
            id: 2,
            slug: "polars-expressions",
            title: "Polars 表达式系统",
            description:
                "深入理解 Polars 表达式（Expressions）的核心概念与链式调用模式。",
            category: "polars",
            difficulty: "intermediate",
            estimatedMinutes: 30,
            order: 2,
            tags: ["Expressions", "链式调用", "列操作"],
        },
        {
            id: 3,
            slug: "polars-lazy-api",
            title: "Lazy API 与查询优化",
            description:
                "掌握 LazyFrame 惰性求值机制，利用查询计划优化大数据处理性能。",
            category: "polars",
            difficulty: "intermediate",
            estimatedMinutes: 35,
            order: 3,
            tags: ["LazyFrame", "惰性求值", "查询优化"],
        },
        {
            id: 4,
            slug: "polars-groupby-agg",
            title: "GroupBy 聚合操作",
            description:
                "掌握 Polars 的 group_by、agg 操作，实现复杂的分组统计需求。",
            category: "polars",
            difficulty: "intermediate",
            estimatedMinutes: 25,
            order: 4,
            tags: ["group_by", "agg", "聚合统计"],
        },
        {
            id: 5,
            slug: "polars-join",
            title: "多表关联（Join）",
            description:
                "学习 inner join、left join、cross join 等各类连接操作及性能对比。",
            category: "polars",
            difficulty: "intermediate",
            estimatedMinutes: 30,
            order: 5,
            tags: ["join", "多表", "关联"],
        },
        {
            id: 6,
            slug: "duckdb-quickstart",
            title: "DuckDB 快速入门",
            description:
                "零配置嵌入式 SQL 数据库，5分钟完成安装、连接与首次查询。",
            category: "duckdb",
            difficulty: "beginner",
            estimatedMinutes: 15,
            order: 1,
            tags: ["SQL", "入门", "零配置"],
        },
        {
            id: 7,
            slug: "duckdb-read-files",
            title: "读取 CSV / Parquet 文件",
            description:
                "用 SQL 直接查询本地文件，支持通配符批量读取，无需手动建表。",
            category: "duckdb",
            difficulty: "beginner",
            estimatedMinutes: 20,
            order: 2,
            tags: ["CSV", "Parquet", "文件读取"],
        },
        {
            id: 8,
            slug: "duckdb-window-functions",
            title: "窗口函数实战",
            description:
                "掌握 OVER、PARTITION BY、ROW_NUMBER、LAG/LEAD 等窗口函数。",
            category: "duckdb",
            difficulty: "advanced",
            estimatedMinutes: 40,
            order: 3,
            tags: ["窗口函数", "OVER", "PARTITION BY"],
        },
        {
            id: 9,
            slug: "polars-duckdb-interop",
            title: "Polars × DuckDB 互操作",
            description:
                "在 Polars 与 DuckDB 之间零拷贝传递 DataFrame，构建高效分析管道。",
            category: "combined",
            difficulty: "intermediate",
            estimatedMinutes: 35,
            order: 1,
            tags: ["互操作", "Arrow", "零拷贝"],
        },
        {
            id: 10,
            slug: "etl-pipeline",
            title: "构建完整 ETL 管道",
            description:
                "综合案例：用 Polars + DuckDB 构建从原始数据到分析报告的完整流程。",
            category: "combined",
            difficulty: "advanced",
            estimatedMinutes: 60,
            order: 2,
            tags: ["ETL", "数据管道", "综合案例"],
        },
    ];
}
</script>

<template>
    <div class="min-h-screen bg-slate-50">
        <!-- ================================================
         页头
    ================================================= -->
        <div class="bg-white border-b border-slate-200 sticky top-0 z-10">
            <div class="max-w-6xl mx-auto px-6">
                <!-- 页面标题行 -->
                <div class="flex items-center justify-between h-16">
                    <div class="flex items-center gap-3">
                        <div>
                            <div class="flex items-center gap-3">
                                <h1 class="text-xl font-bold text-slate-800">
                                    学习中心
                                </h1>
                                <span
                                    v-if="!isLoading"
                                    class="px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold"
                                >
                                    {{ totalCount }} 课
                                </span>
                            </div>
                            <p class="hidden md:block text-xs text-slate-500 mt-0.5">
                                按专题学习数据分析工具与方法，当前支持 Polars / DuckDB。
                            </p>
                        </div>
                    </div>

                    <!-- 搜索框 -->
                    <div class="relative w-64">
                        <svg
                            class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                stroke-linecap="round"
                                stroke-linejoin="round"
                                stroke-width="2"
                                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                            />
                        </svg>
                        <input
                            v-model="searchKeyword"
                            type="text"
                            placeholder="搜索课程或专题..."
                            class="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-slate-200 bg-slate-50 text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 transition-all"
                        />
                        <button
                            v-if="searchKeyword"
                            class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                            @click="searchKeyword = ''"
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
                                    d="M6 18L18 6M6 6l12 12"
                                />
                            </svg>
                        </button>
                    </div>
                </div>

                <!-- 分类 Tab -->
                <div
                    class="flex items-center gap-1 pb-0 overflow-x-auto scrollbar-hide"
                >
                    <button
                        v-for="cat in categories"
                        :key="cat.key"
                        class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors duration-150"
                        :class="
                            activeCategory === cat.key
                                ? 'border-blue-600 text-blue-600'
                                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        "
                        @click="selectCategory(cat.key)"
                    >
                        <span>{{ cat.label }}</span>
                        <span
                            v-if="
                                cat.key !== 'all' &&
                                categoryCounts[cat.key as LessonCategory]
                            "
                            class="px-1.5 py-0.5 rounded-full text-xs"
                            :class="
                                activeCategory === cat.key
                                    ? 'bg-blue-100 text-blue-600'
                                    : 'bg-slate-100 text-slate-500'
                            "
                        >
                            {{ categoryCounts[cat.key as LessonCategory] }}
                        </span>
                    </button>
                </div>
            </div>
        </div>

        <div class="max-w-6xl mx-auto px-6 py-8">
            <!-- ================================================
           筛选栏
      ================================================= -->
            <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
                <!-- 难度筛选 -->
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm text-slate-500">难度：</span>
                    <button
                        v-for="diff in difficulties"
                        :key="diff.key"
                        class="px-3 py-1 rounded-full text-sm font-medium border transition-all duration-150"
                        :class="
                            activeDifficulty === diff.key
                                ? 'bg-slate-800 border-slate-800 text-white'
                                : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300 hover:text-slate-800'
                        "
                        @click="
                            activeDifficulty =
                                diff.key as typeof activeDifficulty
                        "
                    >
                        {{ diff.label }}
                    </button>
                </div>

                <!-- 进度统计 + 重置 -->
                <div class="flex items-center gap-4 text-sm text-slate-500">
                    <div v-if="!isLoading" class="flex items-center gap-1.5">
                        <svg
                            class="w-4 h-4 text-emerald-500"
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
                        <span>
                            已完成
                            <strong class="text-slate-700">{{
                                completedCount
                            }}</strong>
                            /
                            {{ totalCount }}
                        </span>
                    </div>

                    <button
                        v-if="
                            activeCategory !== 'all' ||
                            activeDifficulty !== 'all' ||
                            searchKeyword
                        "
                        class="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
                        @click="clearFilters"
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
                                d="M6 18L18 6M6 6l12 12"
                            />
                        </svg>
                        清除筛选
                    </button>
                </div>
            </div>

            <!-- ================================================
           加载状态
      ================================================= -->
            <div
                v-if="isLoading"
                class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            >
                <div
                    v-for="i in 6"
                    :key="i"
                    class="h-48 rounded-2xl bg-white border border-slate-100 animate-pulse"
                />
            </div>

            <!-- ================================================
           错误提示
      ================================================= -->
            <div
                v-else-if="errorMsg && lessons.length === 0"
                class="flex flex-col items-center justify-center py-20 text-center"
            >
                <div class="text-4xl mb-4">⚠️</div>
                <h3 class="text-lg font-semibold text-slate-700 mb-2">
                    加载失败
                </h3>
                <p class="text-sm text-slate-500 mb-6 max-w-sm">
                    {{ errorMsg }}
                </p>
                <button
                    class="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                    @click="() => loadLessons()"
                >
                    重新加载
                </button>
            </div>

            <!-- ================================================
           无结果
      ================================================= -->
            <div
                v-else-if="!isLoading && filteredLessons.length === 0"
                class="flex flex-col items-center justify-center py-20 text-center"
            >
                <div class="text-5xl mb-4">🔍</div>
                <h3 class="text-lg font-semibold text-slate-700 mb-2">
                    没有找到相关课程
                </h3>
                <p class="text-sm text-slate-500 mb-6">
                    尝试修改搜索词或切换其他分类
                </p>
                <button
                    class="px-5 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 transition-colors"
                    @click="clearFilters"
                >
                    清除所有筛选
                </button>
            </div>

            <!-- ================================================
           分组模式（全部分类时）
      ================================================= -->
            <template
                v-else-if="
                    activeCategory === 'all' &&
                    !searchKeyword &&
                    activeDifficulty === 'all'
                "
            >
                <div
                    v-for="group in groupedLessons"
                    :key="group.category"
                    class="mb-12"
                >
                    <!-- 分组标题 -->
                    <div class="flex items-center gap-2 mb-5">
                        <h2 class="text-xl font-bold text-slate-800">
                            {{ group.label }}
                        </h2>
                        <span
                            class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 text-xs font-medium ml-1"
                        >
                            {{ group.items.length }} 课
                        </span>
                    </div>

                    <!-- 课程卡片网格 -->
                    <div
                        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
                    >
                        <LessonCard
                            v-for="lesson in group.items"
                            :key="lesson.slug"
                            :lesson="lesson"
                            :is-completed="
                                localStateStore.isLessonCompleted(lesson.slug)
                            "
                            @click="goToLesson(lesson.slug)"
                        />
                    </div>
                </div>
            </template>

            <!-- ================================================
           平铺模式（筛选 / 搜索时）
      ================================================= -->
            <div
                v-else
                class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            >
                <LessonCard
                    v-for="lesson in filteredLessons"
                    :key="lesson.slug"
                    :lesson="lesson"
                    :is-completed="localStateStore.isLessonCompleted(lesson.slug)"
                    @click="goToLesson(lesson.slug)"
                />
            </div>
        </div>
    </div>
</template>

<!-- =====================================================
     子组件：LessonCard（使用渲染函数，无需运行时编译）
===================================================== -->
<script lang="ts">
import { defineComponent, h, type PropType } from "vue";

const difficultyLabel: Record<LessonDifficulty, string> = {
    beginner: "入门",
    intermediate: "进阶",
    advanced: "高级",
};

const difficultyColor: Record<LessonDifficulty, string> = {
    beginner: "bg-emerald-100 text-emerald-700",
    intermediate: "bg-blue-100 text-blue-700",
    advanced: "bg-purple-100 text-purple-700",
};

export const LessonCard = defineComponent({
    name: "LessonCard",
    props: {
        lesson: {
            type: Object as PropType<LessonSummary>,
            required: true,
        },
        isCompleted: {
            type: Boolean,
            default: false,
        },
    },
    emits: ["click"],
    setup(props, { emit }) {
        return () =>
            h(
                "div",
                {
                    class: "group relative flex flex-col rounded-2xl bg-white border border-slate-100 p-5 cursor-pointer transition-all duration-200 hover:-translate-y-1 hover:shadow-lg hover:border-blue-100",
                    onClick: () => emit("click"),
                },
                [
                    props.isCompleted
                        ? h(
                              "div",
                              {
                                  class: "absolute top-4 right-4 flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500",
                                  title: "已完成",
                              },
                              [
                                  h("svg", { class: "w-3.5 h-3.5 text-white", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
                                      h("path", { "stroke-linecap": "round", "stroke-linejoin": "round", "stroke-width": "3", d: "M5 13l4 4L19 7" }),
                                  ]),
                              ],
                          )
                        : null,
                    h("h3", { class: "text-base font-semibold text-slate-800 mb-2 group-hover:text-blue-600 transition-colors pr-8 leading-snug" }, props.lesson.title),
                    h("p", { class: "text-sm text-slate-500 leading-relaxed mb-4 flex-1 line-clamp-2" }, props.lesson.description),
                    h(
                        "div",
                        { class: "flex flex-wrap gap-1.5 mb-4" },
                        props.lesson.tags.slice(0, 3).map((tag) => h("span", { class: "px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 text-xs" }, tag)),
                    ),
                    h(
                        "div",
                        { class: "flex items-center justify-between pt-3 border-t border-slate-100 text-xs text-slate-400" },
                        [
                            h(
                                "div",
                                { class: "flex items-center gap-2" },
                                [
                                    h(
                                        "span",
                                        { class: `px-2 py-0.5 rounded-full font-medium text-xs ${difficultyColor[props.lesson.difficulty]}` },
                                        difficultyLabel[props.lesson.difficulty],
                                    ),
                                ],
                            ),
                            h(
                                "div",
                                { class: "flex items-center gap-1" },
                                [
                                    h("svg", { class: "w-3.5 h-3.5", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
                                        h("path", { "stroke-linecap": "round", "stroke-linejoin": "round", "stroke-width": "2", d: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" }),
                                    ]),
                                    `${props.lesson.estimatedMinutes} 分钟`,
                                ],
                            ),
                        ],
                    ),
                ],
            );
    },
});

export default {};
</script>
