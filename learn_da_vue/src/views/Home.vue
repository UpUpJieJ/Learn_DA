<script setup lang="ts">
// =====================================================
// 今日（首页，改版 P5）
//
// 单一职责：回答「我现在该做什么」。
//  - 一张主卡：继续上次那个任务（1 击进入，深链带 ?task=）
//  - 一条指标带：已通过任务 / 完成课程 / 一次通过率 / 连续学习
//  - 一张卡点卡：上次没通过的那条断言，点一下就回到那个任务
//  - 两门「接下来」+ 各路径进度 + 两个入口（实验室 / 学习报告）
//
// 数据只来自 GET /workspace/report（task_attempts 真实聚合），没有把营销
// 文案和平台级「今日活跃」塞进来——首页不编数字。
// =====================================================

import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { fetchReport, type ErrorPattern, type LessonProgress, type ReportPayload } from "@/api/workspace";
import { AppButton, AppCard, EmptyState, StatusPill } from "@/components/ui";
import { useAsyncState } from "@/composables/useAsyncState";

const router = useRouter();

const report = useAsyncState<ReportPayload>(() => fetchReport(), {
    isEmpty: (value) => value.lessonProgress.length === 0,
});

const summary = computed(() => report.data.value?.summary ?? null);
const lessons = computed(() => report.data.value?.lessonProgress ?? []);
const tracks = computed(() => report.data.value?.tracks ?? []);
const topError = computed<ErrorPattern | null>(() => report.data.value?.errorPatterns[0] ?? null);

/** 回访主流程：In-progress 里最近动过的那门课；全新访客落到第一门未完成的课；全做完则回到第一门复习。 */
const continueTarget = computed<LessonProgress | null>(() => {
    const started = lessons.value
        .filter((item) => item.status === "in_progress" && item.lastActivityAt)
        .sort((left, right) => String(right.lastActivityAt).localeCompare(String(left.lastActivityAt)));
    if (started.length > 0) return started[0] ?? null;
    return lessons.value.find((item) => item.status !== "completed") ?? lessons.value[0] ?? null;
});

const hasHistory = computed(() => (summary.value?.attemptsTotal ?? 0) > 0);

/** 主卡之外，再推荐两门没做完的课。 */
const nextUp = computed<LessonProgress[]>(() =>
    lessons.value
        .filter((item) => item.status !== "completed" && item.lessonSlug !== continueTarget.value?.lessonSlug)
        .slice(0, 2),
);

const greeting = computed(() => {
    const hour = new Date().getHours();
    if (hour < 6) return "夜深了";
    if (hour < 12) return "早上好";
    if (hour < 18) return "下午好";
    return "晚上好";
});

const overviewLine = computed(() => {
    const value = summary.value;
    if (!value || !hasHistory.value) return "还没有学习记录 —— 从下面这门课的第一个任务开始。";
    const parts = [`已完成 ${value.tasksPassed}/${value.tasksTotal} 个任务`];
    if (value.streakDays > 0) parts.push(`连续学习 ${value.streakDays} 天`);
    if ((value.daysSinceActive ?? 0) >= 3) parts.push(`已经 ${value.daysSinceActive} 天没练了`);
    return parts.join(" · ");
});

const firstTryRate = computed(() => {
    const value = summary.value;
    if (!value || value.tasksPassed <= 0) return "—";
    return `${Math.round((Math.min(value.tasksFirstTry, value.tasksPassed) / value.tasksPassed) * 100)}%`;
});

const metrics = computed(() => {
    const value = summary.value;
    return [
        { label: "已通过任务", value: value ? `${value.tasksPassed}` : "—", suffix: value ? `/ ${value.tasksTotal}` : "" },
        { label: "完成课程", value: value ? `${value.lessonsCompleted}` : "—", suffix: value ? `/ ${value.lessonsTotal}` : "" },
        { label: "一次通过率", value: firstTryRate.value, suffix: "" },
        { label: "连续学习", value: value ? `${value.streakDays}` : "—", suffix: "天" },
    ];
});

function primaryLabel(lesson: LessonProgress): string {
    if (lesson.status === "in_progress") return "继续";
    if (lesson.status === "completed") return "复习";
    return "开始学习";
}

function lessonMeta(lesson: LessonProgress): string {
    const bits = [`${lesson.passedTasks}/${lesson.totalTasks} 个任务`];
    if (lesson.estimatedMinutes) bits.push(`约 ${lesson.estimatedMinutes} 分钟`);
    if (lesson.lastActivityAt) bits.push(`最近 ${lastSeen(lesson.lastActivityAt)}`);
    return bits.join(" · ");
}

function lastSeen(value: string): string {
    const stamp = new Date(value);
    if (Number.isNaN(stamp.getTime())) return "—";
    return new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(stamp);
}

function ratio(passed: number, total: number): number {
    if (total <= 0) return 0;
    return Math.round((passed / total) * 100);
}

/** 后端 `ratio` 是 0–1 的小数（`progress.py` 里 round(passed/total, 3)），这里统一换成百分比。 */
function trackRatio(track: { totalTasks: number; passedTasks: number; ratio?: number }): number {
    if (typeof track.ratio === "number") return Math.round(track.ratio * 100);
    return ratio(track.passedTasks, track.totalTasks);
}

function open(lesson: LessonProgress) {
    const query =
        lesson.status !== "completed" && lesson.currentTaskId ? { task: lesson.currentTaskId } : undefined;
    void router.push({ path: `/lesson/${lesson.lessonSlug}`, query });
}

function openError(pattern: ErrorPattern) {
    void router.push({ path: `/lesson/${pattern.lessonSlug}`, query: { task: pattern.taskId } });
}

onMounted(() => {
    void report.run();
});
</script>

<template>
    <div class="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
        <header class="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div>
                <h1 class="text-2xl font-bold text-ink-900">今日</h1>
                <p class="mt-1 text-sm text-ink-500">{{ greeting }}，{{ overviewLine }}</p>
            </div>
            <AppButton variant="ghost" size="sm" @click="router.push('/learn')">课程地图</AppButton>
        </header>

        <!-- 三态：loading -->
        <div v-if="report.isLoading.value" class="space-y-3">
            <div class="h-32 animate-pulse rounded-card bg-surface-raised" />
            <div class="h-20 animate-pulse rounded-card bg-surface-raised" />
        </div>

        <!-- 三态：error -->
        <AppCard v-else-if="report.isError.value" title="加载失败">
            <p class="text-sm text-ink-500">{{ report.error.value }}</p>
            <template #footer>
                <AppButton variant="primary" :loading="report.isLoading.value" @click="report.retry()">
                    重试
                </AppButton>
            </template>
        </AppCard>

        <!-- 三态：empty -->
        <EmptyState
            v-else-if="report.isEmpty.value"
            title="还没有可以练习的课"
            hint="课程内容正在准备中，先到实验室跑一段代码熟悉一下。"
            cta="打开实验室"
            @action="router.push('/lab')"
        />

        <template v-else>
            <!-- 主卡：继续上次 -->
            <section v-if="continueTarget" class="mb-4">
                <AppCard>
                    <div class="flex flex-wrap items-start justify-between gap-4">
                        <div class="min-w-0 flex-1">
                            <p class="text-xs font-medium text-brand-600">
                                {{ hasHistory ? "继续上次" : "从这里开始" }}
                            </p>
                            <h2 class="mt-1 text-lg font-semibold text-ink-900">{{ continueTarget.title }}</h2>
                            <p class="mt-1 text-sm text-ink-500">{{ lessonMeta(continueTarget) }}</p>
                            <div class="mt-3 flex items-center gap-3">
                                <div class="h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-surface-raised">
                                    <div
                                        class="h-full rounded-full"
                                        :class="continueTarget.status === 'completed' ? 'bg-ok-500' : 'bg-brand-500'"
                                        :style="{ width: `${ratio(continueTarget.passedTasks, continueTarget.totalTasks)}%` }"
                                    />
                                </div>
                                <span class="shrink-0 text-xs text-ink-500">
                                    {{ ratio(continueTarget.passedTasks, continueTarget.totalTasks) }}%
                                </span>
                            </div>
                        </div>
                        <AppButton variant="primary" @click="open(continueTarget)">
                            {{ primaryLabel(continueTarget) }}
                        </AppButton>
                    </div>
                </AppCard>
            </section>

            <!-- 指标带 -->
            <section class="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <AppCard v-for="metric in metrics" :key="metric.label" dense>
                    <p class="text-xs font-medium text-ink-500">{{ metric.label }}</p>
                    <p class="mt-1 text-xl font-bold text-ink-900">
                        {{ metric.value }}
                        <span v-if="metric.suffix" class="text-sm font-medium text-ink-300">{{ metric.suffix }}</span>
                    </p>
                </AppCard>
            </section>

            <!-- 上次卡在哪 -->
            <section v-if="topError" class="mb-6">
                <AppCard>
                    <div class="flex flex-wrap items-start justify-between gap-3">
                        <div class="min-w-0">
                            <div class="flex flex-wrap items-center gap-2">
                                <p class="text-xs font-medium text-ink-500">上次卡住的地方</p>
                                <StatusPill status="failed" :label="`失败 ${topError.count} 次`" size="sm" />
                            </div>
                            <p class="mt-1 text-sm font-semibold text-ink-900">
                                {{ topError.lessonTitle }} › {{ topError.taskTitle }}
                            </p>
                            <p class="mt-1 text-sm text-ink-500">{{ topError.title }}</p>
                            <pre
                                v-if="topError.lastActual"
                                class="mt-2 overflow-x-auto rounded-control bg-surface-raised px-3 py-2 font-mono text-xs text-ink-700"
                            >{{ topError.lastActual }}</pre>
                        </div>
                        <AppButton variant="secondary" size="sm" @click="openError(topError)">
                            回去看看
                        </AppButton>
                    </div>
                </AppCard>
            </section>

            <!-- 接下来 -->
            <section v-if="nextUp.length > 0" class="mb-6">
                <div class="mb-2 flex items-center justify-between">
                    <h2 class="text-base font-semibold text-ink-900">接下来</h2>
                    <AppButton variant="ghost" size="sm" @click="router.push('/learn')">全部课程</AppButton>
                </div>
                <div class="grid gap-3 sm:grid-cols-2">
                    <AppCard v-for="lesson in nextUp" :key="lesson.lessonSlug" dense>
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-semibold text-ink-900">{{ lesson.title }}</p>
                                <p class="mt-1 text-xs text-ink-500">{{ lessonMeta(lesson) }}</p>
                            </div>
                            <AppButton :variant="lesson.status === 'in_progress' ? 'primary' : 'secondary'" size="sm" @click="open(lesson)">
                                {{ primaryLabel(lesson) }}
                            </AppButton>
                        </div>
                    </AppCard>
                </div>
            </section>

            <!-- 路径进度 -->
            <section v-if="tracks.length > 0" class="mb-6">
                <h2 class="mb-2 text-base font-semibold text-ink-900">学习路径</h2>
                <AppCard dense>
                    <div class="space-y-3">
                        <div v-for="track in tracks" :key="track.track" class="flex items-center gap-3">
                            <span class="w-28 shrink-0 truncate text-xs text-ink-700">{{ track.label }}</span>
                            <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-raised">
                                <div class="h-full rounded-full bg-brand-500" :style="{ width: `${trackRatio(track)}%` }" />
                            </div>
                            <span class="w-16 shrink-0 text-right text-xs text-ink-500">
                                {{ track.passedTasks }}/{{ track.totalTasks }}
                            </span>
                        </div>
                    </div>
                </AppCard>
            </section>

            <!-- 入口 -->
            <section class="grid gap-3 sm:grid-cols-2">
                <AppCard dense>
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <p class="text-sm font-semibold text-ink-900">实验室</p>
                            <p class="mt-0.5 text-xs text-ink-500">不挂课程，随手跑一段 Python。</p>
                        </div>
                        <AppButton variant="secondary" size="sm" @click="router.push('/lab')">打开</AppButton>
                    </div>
                </AppCard>
                <AppCard dense>
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <p class="text-sm font-semibold text-ink-900">学习报告</p>
                            <p class="mt-0.5 text-xs text-ink-500">能力分布、常见卡点与最近提交。</p>
                        </div>
                        <AppButton variant="secondary" size="sm" @click="router.push('/report')">查看</AppButton>
                    </div>
                </AppCard>
            </section>
        </template>
    </div>
</template>