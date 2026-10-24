<template>
    <div class="space-y-4">
        <!-- ambient：失败证据卡。数据直接来自服务端返回的断言结果，
             不经过模型，因此永远与判定一致、零请求零成本。 -->
        <AppCard v-if="failedAssertions.length" dense>
            <div class="flex items-start justify-between gap-2">
                <h2 class="text-xs font-semibold uppercase tracking-wide text-ink-300">
                    我看到了什么
                </h2>
                <StatusPill status="failed" size="sm" />
            </div>
            <p class="mt-2 text-xs leading-5 text-ink-500">
                这是最近一次提交里没通过的断言（服务端判定，不是 AI 推测）。
            </p>
            <ul class="mt-2 space-y-2">
                <li
                    v-for="item in failedAssertions"
                    :key="item.id"
                    class="rounded-control border border-err-500/30 bg-err-50 px-2 py-1.5"
                >
                    <p class="text-xs font-medium text-err-700">
                        ✗ {{ item.title || item.id }}
                    </p>
                    <p
                        v-if="item.actual || item.detail"
                        class="mt-0.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-4 text-ink-500"
                    >
                        {{ item.actual || item.detail }}
                    </p>
                </li>
            </ul>
            <template #footer>
                <AppButton
                    variant="ghost"
                    size="sm"
                    label="这条断言为什么不通过"
                    :disabled="isLoading"
                    @click="askAboutFailure"
                >
                    这条断言为什么不通过
                </AppButton>
            </template>
        </AppCard>

        <!-- chat：自由问答 -->
        <AppCard dense>
            <div class="flex items-center justify-between gap-2">
                <h2 class="text-xs font-semibold uppercase tracking-wide text-ink-300">
                    AI 助手
                </h2>
                <button
                    v-if="messages.length"
                    type="button"
                    class="text-[11px] text-ink-300 hover:text-ink-700"
                    @click="clearMessages"
                >
                    清空
                </button>
            </div>

            <div
                v-if="messages.length"
                ref="listRef"
                class="mt-2 max-h-[320px] space-y-3 overflow-y-auto pr-1"
            >
                <div
                    v-for="msg in messages"
                    :key="msg.id"
                    :class="msg.role === 'user' ? 'text-right' : ''"
                >
                    <div
                        class="inline-block max-w-full rounded-card px-2.5 py-1.5 text-left text-xs leading-5"
                        :class="
                            msg.role === 'user'
                                ? 'bg-brand-50 text-ink-700'
                                : 'bg-surface-raised text-ink-700'
                        "
                    >
                        <p
                            v-if="msg.role === 'assistant' && msg.isStreaming && !msg.content"
                            class="text-ink-300"
                        >
                            正在思考…
                        </p>
                        <div
                            v-else
                            class="whitespace-pre-wrap break-words"
                            v-html="renderMessage(msg.content)"
                        ></div>
                    </div>
                    <p
                        v-if="msg.role === 'assistant' && msg.teachingFeedback"
                        class="mt-1 text-[11px] text-ink-300"
                    >
                        提示层级 L{{ msg.teachingFeedback.hintLevel }} ·
                        {{ stateLabel(msg.teachingFeedback.state) }}
                    </p>
                </div>
            </div>

            <!-- 空态：给可点的具体问题，别让学习者自己想问什么 -->
            <div v-else class="mt-2 space-y-1.5">
                <p class="text-xs leading-5 text-ink-500">
                    {{ emptyHint }}
                </p>
                <button
                    v-for="suggestion in suggestions"
                    :key="suggestion"
                    type="button"
                    class="block w-full rounded-control border border-line px-2 py-1.5 text-left text-xs text-ink-700 hover:bg-surface-raised disabled:opacity-60"
                    :disabled="isLoading"
                    @click="sendMessage(suggestion)"
                >
                    {{ suggestion }}
                </button>
            </div>

            <div class="mt-2 flex items-end gap-1.5">
                <textarea
                    v-model="inputText"
                    rows="2"
                    :placeholder="isLoading ? '正在回答…' : '问点什么（Ctrl/⌘ + Enter 发送）'"
                    :disabled="isLoading"
                    class="min-w-0 flex-1 resize-none rounded-control border border-line bg-surface-card px-2 py-1.5 text-xs text-ink-700 outline-none focus:border-brand-500 disabled:opacity-60"
                    @keydown="onKeydown"
                ></textarea>
                <AppButton
                    size="sm"
                    label="发送"
                    :loading="isLoading"
                    :disabled="!inputText.trim()"
                    @click="submit()"
                >
                    发送
                </AppButton>
            </div>
            <p v-if="error" class="mt-1.5 text-[11px] leading-4 text-err-600">
                {{ error }}
            </p>
        </AppCard>
    </div>
</template>

<script setup lang="ts">
// =====================================================
// 工作区右栏 AI 助手（改版 E1）
//
// 分档依据设计稿 §8.2，但 E1 只做两档：
//   ambient  失败证据卡 —— 纯前端渲染 store 里的断言结果，0 请求 0 token；
//   chat     自由问答   —— 走 /agent/chat，服务端证据 + 提示层级由后端决定。
// ladder（按层给提示）需要 hint_usages 表与专用端点，留 E2。
//
// 刻意不做：让模型复述断言结果（ambient 已经直接显示，复述只会更慢更易错）、
// 让模型改代码（用户已定「只解释不改代码」）、
// 让模型规划"下一步练什么"（任务顺序由服务端任务列表权威给出，模型不该另出主意）。
// =====================================================
import { computed, nextTick, ref, watch } from "vue";
import { AppButton, AppCard, StatusPill } from "@/components/ui";
import { useAgentConversation } from "@/composables/useAgentConversation";
import { renderMarkdown } from "@/lib/markdown";
import type { AssertionResult } from "@/api/workspace";
import type { AgentContext, TeachingState } from "@/types/api";

const props = defineProps<{
    /** 由工作区页面组装：课程/任务/聚焦格/编辑器代码/最近执行 */
    context: AgentContext;
    /** 最近一次提交的断言结果（服务端原样返回） */
    assertions?: AssertionResult[];
    /** 当前任务是否已有提交记录（决定空态问法） */
    hasSubmission?: boolean;
}>();

const STATE_LABELS: Record<TeachingState, string> = {
    execution_failed: "代码没跑通",
    verification_failed: "断言未通过",
    passed_unconfirmed: "任务已通过",
    unverifiable: "结果不可验证",
    no_evidence: "暂无证据",
};

function stateLabel(state: TeachingState): string {
    return STATE_LABELS[state] ?? state;
}

const failedAssertions = computed(() =>
    (props.assertions ?? []).filter((item) => item.status !== "passed"),
);

const suggestions = computed(() => {
    const list: string[] = [];
    if (failedAssertions.value.length) {
        list.push("这条断言为什么不通过？");
    }
    list.push("这一步要用到哪些 API？");
    return list;
});

/** 空态引导语：没提交过就先说清"我为什么还看不到你的结果"。 */
const emptyHint = computed(() =>
    props.hasSubmission
        ? "我会看你最近一次提交的真实断言结果来回答，不会凭空猜你写了什么。"
        : "我还没有你的提交记录。先跑一遍当前格、提交任务，我就能对着真实断言结果回答。",
);

const listRef = ref<HTMLElement | null>(null);

const {
    messages,
    inputText,
    isLoading,
    sendMessage,
    clearMessages,
    formatAgentErrorMessage,
} = useAgentConversation({
    context: () => props.context,
    scrollToBottom: async () => {
        await nextTick();
        const element = listRef.value;
        if (element) element.scrollTop = element.scrollHeight;
    },
});

const error = ref<string | null>(null);

/** 发送并把错误暴露在面板内（不弹 toast，避免抢走代码区注意力）。 */
async function submit(text?: string): Promise<void> {
    error.value = null;
    try {
        await sendMessage(text);
        const last = messages.value[messages.value.length - 1];
        if (last?.role === "assistant" && !last.content) {
            error.value = "这次没有拿到回答，稍后重试。";
        }
    } catch (caught) {
        error.value = formatAgentErrorMessage(
            caught instanceof Error ? caught.message : undefined,
        );
    }
}

function askAboutFailure(): void {
    const titles = failedAssertions.value
        .map((item) => item.title || item.id)
        .slice(0, 3)
        .join("、");
    void submit(
        titles
            ? `我这次提交里「${titles}」没通过，请结合实际值解释原因，但不要直接给我完整代码。`
            : "我这次提交没通过，请结合实际值解释原因，但不要直接给我完整代码。",
    );
}

function renderMessage(content: string): string {
    return content ? renderMarkdown(content) : "";
}

function onKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void submit();
    }
}

// 聚焦格或任务变了，旧对话会误导模型；清掉并让空态重新给建议。
watch(
    () => [props.context.currentTask, props.context.cellId],
    () => {
        if (messages.value.length) clearMessages();
        error.value = null;
    },
);
</script>
