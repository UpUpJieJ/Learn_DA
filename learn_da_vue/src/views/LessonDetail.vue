<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { fetchLessonBySlug } from "@/api/learning";
import { trackEvent, saveCodeSnapshot } from "@/api/analytics";
import { getRecommendations } from "@/api/recommendation";
import { getVisitorId } from "@/lib/visitorId";
import type { LessonDetail, LessonDifficulty, RecommendationResponse } from "@/types/api";
import { useLocalStateStore } from "@/stores/localState";
import { usePlaygroundStore } from "@/stores/playground";
import { renderMarkdown } from "@/lib/markdown";

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
const localStateStore = useLocalStateStore();
const playgroundStore = usePlaygroundStore();

// =====================================================
// 状态
// =====================================================

const lesson = ref<LessonDetail | null>(null);
const isLoading = ref(false);
const errorMsg = ref<string | null>(null);
const recommendation = ref<RecommendationResponse | null>(null);
const isSavingSnapshot = ref(false);
const snapshotSaved = ref(false);

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
    python: "🐍 Python",
};

function formatCategoryLabel(category: string): string {
    return categoryLabel[category] ?? category;
}

// =====================================================
// 数据加载
// =====================================================

async function loadLesson(slug: string) {
    isLoading.value = true;
    errorMsg.value = null;
    lesson.value = null;
    tocItems.value = [];
    activeAnchor.value = "";
    recommendation.value = null;

    try {
        const [lessonData, recommendationData] = await Promise.all([
            fetchLessonBySlug(slug),
            getRecommendations({
                visitorId: getVisitorId(),
                completedLessons: localStateStore.progress.completedLessons,
                currentLesson: slug,
            }).catch(() => null),
        ]);

        lesson.value = lessonData;
        recommendation.value = recommendationData;
        localStateStore.setLastVisitedLesson(slug);

        // 上报课程开始学习事件
        trackEvent({
            visitorId: getVisitorId(),
            eventType: "lesson_start",
            lessonSlug: slug,
        }).catch(() => {});

        // 等 DOM 渲染后提取目录
        await nextTick();
        extractToc();
        setupScrollSpy();
    } catch (err) {
        errorMsg.value =
            err instanceof Error ? err.message : "课程内容加载失败，请稍后重试";
    } finally {
        isLoading.value = false;
    }
}

async function refreshRecommendation(slug: string) {
    recommendation.value = await getRecommendations({
        visitorId: getVisitorId(),
        completedLessons: localStateStore.progress.completedLessons,
        currentLesson: slug,
    }).catch(() => null);
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
    lesson.value ? localStateStore.isLessonCompleted(lesson.value.slug) : false,
);

// ---- 完成动画控制 ----
const showCompletionAnim = ref(false);

function toggleCompleted() {
    if (!lesson.value) return;
    const lessonSlug = lesson.value.slug;
    const wasCompleted = localStateStore.isLessonCompleted(lessonSlug);
    localStateStore.toggleLessonCompleted(lessonSlug);
    void refreshRecommendation(lessonSlug);

    // 标记为完成时播放庆祝动画 + 上报事件
    if (!wasCompleted) {
        showCompletionAnim.value = true;
        setTimeout(() => (showCompletionAnim.value = false), 2000);
        trackEvent({
            visitorId: getVisitorId(),
            eventType: "lesson_complete",
            lessonSlug,
        }).catch(() => {});
    }
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

async function saveLessonSnapshot() {
    if (!lesson.value?.codeExample?.trim() || isSavingSnapshot.value) return;

    isSavingSnapshot.value = true;
    snapshotSaved.value = false;

    try {
        await saveCodeSnapshot({
            visitorId: getVisitorId(),
            lessonSlug: lesson.value.slug,
            code: lesson.value.codeExample,
            language: "python",
            description: `课程示例起点：${lesson.value.title}`,
        });
        trackEvent({
            visitorId: getVisitorId(),
            eventType: "code_save",
            lessonSlug: lesson.value.slug,
        }).catch(() => {});
        snapshotSaved.value = true;
        setTimeout(() => {
            snapshotSaved.value = false;
        }, 2200);
    } catch {
        console.warn("保存代码快照失败");
    } finally {
        isSavingSnapshot.value = false;
    }
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

const recommendationCta = computed(() => {
    if (recommendation.value?.primary) {
        return {
            title: recommendation.value.primary.targetTitle,
            actionLabel: recommendation.value.primary.actionLabel,
            reason: recommendation.value.primary.reason,
            slug: recommendation.value.primary.targetSlug,
        };
    }
    if (lesson.value?.nextLesson) {
        return {
            title: lesson.value.nextLesson.title,
            actionLabel: "继续学习",
            reason: "按当前课程顺序继续推进，保持稳定学习节奏。",
            slug: lesson.value.nextLesson.slug,
        };
    }
    return null;
});

function getRecommendationStyle(rec: any) {
    const type = rec.type;

    // 回补建议 - 橙色警示
    if (type === "review_lesson") {
        return {
            containerClass: "bg-gradient-to-br from-orange-50 via-amber-50 to-orange-50 border-2 border-orange-200",
            labelClass: "text-orange-800 font-semibold",
            buttonClass: "bg-orange-600 hover:bg-orange-700 shadow-md hover:shadow-lg",
            badgeClass: "bg-orange-100 border border-orange-200",
            iconBgClass: "bg-orange-100 border-2 border-orange-200",
            icon: "⚠️",
            label: "建议回补前置课程",
        };
    }

    // 分支建议 - 紫色高亮
    if (type === "branch_path") {
        return {
            containerClass: "bg-gradient-to-br from-purple-50 via-indigo-50 to-purple-50 border-2 border-purple-200",
            labelClass: "text-purple-800 font-semibold",
            buttonClass: "bg-purple-600 hover:bg-purple-700 shadow-md hover:shadow-lg",
            badgeClass: "bg-purple-100 border border-purple-200",
            iconBgClass: "bg-purple-100 border-2 border-purple-200",
            icon: "🔀",
            label: "学习路径分支点",
        };
    }

    // 回流建议 - 绿色温馨
    if (type === "resume_session") {
        return {
            containerClass: "bg-gradient-to-br from-emerald-50 via-green-50 to-emerald-50 border-2 border-emerald-200",
            labelClass: "text-emerald-800 font-semibold",
            buttonClass: "bg-emerald-600 hover:bg-emerald-700 shadow-md hover:shadow-lg",
            badgeClass: "bg-emerald-100 border border-emerald-200",
            iconBgClass: "bg-emerald-100 border-2 border-emerald-200",
            icon: "👋",
            label: "欢迎回来继续学习",
        };
    }

    // 顺学建议 - 蓝色默认
    return {
        containerClass: "bg-gradient-to-br from-blue-50 via-indigo-50 to-blue-50 border-2 border-blue-200",
        labelClass: "text-blue-800 font-semibold",
        buttonClass: "bg-blue-600 hover:bg-blue-700 shadow-md hover:shadow-lg",
        badgeClass: "bg-blue-100 border border-blue-200",
        iconBgClass: "bg-blue-100 border-2 border-blue-200",
        icon: "💡",
        label: "学完本课后的建议",
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
            <!-- 完成庆祝动画 -->
            <Transition name="completion-fade">
                <div
                    v-if="showCompletionAnim"
                    class="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
                >
                    <div class="flex flex-col items-center gap-4 animate-completion-bounce">
                        <div class="text-7xl">🎉</div>
                        <div class="text-2xl font-bold text-emerald-600 bg-white/90 px-6 py-3 rounded-2xl shadow-xl border border-emerald-100">
                            课程完成！
                        </div>
                    </div>
                </div>
            </Transition>

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
                                    formatCategoryLabel(lesson.category)
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
               Phase 2: 练习结构卡片（仅样板课展示）
          ================================================= -->
                    <div v-if="lesson.practiceObjective || (lesson.completionCriteria && lesson.completionCriteria.length)" class="mb-8 space-y-4">
                        <!-- 训练目标 -->
                        <div v-if="lesson.practiceObjective" class="rounded-xl border border-blue-200 bg-blue-50/60 p-5">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="text-lg">🎯</span>
                                <h3 class="text-sm font-bold text-blue-800">本课训练目标</h3>
                            </div>
                            <p class="text-sm text-blue-900/80 leading-relaxed">{{ lesson.practiceObjective }}</p>
                        </div>

                        <!-- 完成标准 -->
                        <div v-if="lesson.completionCriteria && lesson.completionCriteria.length" class="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5">
                            <div class="flex items-center gap-2 mb-3">
                                <span class="text-lg">✅</span>
                                <h3 class="text-sm font-bold text-emerald-800">完成标准</h3>
                            </div>
                            <ul class="space-y-2">
                                <li
                                    v-for="(criteria, idx) in lesson.completionCriteria"
                                    :key="idx"
                                    class="flex items-start gap-2.5 text-sm text-emerald-900/80"
                                >
                                    <span class="w-5 h-5 rounded-full border-2 border-emerald-300 flex items-center justify-center shrink-0 mt-0.5 text-xs text-emerald-500">
                                        {{ idx + 1 }}
                                    </span>
                                    <span>{{ criteria }}</span>
                                </li>
                            </ul>
                        </div>

                        <div class="flex flex-wrap gap-3">
                            <button
                                class="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-700"
                                @click="openInPlayground()"
                            >
                                <svg class="h-4 w-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                立刻开始练习
                            </button>
                            <button
                                class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:text-slate-900"
                                :disabled="isSavingSnapshot"
                                @click="saveLessonSnapshot"
                            >
                                <svg class="h-4 w-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5h14v14H5z" />
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5v4h6V5" />
                                </svg>
                                {{ snapshotSaved ? "已保存练习起点" : isSavingSnapshot ? "保存中..." : "保存当前示例" }}
                            </button>
                        </div>
                    </div>

                    <!-- ================================================
               Markdown 正文内容
          ================================================= -->
                    <div
                        id="lesson-content"
                        class="lesson-content prose prose-slate max-w-none"
                        v-html="renderMarkdown(lesson.content)"
                    />

                    <!-- ================================================
               Phase 3: 下一步学习建议
          ================================================= -->
                    <div v-if="recommendation?.primary" class="mt-12 space-y-4">
                        <!-- 主要建议 -->
                        <div
                            class="p-6 rounded-xl border shadow-sm hover:shadow-md transition-shadow"
                            :class="getRecommendationStyle(recommendation.primary).containerClass"
                        >
                            <div class="flex items-start gap-4">
                                <div
                                    class="w-14 h-14 rounded-xl flex items-center justify-center shrink-0"
                                    :class="getRecommendationStyle(recommendation.primary).iconBgClass"
                                >
                                    <span class="text-3xl">{{ getRecommendationStyle(recommendation.primary).icon }}</span>
                                </div>
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2 mb-2">
                                        <span
                                            class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium"
                                            :class="getRecommendationStyle(recommendation.primary).badgeClass"
                                        >
                                            {{ getRecommendationStyle(recommendation.primary).label }}
                                        </span>
                                    </div>
                                    <h4 class="text-xl font-bold text-slate-900 mb-2">{{ recommendation.primary.targetTitle }}</h4>
                                    <p class="text-sm text-slate-700 leading-relaxed mb-5">{{ recommendation.primary.reason }}</p>
                                    <button
                                        class="inline-flex items-center gap-2 px-6 py-3 text-white text-sm font-semibold rounded-lg transition-all"
                                        :class="getRecommendationStyle(recommendation.primary).buttonClass"
                                        @click="router.push(`/learn/${recommendation.primary.targetSlug}`)"
                                    >
                                        <span>{{ recommendation.primary.actionLabel }}</span>
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>

                        <!-- 备选建议 -->
                        <div
                            v-if="recommendation.alternatives && recommendation.alternatives.length > 0"
                            class="space-y-3"
                        >
                            <h5 class="text-sm font-semibold text-slate-600 px-1">其他选择</h5>
                            <div
                                v-for="(alt, idx) in recommendation.alternatives"
                                :key="idx"
                                class="p-4 rounded-lg border bg-white hover:border-slate-300 hover:shadow-sm transition-all cursor-pointer"
                                @click="router.push(`/learn/${alt.targetSlug}`)"
                            >
                                <div class="flex items-start gap-3">
                                    <div
                                        class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                                        :class="getRecommendationStyle(alt).iconBgClass"
                                    >
                                        <span class="text-xl">{{ getRecommendationStyle(alt).icon }}</span>
                                    </div>
                                    <div class="flex-1 min-w-0">
                                        <div class="flex items-center gap-2 mb-1">
                                            <h5 class="text-base font-bold text-slate-800">{{ alt.targetTitle }}</h5>
                                            <span
                                                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
                                                :class="getRecommendationStyle(alt).badgeClass"
                                            >
                                                {{ getRecommendationStyle(alt).label }}
                                            </span>
                                        </div>
                                        <p class="text-xs text-slate-600 leading-relaxed">{{ alt.reason }}</p>
                                    </div>
                                    <svg class="w-5 h-5 text-slate-400 shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                                    </svg>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- 兜底：推荐系统无结果时，使用课程导航的下一课 -->
                    <div
                        v-else-if="lesson.nextLesson"
                        class="mt-12 p-5 rounded-xl border border-blue-100 bg-blue-50/50"
                    >
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center shrink-0">
                                <span class="text-xl">💡</span>
                            </div>
                            <div class="flex-1 min-w-0">
                                <p class="text-xs font-medium text-blue-700 mb-0.5">下一步学习建议</p>
                                <h4 class="text-base font-bold text-slate-800">{{ lesson.nextLesson.title }}</h4>
                            </div>
                            <button
                                class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors shrink-0"
                                @click="goToLesson(lesson.nextLesson!.slug)"
                            >
                                继续学习
                            </button>
                        </div>
                    </div>

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
               动手练习（Phase 2 有结构化练习时自动隐藏）
          ================================================= -->
                    <div v-if="!lesson.practiceObjective" class="mt-10 rounded-2xl border border-blue-100 bg-blue-50/50 p-6">
                        <div class="flex items-center gap-2 mb-3">
                            <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                            </svg>
                            <h3 class="text-lg font-bold text-blue-800">动手练习</h3>
                        </div>
                        <p class="text-sm text-blue-700/80 mb-4">
                            学完之后，试试在 Playground 中自己动手改一改：
                        </p>
                        <ul class="space-y-2 text-sm text-blue-700">
                            <li class="flex items-start gap-2">
                                <span class="text-blue-400 mt-0.5">•</span>
                                <span>尝试修改代码中的筛选条件或排序方式，观察输出变化</span>
                            </li>
                            <li class="flex items-start gap-2">
                                <span class="text-blue-400 mt-0.5">•</span>
                                <span>增加一个新的聚合操作（如 group_by / GROUP BY）</span>
                            </li>
                            <li class="flex items-start gap-2">
                                <span class="text-blue-400 mt-0.5">•</span>
                                <span>向 Agent 提问："根据本课给我一个小练习"</span>
                            </li>
                        </ul>
                        <button
                            class="mt-4 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
                            @click="openInPlayground()"
                        >
                            <svg class="w-4 h-4 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            去 Playground 练习
                        </button>
                    </div>

                    <!-- ================================================
               下一步引导
          ================================================= -->
                    <div class="mt-8 rounded-2xl border border-slate-100 bg-white p-6">
                        <h3 class="text-base font-bold text-slate-800 mb-4">下一步</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <!-- 去 Playground 练习 -->
                            <button
                                class="flex items-center gap-3 p-4 rounded-xl border border-slate-100 hover:border-blue-200 hover:bg-blue-50/50 text-left transition-all"
                                @click="openInPlayground()"
                            >
                                <div class="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                                    <svg class="w-5 h-5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                </div>
                                <div>
                                    <p class="text-sm font-semibold text-slate-700">去 Playground 练习</p>
                                    <p class="text-xs text-slate-400">动手改代码、跑起来看效果</p>
                                </div>
                            </button>

                            <!-- 让 AI 出题 -->
                            <button
                                class="flex items-center gap-3 p-4 rounded-xl border border-slate-100 hover:border-blue-200 hover:bg-blue-50/50 text-left transition-all"
                                @click="router.push(`/playground/${lesson.slug}?action=exercise`)"
                            >
                                <div class="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center shrink-0">
                                    <svg class="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                    </svg>
                                </div>
                                <div>
                                    <p class="text-sm font-semibold text-slate-700">让 AI 出题</p>
                                    <p class="text-xs text-slate-400">基于本课内容生成练习</p>
                                </div>
                            </button>

                            <!-- 下一课 -->
                            <button
                                v-if="recommendationCta"
                                class="flex items-center gap-3 p-4 rounded-xl border border-slate-100 hover:border-blue-200 hover:bg-blue-50/50 text-left transition-all"
                                @click="goToLesson(recommendationCta.slug)"
                            >
                                <div class="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                                    <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                                    </svg>
                                </div>
                                <div>
                                    <p class="text-sm font-semibold text-slate-700">{{ recommendationCta.actionLabel }}</p>
                                    <p class="text-xs text-slate-400 truncate max-w-[160px]">{{ recommendationCta.title }}</p>
                                </div>
                            </button>
                        </div>
                        <p
                            v-if="recommendationCta?.reason"
                            class="mt-4 text-xs leading-relaxed text-slate-500"
                        >
                            {{ recommendationCta.reason }}
                        </p>
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
                                    class="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm font-medium text-slate-600 transition-all hover:border-slate-300 hover:text-slate-800"
                                    :disabled="isSavingSnapshot"
                                    @click="saveLessonSnapshot"
                                >
                                    <svg class="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5h14v14H5z" />
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5v4h6V5" />
                                    </svg>
                                    {{ snapshotSaved ? "已保存练习起点" : isSavingSnapshot ? "保存中..." : "保存当前示例" }}
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
   完成庆祝动画
===================================================== */
.completion-fade-enter-active {
    transition: opacity 0.3s ease;
}
.completion-fade-leave-active {
    transition: opacity 0.8s ease;
}
.completion-fade-enter-from,
.completion-fade-leave-to {
    opacity: 0;
}

@keyframes completion-bounce {
    0% { transform: scale(0.3); opacity: 0; }
    50% { transform: scale(1.1); }
    70% { transform: scale(0.95); }
    100% { transform: scale(1); opacity: 1; }
}
.animate-completion-bounce {
    animation: completion-bounce 0.6s ease-out forwards;
}

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

.lesson-content :deep(ol li::marker) {
    color: #3b82f6;
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

/* 表格 */
.lesson-content :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 1.25rem 0;
    font-size: 0.875rem;
    line-height: 1.6;
}
.lesson-content :deep(th),
.lesson-content :deep(td) {
    border: 1px solid #e2e8f0;
    padding: 0.5rem 0.75rem;
    text-align: left;
}
.lesson-content :deep(th) {
    background: #f8fafc;
    font-weight: 600;
    color: #1e293b;
}
.lesson-content :deep(td) {
    color: #374151;
}
.lesson-content :deep(tr:nth-child(even)) {
    background: #f8fafc;
}
.lesson-content :deep(table .inline-code) {
    font-size: 0.8em;
}
</style>
