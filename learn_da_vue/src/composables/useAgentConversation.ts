import { computed, ref } from "vue";
import { streamChatMessage, buildChatHistory, recordAgentFeedback } from "@/api/agent";
import type {
    AgentContext,
    AgentFeedbackValue,
    ChatMessage,
} from "@/types/api";

// =====================================================
// useAgentConversation：对话状态与请求生命周期（阶段 4 Task 2.4）
//
// 职责：
// - 消息列表、输入、loading、流式占位与停止（AbortSignal）；
// - 发送消息（payload = message + history + 上下文），带稳定 requestId
//   幂等（同一消息重试不重复调用模型）；
// - 结构化教学反馈与 interactionId 关联；
// - 用户反馈提交（upsert，不新增 ai_help）。
// 布局（embedded/floating）、快捷动作与上下文组装留在 AgentPanel。
// =====================================================

interface AgentConversationOptions {
    /** 当前上下文（代码/课程/attempt 等），由页面组装 */
    context: () => AgentContext;
    /** 消息更新后滚动到底部（页面 DOM 副作用，可省略） */
    scrollToBottom?: () => Promise<void> | void;
}

export function useAgentConversation(options: AgentConversationOptions) {
    const messages = ref<ChatMessage[]>([]);
    const inputText = ref("");
    const isLoading = ref(false);
    const copiedBlockId = ref<string | null>(null);
    const feedbackSubmittingId = ref<number | null>(null);
    const streamingMessageId = ref<string | null>(null);

    let abortController: AbortController | null = null;

    const messageCount = computed(() => messages.value.length);

    function formatAgentErrorMessage(message?: string) {
        if (!message?.trim()) {
            return "这次请求没有成功发出。\n\n建议你先重试一次，或者把问题缩小成“解释这段代码 / 为什么报错 / 下一步练什么”这样的单一步骤。";
        }
        return `这次请求失败了：${message}\n\n你可以重试一次，或者让我先围绕当前课程给一个更小的提示。`;
    }

    async function sendMessage(text?: string): Promise<void> {
        const content = (text ?? inputText.value).trim();
        if (!content || isLoading.value) return;

        inputText.value = "";

        // id 必须唯一：同毫秒内连续发送时 Date.now() 相同，会导致
        // buildChatHistory 误过滤历史、assistant 消息互相覆盖。
        const token = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

        const userMsg: ChatMessage = {
            id: `user-${token}`,
            role: "user",
            content,
            timestamp: Date.now(),
        };
        messages.value.push(userMsg);

        const assistantId = `assistant-${token}`;
        const assistantMsg: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: "",
            timestamp: Date.now(),
            isStreaming: true,
        };
        messages.value.push(assistantMsg);
        streamingMessageId.value = assistantId;

        isLoading.value = true;
        await options.scrollToBottom?.();

        const history = buildChatHistory(
            messages.value.filter((m) => !m.isStreaming),
            userMsg.id,
        );
        abortController = new AbortController();

        try {
            await streamChatMessage({
                payload: {
                    message: content,
                    history,
                    context: options.context(),
                },
                onToken: (token) => {
                    const msg = messages.value.find((m) => m.id === assistantId);
                    if (msg) {
                        msg.content += token;
                        void options.scrollToBottom?.();
                    }
                },
                onDone: (fullReply, feedback, interactionId) => {
                    const msg = messages.value.find((m) => m.id === assistantId);
                    if (msg) {
                        msg.content = fullReply || msg.content;
                        msg.isStreaming = false;
                        msg.teachingFeedback = feedback ?? null;
                        msg.interactionId = interactionId ?? null;
                    }
                    streamingMessageId.value = null;
                    isLoading.value = false;
                    void options.scrollToBottom?.();
                },
                onError: (error) => {
                    const msg = messages.value.find((m) => m.id === assistantId);
                    if (msg) {
                        msg.content = formatAgentErrorMessage(error.message);
                        msg.isStreaming = false;
                    }
                    streamingMessageId.value = null;
                    isLoading.value = false;
                    void options.scrollToBottom?.();
                },
                signal: abortController.signal,
            });
        } catch {
            const msg = messages.value.find((m) => m.id === assistantId);
            if (msg) {
                msg.content = formatAgentErrorMessage();
                msg.isStreaming = false;
            }
            streamingMessageId.value = null;
            isLoading.value = false;
        }
    }

    function stopStreaming() {
        abortController?.abort();
        abortController = null;

        const msg = messages.value.find((m) => m.id === streamingMessageId.value);
        if (msg) {
            msg.content = msg.content || "已中断";
            msg.isStreaming = false;
        }
        streamingMessageId.value = null;
        isLoading.value = false;
    }

    function clearMessages() {
        messages.value = [];
    }

    async function copyCode(code: string, blockId: string) {
        try {
            await navigator.clipboard.writeText(code);
            copiedBlockId.value = blockId;
            setTimeout(() => {
                if (copiedBlockId.value === blockId) copiedBlockId.value = null;
            }, 2000);
        } catch {
            // silent
        }
    }

    async function submitFeedback(msg: ChatMessage, feedback: AgentFeedbackValue) {
        if (!msg.interactionId || feedbackSubmittingId.value !== null) return;
        feedbackSubmittingId.value = msg.interactionId;
        try {
            await recordAgentFeedback(msg.interactionId, feedback);
            msg.feedback = feedback;
        } catch {
            // Feedback is optional and must not disrupt the learning conversation.
        } finally {
            feedbackSubmittingId.value = null;
        }
    }

    return {
        messages,
        inputText,
        isLoading,
        copiedBlockId,
        feedbackSubmittingId,
        streamingMessageId,
        messageCount,
        sendMessage,
        stopStreaming,
        clearMessages,
        copyCode,
        submitFeedback,
        formatAgentErrorMessage,
    };
}
