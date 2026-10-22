<script setup lang="ts">
// =====================================================
// 首页「继续上次」条（设计稿 §15.2）
//
// 回访主流程：1 次点击回到上次做到的任务（改造前需要 3 击且得自己回忆学到哪）。
// 没有学习记录时降级为「从第一课开始」，空态也给出动作。
// =====================================================

import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { fetchProgress, type LessonProgress, type ProgressPayload } from "@/api/workspace";
import { AppButton } from "@/components/ui";
import { useAsyncState } from "@/composables/useAsyncState";

const router = useRouter();

const progress = useAsyncState<ProgressPayload>(() => fetchProgress(), {
    isEmpty: (value) => value.lessons.length === 0,
});

const target = computed<LessonProgress | null>(() => {
    const lessons = progress.data.value?.lessons ?? [];
    const started = lessons
        .filter((item) => item.status === "in_progress" && item.lastActivityAt)
        .sort((left, right) => String(right.lastActivityAt).localeCompare(String(left.lastActivityAt)));
    if (started.length > 0) return started[0] ?? null;
    return lessons.find((item) => item.status === "not_started") ?? lessons[0] ?? null;
});

const summary = computed(() => progress.data.value?.summary ?? null);
const hasHistory = computed(() => (summary.value?.attemptsTotal ?? 0) > 0);

const hint = computed(() => {
    if (!target.value) return "";
    if (hasHistory.value) {
        return `${target.value.passedTasks}/${target.value.totalTasks} 任务 · 接着上次的位置继续`;
    }
    return `${target.value.totalTasks} 个任务 · 从第一门课开始`;
});

function go() {
    const lesson = target.value;
    if (!lesson) {
        void router.push("/learn");
        return;
    }
    const query =
        lesson.status !== "completed" && lesson.currentTaskId ? { task: lesson.currentTaskId } : undefined;
    void router.push({ path: `/lesson/${lesson.lessonSlug}`, query });
}

onMounted(() => {
    void progress.run();
});
</script>

<template>
    <!-- 加载中和失败都直接隐藏：首页不该为这一条卡住渲染 -->
    <div
        v-if="target"
        class="mx-auto w-full max-w-5xl px-4 pt-6 sm:px-6"
    >
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-surface-card px-4 py-3 shadow-card">
            <div class="min-w-0">
                <p class="text-xs font-medium text-brand-600">
                    {{ hasHistory ? "继续上次" : "从这里开始" }}
                </p>
                <p class="mt-0.5 truncate text-sm font-semibold text-ink-900">{{ target.title }}</p>
                <p class="text-xs text-ink-500">{{ hint }}</p>
            </div>
            <AppButton variant="primary" size="sm" @click="go">
                {{ hasHistory ? "继续" : "开始学习" }}
            </AppButton>
        </div>
    </div>
</template>