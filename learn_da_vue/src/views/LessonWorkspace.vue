<template>
    <div class="min-h-screen bg-surface-page">
        <div class="mx-auto max-w-[1500px] px-4 py-6 lg:px-6">
            <!-- 顶栏：课程名 + 进度 + 保存状态 -->
            <header class="mb-5 flex flex-wrap items-center gap-3">
                <RouterLink
                    to="/learn"
                    class="text-sm text-ink-500 hover:text-ink-700"
                >
                    ← 课程
                </RouterLink>
                <h1 class="text-lg font-semibold text-ink-900">
                    {{ lesson?.title ?? slug }}
                </h1>
                <StatusPill
                    v-if="tasks.length"
                    :status="allPassed ? 'passed' : 'in_progress'"
                    :label="`任务 ${passedTasks}/${tasks.length}`"
                />
                <span
                    v-if="saveState !== 'idle'"
                    class="ml-auto text-xs"
                    :class="saveState === 'error' ? 'text-err-600' : 'text-ink-300'"
                >
                    {{
                        saveState === "saving"
                            ? "保存中…"
                            : saveState === "dirty"
                              ? "有未保存修改"
                              : saveState === "error"
                                ? "保存失败"
                                : "已保存"
                    }}
                </span>
            </header>

            <!-- 加载 / 失败 / 无工作区 -->
            <div v-if="loading" class="flex items-center gap-2 text-sm text-ink-500">
                <span class="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand-600"></span>
                正在准备工作区…
            </div>
            <EmptyState
                v-else-if="error && !snapshot"
                title="工作区打不开"
                :hint="error"
                cta="重试"
                @action="load(slug)"
            />
            <EmptyState
                v-else-if="!snapshot"
                title="这门课还没有可交互的工作区"
                hint="当前只有样板课（Polars 分组聚合）支持多格任务式练习。"
                cta="去课程列表"
                @action="router.push('/learn')"
            />

            <div
                v-else
                class="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)_320px] lg:items-start"
            >
                <!-- 左栏：任务清单 + 数据集 -->
                <aside class="space-y-4 lg:sticky lg:top-6">
                    <AppCard>
                        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-300">
                            任务
                        </h2>
                        <ol class="space-y-1">
                            <li v-for="(task, index) in tasks" :key="task.taskId">
                                <button
                                    type="button"
                                    class="flex w-full items-start gap-2 rounded-control px-2 py-1.5 text-left hover:bg-surface-raised"
                                    :class="
                                        activeTaskId === task.taskId
                                            ? 'bg-surface-raised'
                                            : ''
                                    "
                                    @click="focusCell(task.cellId)"
                                >
                                    <span class="mt-0.5 font-mono text-xs text-ink-300">
                                        {{ index + 1 }}
                                    </span>
                                    <span class="min-w-0 flex-1">
                                        <span class="block text-sm text-ink-700">
                                            {{ task.title }}
                                        </span>
                                        <span class="mt-0.5 block text-[11px] text-ink-300">
                                            {{ taskStatusMeta(task.status).label }}
                                        </span>
                                    </span>
                                    <StatusPill :status="task.status" size="sm" />
                                </button>
                            </li>
                        </ol>
                    </AppCard>

                    <AppCard v-if="snapshot.datasets.length">
                        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-300">
                            数据集
                        </h2>
                        <ul class="space-y-1 text-xs text-ink-500">
                            <li
                                v-for="dataset in snapshot.datasets"
                                :key="dataset"
                                class="font-mono"
                            >
                                data/{{ dataset }}
                            </li>
                        </ul>
                        <p class="mt-2 text-[11px] text-ink-300">
                            只读挂载；用 pl.read_csv 读入。
                        </p>
                    </AppCard>
                </aside>

                <!-- 中栏：单元格 -->
                <main class="space-y-4">
                    <div
                        v-if="staleNeedsAttention"
                        class="flex items-start gap-2 rounded-card border border-warn-500/40 bg-warn-50 px-3 py-2 text-xs text-warn-700"
                    >
                        <span>⚠︎</span>
                        <span>
                            从单元格 <code class="font-mono">{{ staleFrom }}</code> 起需要重新执行：
                            上游代码改过，后面的结果不再有效。按顺序运行到当前任务。
                        </span>
                    </div>

                    <AppCard
                        v-for="cell in cells"
                        :id="`cell-${cell.cellId}`"
                        :key="cell.cellId"
                        :padded="false"
                        class="overflow-hidden"
                        :class="
                            activeCellId === cell.cellId
                                ? 'ring-1 ring-brand-300'
                                : ''
                        "
                    >
                        <div
                            class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2"
                        >
                            <button
                                type="button"
                                class="font-mono text-xs text-ink-300 hover:text-ink-700"
                                @click="activeCellId = cell.cellId"
                            >
                                {{ cell.cellId }}
                            </button>
                            <span class="text-xs text-ink-500">
                                {{
                                    cell.kind === "starter"
                                        ? "起始代码"
                                        : cellTask(cell)?.title ?? "任务"
                                }}
                            </span>
                            <StatusPill
                                :status="cellPillStatus(cell)"
                                :label="cellPillLabel(cell)"
                                size="sm"
                            />
                            <div class="ml-auto flex items-center gap-2">
                                <AppButton
                                    variant="secondary"
                                    size="sm"
                                    :loading="runningCellId === cell.cellId"
                                    :disabled="Boolean(runningCellId)"
                                    @click="run(cell.cellId)"
                                >
                                    运行
                                </AppButton>
                                <AppButton
                                    v-if="cellTask(cell)"
                                    :variant="
                                        activeCellId === cell.cellId ? 'primary' : 'ghost'
                                    "
                                    size="sm"
                                    :loading="submittingTaskId === cellTask(cell)!.taskId"
                                    :disabled="Boolean(submittingTaskId) || Boolean(runningCellId)"
                                    @click="submit(cellTask(cell)!.taskId)"
                                >
                                    提交任务
                                </AppButton>
                            </div>
                        </div>

                        <textarea
                            :value="cell.code"
                            spellcheck="false"
                            rows="8"
                            class="block w-full resize-y border-0 bg-surface-card px-3 py-2.5 font-mono text-[13px] leading-6 text-ink-900 focus:outline-none"
                            :aria-label="`单元格 ${cell.cellId} 的代码`"
                            @focus="activeCellId = cell.cellId"
                            @input="onInput(cell.cellId, $event)"
                            @keydown="onKeydown(cell.cellId, $event)"
                        ></textarea>

                        <div
                            v-if="runs[cell.cellId]"
                            class="border-t border-line px-3 py-2.5"
                            :class="cell.status === 'stale' ? 'opacity-60' : ''"
                        >
                            <p
                                v-if="cell.status === 'stale'"
                                class="mb-1.5 text-[11px] text-warn-700"
                            >
                                结果已过期：本格代码或上游有改动，下面显示的是上一次的输出，重新运行才算数。
                            </p>
                            <CodeOutput
                                :stdout="cellOutput(cell.cellId)?.stdout"
                                :stderr="cellOutput(cell.cellId)?.stderr"
                                :duration-ms="runs[cell.cellId]?.durationMs"
                                :status="outputStatus(cell.cellId)"
                                min-height-class="min-h-[80px]"
                            />
                            <ul
                                v-if="assertionsFor(cell.cellId).length"
                                class="mt-2 space-y-1"
                            >
                                <li
                                    v-for="assertion in assertionsFor(cell.cellId)"
                                    :key="assertion.id"
                                    class="flex items-start gap-2 text-xs"
                                >
                                    <span
                                        class="mt-0.5"
                                        :class="
                                            assertion.status === 'passed'
                                                ? 'text-ok-600'
                                                : assertion.status === 'failed'
                                                  ? 'text-err-600'
                                                  : 'text-ink-300'
                                        "
                                    >
                                        {{
                                            assertion.status === "passed"
                                                ? "✓"
                                                : assertion.status === "failed"
                                                  ? "✗"
                                                  : "–"
                                        }}
                                    </span>
                                    <span class="min-w-0 flex-1">
                                        <span class="text-ink-700">{{ assertion.title }}</span>
                                        <span
                                            v-if="assertion.actual || assertion.detail"
                                            class="mt-0.5 block whitespace-pre-wrap font-mono text-[11px] text-ink-500"
                                        >
                                            {{ assertion.actual || assertion.detail }}
                                        </span>
                                    </span>
                                </li>
                            </ul>
                            <p
                                v-if="runs[cell.cellId]?.assertionsSkipped"
                                class="mt-1 text-[11px] text-ink-300"
                            >
                                前面的单元格没有全部执行成功，断言未求值。
                            </p>
                        </div>
                    </AppCard>
                </main>

                <!-- 右栏：任务目标 + 教练入口 -->
                <aside class="space-y-4 lg:sticky lg:top-6">
                    <AppCard>
                        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-300">
                            当前任务
                        </h2>
                        <template v-if="activeTask">
                            <p class="text-sm font-medium text-ink-900">
                                {{ activeTask.title }}
                            </p>
                            <p class="mt-1 whitespace-pre-wrap text-xs leading-5 text-ink-500">
                                {{ activeTask.objective }}
                            </p>
                            <div class="mt-3">
                                <StatusPill :status="activeTask.status" size="sm" />
                            </div>
                        </template>
                        <p v-else class="text-xs text-ink-300">
                            点一下任务或单元格，这里会显示任务目标。
                        </p>
                    </AppCard>

                    <AppCard>
                        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-300">
                            教练
                        </h2>
                        <p class="text-xs leading-5 text-ink-500">
                            AI 教练入口会在后续接入：提交失败后可以针对具体断言提问，
                            提示分级由服务端统计。
                        </p>
                        <AppButton
                            class="mt-3"
                            variant="ghost"
                            size="sm"
                            disabled
                            label="即将开放"
                        >
                            问教练
                        </AppButton>
                    </AppCard>

                    <p class="px-1 text-[11px] leading-5 text-ink-300">
                        快捷键：Ctrl/⌘ + Enter 运行当前格；Shift + Enter 换行。
                    </p>
                </aside>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { fetchLessonBySlug } from "@/api/learning";
import type { LessonDetail } from "@/types/api";
import { AppButton, AppCard, CodeOutput, EmptyState, StatusPill, taskStatusMeta } from "@/components/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import type { WorkspaceCell } from "@/api/workspace";

const route = useRoute();
const router = useRouter();
const store = useWorkspaceStore();

const slug = computed(() => String(route.params.slug ?? ""));
const lesson = ref<LessonDetail | null>(null);
const activeCellId = ref<string | null>(null);
const activeTaskId = ref<string | null>(null);

const snapshot = computed(() => store.snapshot);
const loading = computed(() => store.loading);
const error = computed(() => store.error);
const cells = computed(() => store.cells);
const tasks = computed(() => store.tasks);
const passedTasks = computed(() => store.passedTasks);
const allPassed = computed(() => store.allPassed);
const staleFrom = computed(() => store.staleFrom);
/** 全部都是 stale（刚进来还没跑过）不算"上游改动"，不用吓人。 */
const staleNeedsAttention = computed(() => {
    const cellId = staleFrom.value;
    if (!cellId) return false;
    const index = cells.value.findIndex((cell) => cell.cellId === cellId);
    return index > 0;
});
const saveState = computed(() => store.saveState);
const runs = computed(() => store.runs);
const runningCellId = computed(() => store.runningCellId);
const submittingTaskId = computed(() => store.submittingTaskId);

const activeTask = computed(
    () => tasks.value.find((task) => task.taskId === activeTaskId.value) ?? null,
);

function load(lessonSlug: string) {
    activeCellId.value = null;
    activeTaskId.value = null;
    return store.load(lessonSlug);
}

function cellTask(cell: WorkspaceCell) {
    return tasks.value.find((task) => task.cellId === cell.cellId) ?? null;
}

function cellPillStatus(cell: WorkspaceCell) {
    if (cell.status === "ok") return "passed";
    if (cell.status === "failed") return "failed";
    return "todo";
}

function cellPillLabel(cell: WorkspaceCell) {
    if (cell.status === "ok") return "已执行";
    if (cell.status === "failed") return "执行失败";
    return "待执行";
}

function cellOutput(cellId: string) {
    const run = runs.value[cellId];
    if (!run) return null;
    return run.cells.find((item) => item.cellId === cellId) ?? null;
}

function outputStatus(cellId: string): "idle" | "running" | "success" | "error" {
    if (runningCellId.value === cellId) return "running";
    const run = runs.value[cellId];
    if (!run) return "idle";
    return run.verdict === "passed" ? "success" : "error";
}

function assertionsFor(cellId: string) {
    return store.assertionsFor(cellId);
}

function onInput(cellId: string, event: Event) {
    const target = event.target as HTMLTextAreaElement | null;
    if (!target) return;
    store.editCell(cellId, target.value);
}

function onKeydown(cellId: string, event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        void run(cellId);
    }
}

function focusCell(cellId: string) {
    activeCellId.value = cellId;
    const task = tasks.value.find((item) => item.cellId === cellId);
    activeTaskId.value = task?.taskId ?? null;
    const element = document.getElementById(`cell-${cellId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
    const textarea = element?.querySelector("textarea");
    textarea?.focus({ preventScroll: true });
}

async function run(cellId: string) {
    activeCellId.value = cellId;
    const task = tasks.value.find((item) => item.cellId === cellId);
    activeTaskId.value = task?.taskId ?? null;
    await store.runCell(cellId);
}

async function submit(taskId: string) {
    activeTaskId.value = taskId;
    await store.submitTask(taskId);
}

onMounted(async () => {
    await load(slug.value);
    void fetchLessonBySlug(slug.value)
        .then((detail) => {
            lesson.value = detail;
        })
        .catch(() => {
            lesson.value = null;
        });
});

onBeforeUnmount(() => {
    void store.flushAll();
    store.reset();
});
</script>