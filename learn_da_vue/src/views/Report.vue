<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { fetchReport } from "@/api/workspace";
import type {
    ErrorPattern,
    RecentAttempt,
    ReportPayload,
    TrackProgress,
} from "@/api/workspace";
import { useAsyncState } from "@/composables/useAsyncState";
import { AppButton, AppCard, EmptyState, StatusPill } from "@/components/ui";

// =====================================================
// 学习报告页（设计稿 §15.2 / §15.3 的 /report）
//
// 单一职责：把 task_attempts 的真实记录翻译成"我强在哪、卡在哪、然后去哪"。
//   - 所有数字都来自后端 learning_report，没有记录就是 0，不补数据、不画假进度条
//   - 三态统一由 useAsyncState 承载（skeleton / empty / error+重试），页面不写 isLoading
//   - 出口：卡点整条可点 → 回对应课程工作区；空态 → 课程地图
// =====================================================

/** 卡点最多展示条数（后端已截断，前端再兜一层，避免布局被撑坏） */
const ERROR_PATTERN_LIMIT = 8;

const router = useRouter();

// =====================================================
// 数据加载（三态）
// =====================================================

const {
    status,
    data,
    error: loadError,
    run,
    retry,
} = useAsyncState<ReportPayload>(() => fetchReport(), {
    // 一次都没提交过的访客：不是"渲染一张全 0 的表"，而是给一条明确的下一步
    isEmpty: (value) => !value || value.summary.attemptsTotal === 0,
});

onMounted(run);

// =====================================================
// 派生数据
// =====================================================

const summary = computed(() => data.value?.summary ?? null);
const tracks = computed<TrackProgress[]>(() => data.value?.tracks ?? []);
const errorPatterns = computed<ErrorPattern[]>(() =>
    (data.value?.errorPatterns ?? []).slice(0, ERROR_PATTERN_LIMIT),
);
const recent = computed<RecentAttempt[]>(() => data.value?.recent ?? []);
const windowDays = computed(() => data.value?.windowDays ?? 0);

// =====================================================
// 指标口径
//
// 一次通过率 = 一次通过任务数 / 已尝试任务数。
// 后端 summary 只给了 tasksFirstTry，没有单独给"已尝试任务数"，
// 所以分母取「已通过任务数 + 卡点记录里出现过的失败任务数」（按 课程+任务 去重）：
// 只失败过、还没通过的任务也算进分母，避免"失败一堆但通过率 100%"的假象。
// =====================================================

const attemptedTasks = computed(() => {
    const base = summary.value?.tasksPassed ?? 0;
    const failedTasks = new Set<string>();
    for (const pattern of data.value?.errorPatterns ?? []) {
        failedTasks.add(`${pattern.lessonSlug}::${pattern.taskId}`);
    }
    return base + failedTasks.size;
});

const firstTryRate = computed(() => {
    const value = summary.value;
    if (!value || value.attemptsTotal === 0 || attemptedTasks.value === 0) return "—";
    const rate = (value.tasksFirstTry / attemptedTasks.value) * 100;
    return `${Math.round(Math.min(100, Math.max(0, rate)))}%`;
});

interface Metric {
    key: string;
    label: string;
    value: string;
    sub: string;
}

const metrics = computed<Metric[]>(() => {
    const value = summary.value;
    return [
        {
            key: "tasks",
            label: "已通过任务",
            value: `${value?.tasksPassed ?? 0} / ${value?.tasksTotal ?? 0}`,
            sub: "任务级判定，以每个任务的最近一次提交为准",
        },
        {
            key: "lessons",
            label: "完成课程",
            value: `${value?.lessonsCompleted ?? 0} / ${value?.lessonsTotal ?? 0}`,
            sub: `已开始 ${value?.lessonsStarted ?? 0} 门（有任何提交即算开始）`,
        },
        {
            key: "streak",
            label: "连续学习",
            value: `${value?.streakDays ?? 0} 天`,
            sub: "最近一次学习落在今天或昨天才开始起算",
        },
        {
            key: "active",
            label: "累计活跃",
            value: `${value?.activeDays ?? 0} 天`,
            sub: "有提交记录的日历天数（UTC 计日）",
        },
        {
            key: "firstTry",
            label: "一次通过率",
            value: firstTryRate.value,
            sub: "一次通过任务数 / 已尝试任务数（含只失败过的任务，同一任务只计一次）",
        },
    ];
});

// =====================================================
// 格式化
// =====================================================

const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
});

/** createdAt / generatedAt 可能为 null 或不可解析，一律降级为 —— */
function formatDateTime(value: string | null | undefined): string {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "—";
    return dateTimeFormatter.format(parsed);
}

function trackPercent(track: TrackProgress): number {
    if (!track.totalTasks) return 0;
    const raw = (track.passedTasks / track.totalTasks) * 100;
    return Math.min(100, Math.max(0, Math.round(raw)));
}

/** Tailwind 只认完整字面量，所以两档 class 必须写全，不能拼字符串 */
function trackBarClass(percent: number): string {
    return percent >= 100 ? "bg-ok-500" : "bg-brand-500";
}

// =====================================================
// 出口
// =====================================================

function goLesson(slug: string): void {
    void router.push(`/lesson/${slug}`);
}

function goLearn(): void {
    void router.push("/learn");
}
</script>

<template>
    <div class="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-8">
        <header class="flex flex-col gap-1">
            <h1 class="text-2xl font-bold text-ink-900">学习报告</h1>
            <p class="text-sm text-ink-500">
                只用你在工作区真实提交过的任务记录计算；没有记录的地方一律显示 0，不编造数据。
            </p>
            <p v-if="status === 'ready' && windowDays > 0" class="text-xs text-ink-500">
                统计窗口：最近 {{ windowDays }} 天 · 生成于
                {{ formatDateTime(data?.generatedAt) }}
            </p>
        </header>

        <!-- ================================================
             加载态：骨架屏（与真实版式同高，避免跳动）
        ================================================= -->
        <div v-if="status === 'loading'" class="flex flex-col gap-4" aria-busy="true">
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <div
                    v-for="i in 5"
                    :key="i"
                    class="h-24 animate-pulse rounded-card border border-line bg-surface-raised"
                />
            </div>
            <div class="h-44 animate-pulse rounded-card border border-line bg-surface-raised" />
            <div class="h-44 animate-pulse rounded-card border border-line bg-surface-raised" />
            <div class="h-36 animate-pulse rounded-card border border-line bg-surface-raised" />
        </div>

        <!-- ================================================
             错误态：说明 + 重试（调 useAsyncState 的 retry）
        ================================================= -->
        <section
            v-else-if="status === 'error'"
            class="rounded-card border border-line bg-surface-card px-6 py-10 text-center shadow-card"
        >
            <p class="text-[15px] font-semibold text-ink-900">报告加载失败</p>
            <p class="mx-auto mt-1 max-w-md text-sm text-ink-500">
                {{ loadError ?? "网络异常，请稍后重试" }}
            </p>
            <AppButton class="mt-4" variant="secondary" size="sm" @click="retry">
                重试
            </AppButton>
        </section>

        <!-- ================================================
             空态：一次提交都没有 → 直接给下一步，不渲染空表
        ================================================= -->
        <AppCard v-else-if="status === 'empty'" :padded="false">
            <EmptyState
                title="还没有学习记录"
                hint="完成第一个任务后，这里会有真实的能力与卡点分析"
                cta="去课程地图"
                icon="◎"
                @action="goLearn"
            />
        </AppCard>

        <!-- ================================================
             有数据
        ================================================= -->
        <template v-else>
            <!-- 指标区 -->
            <section class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <AppCard v-for="metric in metrics" :key="metric.key" dense>
                    <p class="text-xs font-medium text-ink-500">{{ metric.label }}</p>
                    <p class="mt-1 text-xl font-semibold text-ink-900 tabular-nums">
                        {{ metric.value }}
                    </p>
                    <p class="mt-1 text-[11px] leading-snug text-ink-500">{{ metric.sub }}</p>
                </AppCard>
            </section>

            <!-- 能力分布 -->
            <AppCard title="能力分布" :meta="tracks.length ? `${tracks.length} 条课程线` : undefined">
                <ul v-if="tracks.length" class="flex flex-col gap-4">
                    <li v-for="track in tracks" :key="track.track">
                        <div class="flex items-baseline justify-between gap-3">
                            <span class="text-sm font-medium text-ink-900">{{ track.label }}</span>
                            <span class="shrink-0 text-xs text-ink-500">
                                <template v-if="track.totalTasks === 0">暂无任务</template>
                                <template v-else>
                                    {{ track.passedTasks }} / {{ track.totalTasks }} 任务
                                </template>
                            </span>
                        </div>
                        <div class="mt-1.5 flex items-center gap-3">
                            <div
                                class="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised"
                                role="progressbar"
                                :aria-valuenow="trackPercent(track)"
                                aria-valuemin="0"
                                aria-valuemax="100"
                                :aria-label="`${track.label} 任务通过进度`"
                            >
                                <div
                                    class="h-full rounded-full transition-all"
                                    :class="trackBarClass(trackPercent(track))"
                                    :style="{ width: `${trackPercent(track)}%` }"
                                />
                            </div>
                            <span class="shrink-0 text-xs text-ink-500">
                                完成课程 {{ track.completedLessons }} / {{ track.lessons }}
                            </span>
                        </div>
                    </li>
                </ul>
                <p v-else class="text-sm text-ink-500">还没有分线数据。</p>
            </AppCard>

            <!-- 常见卡点 -->
            <AppCard
                title="常见卡点"
                :meta="errorPatterns.length ? `最多 ${ERROR_PATTERN_LIMIT} 条` : undefined"
            >
                <p v-if="errorPatterns.length === 0" class="py-1 text-sm text-ink-500">
                    还没有失败记录 —— 做完一两个任务再回来
                </p>
                <ul v-else class="divide-y divide-line">
                    <li
                        v-for="pattern in errorPatterns"
                        :key="`${pattern.lessonSlug}-${pattern.taskId}-${pattern.assertionId}`"
                    >
                        <button
                            type="button"
                            class="flex w-full flex-col gap-1 py-3 text-left transition-colors hover:bg-surface-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
                            @click="goLesson(pattern.lessonSlug)"
                        >
                            <span class="flex items-center justify-between gap-3">
                                <span class="text-sm font-medium text-ink-900">
                                    {{ pattern.lessonTitle }}
                                    <span class="text-ink-300" aria-hidden="true">›</span>
                                    {{ pattern.taskTitle }}
                                </span>
                                <StatusPill
                                    status="failed"
                                    :label="`失败 ${pattern.count} 次`"
                                />
                            </span>
                            <span class="text-xs text-ink-700">{{ pattern.title }}</span>
                            <span
                                v-if="pattern.lastActual"
                                class="line-clamp-2 break-words font-mono text-xs text-ink-500"
                            >
                                {{ pattern.lastActual }}
                            </span>
                        </button>
                    </li>
                </ul>
            </AppCard>

            <!-- 最近提交 -->
            <AppCard
                title="最近提交"
                :meta="recent.length ? `最近 ${recent.length} 条` : undefined"
                :padded="false"
            >
                <p v-if="recent.length === 0" class="px-5 py-4 text-sm text-ink-500">
                    还没有提交记录。
                </p>
                <table v-else class="w-full border-collapse text-sm">
                    <thead>
                        <tr class="border-b border-line text-left text-xs font-medium text-ink-500">
                            <th class="px-5 py-2 font-medium">时间</th>
                            <th class="px-2 py-2 font-medium">课程 › 任务</th>
                            <th class="px-2 py-2 font-medium">次序</th>
                            <th class="px-5 py-2 font-medium">状态</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="(item, index) in recent"
                            :key="`${item.lessonSlug}-${item.taskId}-${item.attemptNo}-${index}`"
                            class="border-b border-line last:border-b-0"
                        >
                            <td class="whitespace-nowrap px-5 py-2 font-mono text-xs text-ink-500">
                                {{ formatDateTime(item.createdAt) }}
                            </td>
                            <td class="px-2 py-2">
                                <button
                                    type="button"
                                    class="text-left text-ink-900 transition-colors hover:text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
                                    @click="goLesson(item.lessonSlug)"
                                >
                                    {{ item.lessonTitle }}
                                    <span class="text-ink-300" aria-hidden="true">›</span>
                                    {{ item.taskTitle }}
                                </button>
                            </td>
                            <td class="whitespace-nowrap px-2 py-2 text-xs text-ink-500">
                                第 {{ item.attemptNo }} 次
                            </td>
                            <td class="px-5 py-2">
                                <StatusPill :status="item.status" />
                            </td>
                        </tr>
                    </tbody>
                </table>
            </AppCard>
        </template>
    </div>
</template>