<template>
    <div class="min-h-screen bg-surface-page">
        <div class="mx-auto max-w-[1440px] px-4 py-6 lg:px-6">
            <!-- 顶部说明：这是个不判定的沙盒 -->
            <header class="mb-5">
                <div class="flex flex-wrap items-center gap-2">
                    <h1 class="text-lg font-semibold text-ink-900">实验室</h1>
                    <span
                        class="rounded-pill bg-surface-raised px-2 py-0.5 text-[11px] text-ink-500"
                    >
                        自由沙盒
                    </span>
                </div>
                <p class="mt-1.5 max-w-3xl text-sm leading-6 text-ink-500">
                    这里<strong class="font-medium text-ink-700">不判定</strong>、不记录成绩，也不落教学证据：
                    随手写 Python / Polars / DuckDB 跑一下，没有任务、没有断言。
                    想练有判定和提示的任务，去
                    <RouterLink to="/learn" class="text-brand-600 hover:text-brand-700">
                        课程里做题
                    </RouterLink>
                    。
                </p>
            </header>

            <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
                <main class="min-w-0 space-y-4">
                    <!-- 编辑器 + 操作条 + 输出（同一张卡片，执行链路从上到下） -->
                    <AppCard title="代码" :padded="false">
                        <template #actions>
                            <div class="flex items-center gap-2">
                                <label
                                    for="lab-language"
                                    class="text-[11px] text-ink-500"
                                >
                                    语言
                                </label>
                                <select
                                    id="lab-language"
                                    :value="language"
                                    class="h-8 rounded-control border border-line bg-surface-card px-2 text-xs text-ink-700 focus:outline-2 focus:outline-offset-2 focus:outline-brand-600"
                                >
                                    <option value="python">Python 3.12</option>
                                    <option value="sql" disabled>SQL（当前不支持）</option>
                                </select>
                            </div>
                        </template>

                        <!-- 带行号的 textarea：行号列与编辑区字号/行高一致，滚动同步 -->
                        <div class="p-3">
                            <div
                                class="flex overflow-hidden rounded-control border border-line bg-surface-raised"
                            >
                                <div
                                    ref="gutterRef"
                                    class="w-10 shrink-0 select-none overflow-hidden border-r border-line py-3 text-right"
                                    aria-hidden="true"
                                >
                                    <div
                                        v-for="line in lineNumbers"
                                        :key="line"
                                        class="pr-2 font-mono text-[13px] leading-6 text-ink-300"
                                    >
                                        {{ line }}
                                    </div>
                                </div>
                                <textarea
                                    ref="editorRef"
                                    v-model="sourceCode"
                                    rows="14"
                                    spellcheck="false"
                                    autocomplete="off"
                                    autocapitalize="off"
                                    autocorrect="off"
                                    aria-label="实验室代码编辑器"
                                    class="block w-full resize-none border-0 bg-surface-raised px-3 py-3 font-mono text-[13px] leading-6 text-ink-900 focus:outline-none"
                                    @scroll="syncEditorScroll"
                                    @keydown="onEditorKeydown"
                                ></textarea>
                            </div>
                        </div>

                        <div
                            class="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2.5"
                        >
                            <AppButton
                                variant="primary"
                                size="sm"
                                :loading="isRunning"
                                :disabled="!canRun"
                                @click="run"
                            >
                                运行
                            </AppButton>
                            <AppButton
                                variant="ghost"
                                size="sm"
                                :disabled="!canClear"
                                @click="clearOutput"
                            >
                                清空输出
                            </AppButton>
                            <span class="ml-auto text-[11px] text-ink-300">
                                Ctrl/⌘ + Enter 运行
                            </span>
                        </div>

                        <div class="border-t border-line p-3">
                            <CodeOutput
                                :stdout="runState.stdout"
                                :stderr="outputStderr"
                                :duration-ms="runState.durationMs"
                                :status="outputStatus"
                                min-height-class="min-h-[150px]"
                            />
                        </div>
                    </AppCard>
                </main>

                <!-- 侧栏：数据集参考（只描述，不给假路径） -->
                <aside class="space-y-4 lg:sticky lg:top-6">
                    <AppCard title="数据集参考">
                        <p class="text-xs leading-5 text-ink-500">
                            实验室<strong class="font-medium text-ink-700">不挂载</strong>
                            课程数据集：<code class="font-mono text-ink-700"
                                >data/ecommerce/*.csv</code
                            >
                            只有课程工作区能读到，在这里
                            <code class="font-mono text-ink-700">pl.read_csv()</code>
                            是读不到的。想跑例子请用下面的内联数据。
                        </p>

                        <ul class="mt-3 space-y-2">
                            <li
                                v-for="dataset in DATASETS"
                                :key="dataset.file"
                                class="rounded-control border border-line px-2.5 py-2"
                            >
                                <div class="flex items-baseline justify-between gap-2">
                                    <span class="font-mono text-xs text-ink-900">
                                        {{ dataset.file }}
                                    </span>
                                    <span class="shrink-0 text-[11px] text-ink-500">
                                        {{ dataset.shape }}
                                    </span>
                                </div>
                                <p class="mt-1 text-[11px] leading-4 text-ink-500">
                                    {{ dataset.note }}
                                </p>
                                <p class="mt-1 font-mono text-[11px] leading-4 text-ink-300">
                                    {{ dataset.columns }}
                                </p>
                            </li>
                        </ul>

                        <AppButton
                            variant="secondary"
                            size="sm"
                            block
                            class="mt-3"
                            @click="useInlineSample"
                        >
                            用内联数据试试
                        </AppButton>
                    </AppCard>

                    <p class="px-1 text-[11px] leading-5 text-ink-300">
                        输出只留在本页，刷新就没了；实验室不保存历史。
                    </p>
                </aside>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import { AppButton, AppCard, CodeOutput } from "@/components/ui";
import { ApiError } from "@/api/index";
import { executeCode } from "@/api/playground";
import { randomId } from "@/lib/uuid";
import type { ExecuteRequest, ExecuteResponse } from "@/types/api";

// =====================================================
// 实验室（/lab）：不判定的自由沙盒（设计稿 §15.2）
//
// 与练习/工作区的差别只有一条：这里没有任务、没有断言、不落教学证据。
// 执行链路复用 Playground 的 /playground/execute，因此 Runner 不可用时
// 后端 fail-closed 返回 503（status = "unavailable"），页面必须显示
// 「执行服务不可用，请稍后再试」，而不是把异常抛到控制台。
//
// 执行状态收敛在 runState 一个对象里（idle → running → done/error），
// 模板只读派生的 computed，不再散落一堆布尔。
// =====================================================

type LabLanguage = NonNullable<ExecuteRequest["language"]>;
type RunPhase = "idle" | "running" | "done" | "error";
type OutputStatus = "idle" | "running" | "success" | "error";

interface LabRunState {
    phase: RunPhase;
    stdout: string;
    stderr: string;
    durationMs: number | null;
    /**
     * 不是用户代码的错：服务不可用 / 超时 / 安全校验拒绝 / 网络失败。
     * 与 stderr 分开存，展示时再接在代码报错前面。
     */
    notice: string | null;
}

const UNAVAILABLE_MESSAGE = "执行服务不可用，请稍后再试";

function idleState(): LabRunState {
    return {
        phase: "idle",
        stdout: "",
        stderr: "",
        durationMs: null,
        notice: null,
    };
}

const DEFAULT_SAMPLE = `import polars as pl

df = pl.DataFrame(
    {
        "city": ["上海", "北京", "深圳", "成都"],
        "orders": [128, 96, 74, 52],
        "gmv": [18240.5, 12980.0, 9640.5, 6180.0],
    }
)

print(df)
print(df.filter(pl.col("orders") > 60).sort("gmv", descending=True))
`;

const INLINE_SAMPLE = `import polars as pl

# 实验室不挂载课程数据集，这里用内联数据造一张小表
sales = pl.DataFrame(
    {
        "region": ["华东", "华北", "华南", "西南", "华东", "华南"],
        "channel": ["app", "web", "app", "offline", "web", "app"],
        "orders": [42, 31, 27, 12, 18, 35],
        "amount": [5230.0, 3860.5, 2940.0, 1180.0, 2105.5, 4470.0],
    }
)

summary = sales.group_by("region").agg(
    pl.col("amount").sum().alias("total_amount"),
    pl.len().alias("row_count"),
).sort("total_amount", descending=True)

print(summary)
`;

interface DatasetReference {
    file: string;
    shape: string;
    note: string;
    columns: string;
}

/** 课程工作区里能读到的 ecommerce 数据集（此处只做参考，不提供路径）。 */
const DATASETS: readonly DatasetReference[] = [
    {
        file: "orders.csv",
        shape: "5000 行 · 11 列",
        note: "订单明细，一个订单一行；amount = 单价 × 数量 × 折扣。",
        columns:
            "order_id, customer_id, product_id, region, channel, quantity, unit_price, discount, amount, order_date, refunded",
    },
    {
        file: "customers.csv",
        shape: "800 行 · 6 列",
        note: "客户主数据，region 是所属大区。",
        columns: "customer_id, name, city, region, segment, signup_date",
    },
    {
        file: "products.csv",
        shape: "120 行 · 5 列",
        note: "商品主数据：单价、成本、上架日期。",
        columns: "product_id, category, unit_price, cost, launch_date",
    },
    {
        file: "orders_dirty.csv",
        shape: "1230 行 · 11 列",
        note: "前 1200 行 + 30 行整行重复；amount 有 N/A、order_date 混斜杠格式、region 带空格、channel 大小写不一致、discount/quantity 有 null。",
        columns: "字段同 orders.csv",
    },
];

const sourceCode = ref<string>(DEFAULT_SAMPLE);
/**
 * 后端 /playground/execute 目前只执行 Python（SandboxService 忽略 language），
 * 所以只开放 python；sql 选项保留但禁用，避免"选了 SQL 却按 Python 跑"。
 */
const language = ref<LabLanguage>("python");
const runState = ref<LabRunState>(idleState());

const editorRef = ref<HTMLTextAreaElement | null>(null);
const gutterRef = ref<HTMLElement | null>(null);

const lineCount = computed(() => Math.max(1, sourceCode.value.split("\n").length));
const lineNumbers = computed(() =>
    Array.from({ length: lineCount.value }, (_unused, index) => index + 1),
);

const isRunning = computed(() => runState.value.phase === "running");
const canRun = computed(() => !isRunning.value && sourceCode.value.trim().length > 0);
const canClear = computed(() => runState.value.phase !== "idle");

const outputStatus = computed<OutputStatus>(() => {
    switch (runState.value.phase) {
        case "running":
            return "running";
        case "done":
            return "success";
        case "error":
            return "error";
        default:
            return "idle";
    }
});

/** CodeOutput 只认 stderr：把非代码原因（服务不可用等）接在真正的 stderr 前面。 */
const outputStderr = computed(() => {
    const { notice, stderr } = runState.value;
    return [notice, stderr].filter((part): part is string => Boolean(part)).join("\n\n");
});

function syncEditorScroll(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    if (!target || !gutterRef.value) return;
    gutterRef.value.scrollTop = target.scrollTop;
}

function onEditorKeydown(event: KeyboardEvent): void {
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
    event.preventDefault();
    void run();
}

function failureNotice(response: ExecuteResponse): string | null {
    if (response.status === "timeout") {
        return "执行超时：代码跑得太久，缩短循环或减少数据量后再试。";
    }
    if (response.status === "rejected") {
        return "这段代码没有通过安全校验，未执行。";
    }
    return null;
}

function describeError(error: unknown): string {
    if (error instanceof ApiError && error.code === 503) return UNAVAILABLE_MESSAGE;
    if (error instanceof Error && error.message.trim()) return error.message.trim();
    return "执行失败，请稍后再试";
}

async function run(): Promise<void> {
    if (!canRun.value) return;
    runState.value = {
        phase: "running",
        stdout: "",
        stderr: "",
        durationMs: null,
        notice: null,
    };

    try {
        const response = await executeCode({
            code: sourceCode.value,
            language: language.value,
            requestId: randomId(),
            source: "playground",
        });

        // 后端 fail-closed：Runner 不可用或未获准执行，都不是代码问题。
        if (response.status === "unavailable") {
            runState.value = {
                phase: "error",
                stdout: "",
                stderr: "",
                durationMs: null,
                notice: UNAVAILABLE_MESSAGE,
            };
            return;
        }

        runState.value = {
            phase: response.status === "success" ? "done" : "error",
            stdout: response.stdout ?? "",
            stderr: response.stderr ?? "",
            durationMs: typeof response.executionTime === "number" ? response.executionTime : null,
            notice: failureNotice(response),
        };
    } catch (error) {
        // 503 走 HTTP 错误分支（StdResp code >= 400 → ApiError），这里兜住。
        runState.value = {
            phase: "error",
            stdout: "",
            stderr: "",
            durationMs: null,
            notice: describeError(error),
        };
    }
}

function clearOutput(): void {
    runState.value = idleState();
}

function useInlineSample(): void {
    sourceCode.value = INLINE_SAMPLE;
    clearOutput();
    void nextTick(() => editorRef.value?.focus());
}
</script>