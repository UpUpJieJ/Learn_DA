<script setup lang="ts">
// =====================================================
// 课程地图（改版 P1）
//
// 单一职责：按 track 纵览 13 门课的任务级进度，一次点击进入任务。
// 数据来自 GET /workspace/progress（task_attempts 聚合），没有数据时显示
// 真实的 0 而不是假进度。
// =====================================================

import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { fetchProgress, type LessonProgress, type ProgressPayload } from "@/api/workspace";
import { AppButton, AppCard, EmptyState, StatusPill } from "@/components/ui";
import { useAsyncState } from "@/composables/useAsyncState";

const router = useRouter();

const progress = useAsyncState<ProgressPayload>(() => fetchProgress(), {
    isEmpty: (value) => value.lessons.length === 0,
});

const summary = computed(() => progress.data.value?.summary ?? null);
const lessons = computed(() => progress.data.value?.lessons ?? []);
const tracks = computed(() => progress.data.value?.tracks ?? []);

/** 回访主流程：一键回到「上次做到的任务」（设计稿 §15.2，1 击可达）。 */
const continueTarget = computed<LessonProgress | null>(() => {
    const started = lessons.value
        .filter((item) => item.status === "in_progress" && item.lastActivityAt)
        .sort((left, right) => String(right.lastActivityAt).localeCompare(String(left.lastActivityAt)));
    if (started.length > 0) return started[0] ?? null;
    if (summary.value && summary.value.attemptsTotal === 0) return lessons.value[0] ?? null;
    return lessons.value.find((item) => item.status !== "completed") ?? null;
});

interface TrackGroup {
    track: string;
    label: string;
    items: LessonProgress[];
}

const groups = computed<TrackGroup[]>(() => {
    const map = new Map<string, TrackGroup>();
    for (const lesson of lessons.value) {
        const key = lesson.track ?? "other";
        let group = map.get(key);
        if (!group) {
            const meta = tracks.value.find((item) => item.track === key);
            group = { track: key, label: meta?.label ?? key, items: [] };
            map.set(key, group);
        }
        group.items.push(lesson);
    }
    return [...map.values()];
});

function ratio(passed: number, total: number): number {
    if (total <= 0) return 0;
    return Math.round((passed / total) * 100);
}

function pillStatus(lesson: LessonProgress): string {
    if (lesson.status === "completed") return "passed";
    if (lesson.status === "in_progress") return "in_progress";
    return "todo";
}

function pillLabel(lesson: LessonProgress): string {
    if (lesson.status === "completed") return "已完成";
    if (lesson.status === "in_progress") return `${lesson.passedTasks}/${lesson.totalTasks} 任务`;
    return "未开始";
}

function ctaLabel(lesson: LessonProgress): string {
    if (lesson.status === "completed") return "复习";
    if (lesson.status === "in_progress") return "继续";
    return "开始";
}

function open(lesson: LessonProgress) {
    const query =
        lesson.status !== "completed" && lesson.currentTaskId
            ? { task: lesson.currentTaskId }
            : undefined;
    void router.push({ path: `/lesson/${lesson.lessonSlug}`, query });
}

function lastSeen(lesson: LessonProgress): string {
    if (!lesson.lastActivityAt) return "还没开始";
    const stamp = new Date(lesson.lastActivityAt);
    if (Number.isNaN(stamp.getTime())) return "还没开始";
    return new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(stamp);
}

onMounted(() => {
    void progress.run();
});
</script>

<template>
    <div class="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
        <header class="mb-6">
            <h1 class="text-2xl font-bold text-ink-900">课程地图</h1>
            <p class="mt-1 text-sm text-ink-500">
                按学习路径纵览每门课的任务进度，点「继续」直接回到上次做到的那一格。
            </p>
        </header>

        <!-- 三态：loading -->
        <div v-if="progress.isLoading.value" class="space-y-3">
            <div v-for="index in 3" :key="index" class="h-24 animate-pulse rounded-card bg-surface-raised" />
        </div>

        <!-- 三态：error -->
        <AppCard v-else-if="progress.isError.value" title="课程地图加载失败">
            <p class="text-sm text-ink-500">{{ progress.error.value }}</p>
            <template #footer>
                <AppButton variant="primary" :loading="progress.isLoading.value" @click="progress.retry()">
                    重试
                </AppButton>
            </template>
        </AppCard>

        <!-- 三态：empty -->
        <EmptyState
            v-else-if="progress.isEmpty.value"
            title="还没有可练习的课程"
            hint="课程内容正在准备中，先回首页看看平台能做什么。"
            cta="回到首页"
            @action="router.push('/')"
        />

        <template v-else>
            <!-- 汇总 -->
            <div v-if="summary" class="mb-6 grid gap-3 sm:grid-cols-3">
                <AppCard dense>
                    <p class="text-xs font-medium text-ink-500">已通过任务</p>
                    <p class="mt-1 text-xl font-bold text-ink-900">
                        {{ summary.tasksPassed }}<span class="text-sm font-medium text-ink-300"> / {{ summary.tasksTotal }}</span>
                    </p>
                </AppCard>
                <AppCard dense>
                    <p class="text-xs font-medium text-ink-500">完成课程</p>
                    <p class="mt-1 text-xl font-bold text-ink-900">
                        {{ summary.lessonsCompleted }}<span class="text-sm font-medium text-ink-300"> / {{ summary.lessonsTotal }}</span>
                    </p>
                </AppCard>
                <AppCard dense>
                    <p class="text-xs font-medium text-ink-500">在学课程</p>
                    <p class="mt-1 text-xl font-bold text-ink-900">{{ summary.lessonsStarted }}</p>
                </AppCard>
            </div>

            <!-- 继续上次 -->
            <AppCard v-if="continueTarget" class="mb-6">
                <div class="flex flex-wrap items-center justify-between gap-3">
                    <div class="min-w-0">
                        <p class="text-xs font-medium text-brand-600">
                            {{ continueTarget.status === "not_started" ? "从这里开始" : "继续上次" }}
                        </p>
                        <p class="mt-1 truncate text-base font-semibold text-ink-900">
                            {{ continueTarget.title }}
                        </p>
                        <p class="mt-0.5 text-xs text-ink-500">
                            {{ continueTarget.passedTasks }}/{{ continueTarget.totalTasks }} 任务
                            · 最近学习 {{ lastSeen(continueTarget) }}
                        </p>
                    </div>
                    <AppButton variant="primary" @click="open(continueTarget)">
                        {{ continueTarget.status === "not_started" ? "开始学习" : "继续" }}
                    </AppButton>
                </div>
            </AppCard>

            <!-- 按 track 分组 -->
            <section v-for="group in groups" :key="group.track" class="mb-6">
                <div class="mb-2 flex items-center justify-between">
                    <h2 class="text-base font-semibold text-ink-900">{{ group.label }}</h2>
                    <span class="text-xs text-ink-500">{{ group.items.length }} 门课</span>
                </div>
                <div class="space-y-2">
                    <AppCard v-for="lesson in group.items" :key="lesson.lessonSlug" dense>
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <div class="flex flex-wrap items-center gap-2">
                                    <span class="text-sm font-semibold text-ink-900">{{ lesson.title }}</span>
                                    <StatusPill :status="pillStatus(lesson)" :label="pillLabel(lesson)" size="sm" />
                                </div>
                                <div class="mt-2 flex items-center gap-3">
                                    <div class="h-1.5 w-40 overflow-hidden rounded-full bg-surface-raised">
                                        <div
                                            class="h-full rounded-full"
                                            :class="lesson.status === 'completed' ? 'bg-ok-500' : 'bg-brand-500'"
                                            :style="{ width: `${ratio(lesson.passedTasks, lesson.totalTasks)}%` }"
                                        />
                                    </div>
                                    <span class="text-xs text-ink-500">
                                        {{ lesson.passedTasks }}/{{ lesson.totalTasks }} 任务
                                        <template v-if="lesson.estimatedMinutes"> · 约 {{ lesson.estimatedMinutes }} 分钟</template>
                                    </span>
                                </div>
                            </div>
                            <AppButton
                                :variant="lesson.status === 'completed' ? 'secondary' : 'primary'"
                                size="sm"
                                @click="open(lesson)"
                            >
                                {{ ctaLabel(lesson) }}
                            </AppButton>
                        </div>
                    </AppCard>
                </div>
            </section>
        </template>
    </div>
</template>