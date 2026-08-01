import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AgentContext, TeachingFeedback } from "@/types/api";

vi.mock("@/api/agent", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/api/agent")>();
    return {
        ...actual,
        streamChatMessage: vi.fn(),
        recordAgentFeedback: vi.fn(),
    };
});

import { streamChatMessage, recordAgentFeedback } from "@/api/agent";
import { useAgentConversation } from "@/composables/useAgentConversation";

const mockedStream = vi.mocked(streamChatMessage);
const mockedFeedback = vi.mocked(recordAgentFeedback);

const CONTEXT: AgentContext = {
    currentLesson: "polars-basics",
    currentCode: "print(1)",
};

const FEEDBACK: TeachingFeedback = {
    state: "execution_failed",
    attemptId: 7,
    evidenceSummary: "代码执行失败",
    diagnosis: "语法错误",
    hintLevel: 1,
    nextAction: "retry_exercise",
};

function captureOnDone() {
    const call = mockedStream.mock.calls.at(-1)!;
    return call[0];
}

describe("useAgentConversation", () => {
    beforeEach(() => {
        mockedStream.mockReset();
        mockedFeedback.mockReset();
        mockedFeedback.mockResolvedValue({ recorded: true, interactionId: 1 });
    });

    it("sends message with history and context, then renders reply", async () => {
        const conversation = useAgentConversation({
            context: () => CONTEXT,
        });

        conversation.inputText.value = "帮我看看";
        mockedStream.mockImplementation(async ({ onDone }) => {
            onDone?.("修复建议", null, null);
        });

        await conversation.sendMessage();

        expect(conversation.messages.value).toHaveLength(2);
        const assistant = conversation.messages.value[1];
        expect(assistant.content).toBe("修复建议");
        expect(assistant.isStreaming).toBe(false);

        const opts = captureOnDone();
        expect(opts.payload.message).toBe("帮我看看");
        expect(opts.payload.context).toEqual(CONTEXT);
        expect(opts.payload.history).toEqual([]);
    });

    it("excludes current user message from history", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        mockedStream.mockImplementation(async ({ onDone }) => onDone?.("a", null, null));

        await conversation.sendMessage("第一问");
        await conversation.sendMessage("第二问");

        const opts = captureOnDone();
        // 历史只包含第一轮对话（user + assistant），不含当前"第二问"
        expect(opts.payload.history).toHaveLength(2);
        expect(opts.payload.history[0]?.content).toBe("第一问");
        expect(opts.payload.history[1]?.content).toBe("a");
    });

    it("attaches teachingFeedback and interactionId on done", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        mockedStream.mockImplementation(async ({ onDone }) => {
            onDone?.("回答", FEEDBACK, 42);
        });

        await conversation.sendMessage("为什么报错");

        const assistant = conversation.messages.value[1];
        expect(assistant.teachingFeedback?.state).toBe("execution_failed");
        expect(assistant.interactionId).toBe(42);
    });

    it("stopStreaming aborts the request and marks message as interrupted", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        let capturedSignal: AbortSignal | undefined;
        mockedStream.mockImplementation(async ({ onDone, signal }) => {
            capturedSignal = signal;
            // 模拟挂起请求：仅在 abort 时结束（与 axios 行为一致）
            await new Promise<void>((resolve) => {
                signal?.addEventListener("abort", () => resolve());
            });
        });

        const pending = conversation.sendMessage("hi");
        await vi.waitFor(() => expect(conversation.isLoading.value).toBe(true));

        conversation.stopStreaming();
        expect(capturedSignal?.aborted).toBe(true);
        expect(conversation.isLoading.value).toBe(false);
        const assistant = conversation.messages.value[1];
        expect(assistant.content).toBe("已中断");
        expect(assistant.isStreaming).toBe(false);

        // 终止未完成的 promise，避免悬挂
        await pending.catch(() => {});
    });

    it("submitFeedback posts to recordAgentFeedback and marks message", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        mockedStream.mockImplementation(async ({ onDone }) => {
            onDone?.("回答", FEEDBACK, 7);
        });
        await conversation.sendMessage("hi");

        const assistant = conversation.messages.value[1];
        await conversation.submitFeedback(assistant, "helpful");

        expect(mockedFeedback).toHaveBeenCalledWith(7, "helpful");
        expect(assistant.feedback).toBe("helpful");
    });

    it("submitFeedback skips when no interactionId", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        mockedStream.mockImplementation(async ({ onDone }) => onDone?.("回答", null, null));
        await conversation.sendMessage("hi");

        const assistant = conversation.messages.value[1];
        await conversation.submitFeedback(assistant, "not_helpful");

        expect(mockedFeedback).not.toHaveBeenCalled();
    });

    it("clearMessages resets the conversation", async () => {
        const conversation = useAgentConversation({ context: () => CONTEXT });
        mockedStream.mockImplementation(async ({ onDone }) => onDone?.("回答", null, null));
        await conversation.sendMessage("hi");
        expect(conversation.messages.value).toHaveLength(2);

        conversation.clearMessages();
        expect(conversation.messages.value).toHaveLength(0);
    });
});
