<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { CancelledError } from "@/api";
import { fetchLessons, fetchCategoryStats } from "@/api/learning";
import { getRecommendations } from "@/api/recommendation";
import { getVisitorId } from "@/lib/visitorId";
import type {
    LessonSummary,
    LessonCategory,
    LessonDifficulty,
    RecommendationResponse,
} from "@/types/api";
import { useLocalStateStore } from "@/stores/localState";
import { currentTrackKeys, learningTrackMeta } from "@/lib/learningTracks";
import { getRecommendationContextLesson } from "@/lib/recommendation";

const router = useRouter();
const route = useRoute();
const localStateStore = useLocalStateStore();

// =====================================================
// 状态
// =====================================================

const lessons = ref<LessonSummary[]>([]);
const isLoading = ref(false);
const errorMsg = ref<string | null>(null);
const recommendation = ref<RecommendationResponse | null>(null);

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
        const currentLesson = getRecommendationContextLesson({
            lastVisitedSlug: localStateStore.progress.lastVisitedSlug,
        });
        const [lessonsData, statsData, recommendationData] = await Promise.all([
            fetchLessons({
                category: category === "all" ? undefined : category,
            }),
            fetchCategoryStats(),
            getRecommendations({
                visitorId: getVisitorId(),
                completedLessons: localStateStore.progress.completedLessons,
                currentLesson,
            }).catch(() => null),
        ]);

        if (requestId !== latestLessonRequestId) return;

        lessons.value = lessonsData;
        categoryCounts.value = {
            polars: statsData.find((s) => s.category === "polars")?.count ?? 0,
            duckdb: statsData.find((s) => s.category === "duckdb")?.count ?? 0,
            combined: statsData.find((s) => s.category === "combined")?.count ?? 0,
        };
        recommendation.value = recommendationData;
    } catch (err) {
        if (requestId !== latestLessonRequestId) return;
        if (err instanceof CancelledError) return;
        errorMsg.value = err instanceof Error ? err.message : "加载失败";
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

// ---- 当前选中路径的元信息 ----
const currentTrackInfo = computed(() => {
    if (activeCategory.value === "all") return null;
    return learningTrackMeta[activeCategory.value] ?? null;
});

// ---- 继续学习 ----
const lastVisitedSlug = computed(() => localStateStore.progress.lastVisitedSlug);
const lastVisitedTitle = computed(() => {
    if (!lastVisitedSlug.value) return null;
    const lesson = lessons.value.find((l) => l.slug === lastVisitedSlug.value);
    return lesson?.title ?? null;
});
const currentTrackLessons = computed(() => {
    if (activeCategory.value === "all") return [];
    return filteredLessons.value.filter((lesson) => lesson.category === activeCategory.value);
});
const currentTrackCompletedCount = computed(() => {
    return currentTrackLessons.value.filter((lesson) =>
        localStateStore.isLessonCompleted(lesson.slug),
    ).length;
});
const currentTrackProgressPercent = computed(() => {
    if (currentTrackLessons.value.length === 0) return 0;
    return Math.round((currentTrackCompletedCount.value / currentTrackLessons.value.length) * 100);
});
const currentTrackContinueLesson = computed(() => {
    if (activeCategory.value === "all") return null;

    const recommendationLesson =
        recommendation.value?.primary &&
        lessons.value.find((lesson) => lesson.slug === recommendation.value?.primary?.targetSlug);
    if (recommendationLesson?.category === activeCategory.value) {
        return recommendationLesson;
    }

    const firstUnfinished = currentTrackLessons.value.find(
        (lesson) => !localStateStore.isLessonCompleted(lesson.slug),
    );
    return firstUnfinished ?? currentTrackLessons.value[0] ?? null;
});

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

watch(
    () => localStateStore.progress.updatedAt,
    () => {
        void loadLessons(activeCategory.value);
    },
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

function getRecommendationStyle(rec: any) {
    const type = rec.type;
    const priority = rec.priority || 1;

    // 回补建议 - 橙色警示
    if (type === "review_lesson") {
        return {
            containerClass: "bg-gradient-to-r from-orange-50 to-amber-50 border-2 border-orange-200 hover:border-orange-300 hover:shadow-md",
            labelClass: "text-orange-700 font-semibold",
            buttonClass: "bg-orange-600 hover:bg-orange-700 shadow-sm",
            badgeClass: "bg-orange-100 text-orange-700",
            icon: "⚠️",
            label: "建议回补前置课程",
            priorityBadge: priority >= 5 ? "高优先级" : null,
        };
    }

    // 分支建议 - 紫色高亮
    if (type === "branch_path") {
        return {
            containerClass: "bg-gradient-to-r from-purple-50 to-indigo-50 border-2 border-purple-200 hover:border-purple-300 hover:shadow-md",
            labelClass: "text-purple-700 font-semibold",
            buttonClass: "bg-purple-600 hover:bg-purple-700 shadow-sm",
            badgeClass: "bg-purple-100 text-purple-700",
            icon: "🔀",
            label: "学习路径分支点",
            priorityBadge: priority >= 4 ? "推荐路径" : null,
        };
    }

    // 回流建议 - 绿色温馨
    if (type === "resume_session") {
        return {
            containerClass: "bg-gradient-to-r from-emerald-50 to-green-50 border-2 border-emerald-200 hover:border-emerald-300 hover:shadow-md",
            labelClass: "text-emerald-700 font-semibold",
            buttonClass: "bg-emerald-600 hover:bg-emerald-700 shadow-sm",
            badgeClass: "bg-emerald-100 text-emerald-700",
            icon: "👋",
            label: "欢迎回来继续学习",
            priorityBadge: null,
        };
    }

    // 顺学建议 - 蓝色默认
    return {
        containerClass: "bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-100 hover:border-blue-200 hover:shadow-md",
        labelClass: "text-blue-700 font-semibold",
        buttonClass: "bg-blue-600 hover:bg-blue-700 shadow-sm",
        badgeClass: "bg-blue-100 text-blue-700",
        icon: "💡",
        label: "下一步学习建议",
        priorityBadge: null,
    };
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
                                按迁移路径学习 Polars 与 DuckDB，从你熟悉的技术栈出发。
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
           路径说明（选中具体分类时显示）
      ================================================= -->
            <div
                v-if="currentTrackInfo"
                class="mb-6 p-5 rounded-2xl border transition-all"
                :class="
                    currentTrackInfo.color === 'blue'
                        ? 'bg-blue-50/50 border-blue-100'
                        : currentTrackInfo.color === 'yellow'
                        ? 'bg-yellow-50/50 border-yellow-100'
                        : 'bg-purple-50/50 border-purple-100'
                "
            >
                    <div class="flex flex-wrap items-start justify-between gap-4">
                        <div class="flex-1 min-w-0">
                        <h2 class="text-lg font-bold text-slate-800 mb-1">
                            {{ currentTrackInfo.label }}
                        </h2>
                        <p class="text-sm text-slate-500 mb-2">
                            {{ currentTrackInfo.description }}
                        </p>
                        <div class="flex flex-wrap gap-x-6 gap-y-1 text-xs">
                            <span class="text-slate-500">
                                <strong class="text-slate-700">适合：</strong>{{ currentTrackInfo.targetAudience }}
                            </span>
                            <span class="text-slate-500">
                                <strong class="text-slate-700">你将获得：</strong>{{ currentTrackInfo.learningOutcome }}
                            </span>
                        </div>
                        <div class="mt-4 max-w-xl">
                            <div class="mb-2 flex items-center justify-between text-xs text-slate-500">
                                <span>当前路径进度</span>
                                <span>{{ currentTrackCompletedCount }} / {{ currentTrackLessons.length }} 课</span>
                            </div>
                            <div class="h-2 overflow-hidden rounded-full bg-white/80">
                                <div
                                    class="h-full rounded-full transition-all duration-300"
                                    :class="
                                        currentTrackInfo.color === 'blue'
                                            ? 'bg-blue-500'
                                            : currentTrackInfo.color === 'yellow'
                                            ? 'bg-amber-500'
                                            : 'bg-purple-500'
                                    "
                                    :style="{ width: `${currentTrackProgressPercent}%` }"
                                />
                            </div>
                        </div>
                    </div>
                    <div class="shrink-0 space-y-2 text-right">
                        <div class="text-xs text-blue-600/70">
                            💡 {{ currentTrackInfo.recommendedStart }}
                        </div>
                        <button
                            v-if="currentTrackContinueLesson"
                            class="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-slate-700"
                            @click="goToLesson(currentTrackContinueLesson.slug)"
                        >
                            {{ localStateStore.isLessonCompleted(currentTrackContinueLesson.slug) ? "回顾这条路径" : "继续这条路径" }}
                            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>

            <!-- ================================================
           下一步学习建议 (Phase 3)
      ================================================= -->
            <div
                v-if="recommendation?.primary"
                class="mb-6 rounded-xl border transition-all"
                :class="getRecommendationStyle(recommendation.primary).containerClass"
            >
                <div class="flex items-start gap-4 p-5">
                    <div
                        class="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                        :class="getRecommendationStyle(recommendation.primary).badgeClass"
                    >
                        <span class="text-2xl">{{ getRecommendationStyle(recommendation.primary).icon }}</span>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1.5">
                            <p class="text-xs font-semibold" :class="getRecommendationStyle(recommendation.primary).labelClass">
                                {{ getRecommendationStyle(recommendation.primary).label }}
                            </p>
                            <span
                                v-if="getRecommendationStyle(recommendation.primary).priorityBadge"
                                class="px-2 py-0.5 rounded-full text-xs font-medium"
                                :class="getRecommendationStyle(recommendation.primary).badgeClass"
                            >
                                {{ getRecommendationStyle(recommendation.primary).priorityBadge }}
                            </span>
                        </div>
                        <h3 class="text-base font-bold text-slate-800 mb-2">{{ recommendation.primary.targetTitle }}</h3>
                        <p class="text-sm text-slate-600 leading-relaxed mb-4">{{ recommendation.primary.reason }}</p>
                        <div class="flex items-center gap-3">
                            <button
                                class="px-5 py-2 text-white text-sm font-medium rounded-lg transition-all"
                                :class="getRecommendationStyle(recommendation.primary).buttonClass"
                                @click="goToLesson(recommendation.primary.targetSlug)"
                            >
                                {{ recommendation.primary.actionLabel }}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- 备选建议（如果有） -->
                <div
                    v-if="recommendation.alternatives && recommendation.alternatives.length > 0"
                    class="border-t border-slate-200/50 px-5 py-3 bg-white/30"
                >
                    <p class="text-xs text-slate-500 font-medium mb-2">其他选择：</p>
                    <div class="flex flex-wrap gap-2">
                        <button
                            v-for="alt in recommendation.alternatives"
                            :key="alt.targetSlug"
                            class="px-3 py-1.5 text-xs font-medium rounded-lg bg-white border border-slate-200 text-slate-700 hover:border-slate-300 hover:shadow-sm transition-all"
                            @click="goToLesson(alt.targetSlug)"
                        >
                            {{ alt.targetTitle }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- 继续学习（兜底，无建议时显示）-->
            <div
                v-else-if="activeCategory === 'all' && lastVisitedSlug"
                class="mb-6 flex items-center gap-3 p-4 rounded-xl bg-white border border-slate-200 hover:border-blue-200 hover:shadow-sm cursor-pointer transition-all"
                @click="router.push(`/learn/${lastVisitedSlug}`)"
            >
                <div class="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                    <svg class="w-5 h-5 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                    </svg>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-slate-700">继续上次学习</p>
                    <p class="text-xs text-slate-400 truncate">{{ lastVisitedTitle ?? lastVisitedSlug }}</p>
                </div>
                <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
            </div>
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
                        <span
                            v-if="group.items.filter(l => localStateStore.isLessonCompleted(l.slug)).length > 0"
                            class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-600 text-xs font-medium"
                        >
                            已完成 {{ group.items.filter(l => localStateStore.isLessonCompleted(l.slug)).length }}/{{ group.items.length }}
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
