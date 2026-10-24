import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import type { AgentContext } from "@/types/api";
import type { AssertionResult } from "@/api/workspace";

vi.mock("@/api/agent", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/api/agent")>();
    return {
        ...actual,
        sendChatMessage: vi.fn(),
        recordAgentFeedback: vi.fn(),
    };
});

import { sendChatMessage } from "@/api/agent";
import WorkspaceCoach from "@/components/workspace/WorkspaceCoach.vue";

const mockedSend = vi.mocked(sendChatMessage);

function assertion(overrides: Partial<AssertionResult> = {}): AssertionResult {
    return {
        id: "t1-schema",
        type: "schema",
        title: "聚合结果包含三列",
        status: "failed",
        actual: "缺少列 ['orders']",
        detail: null,
        durationMs: 3,
        ...overrides,
    };
}

const CONTEXT: AgentContext = {
    currentLesson: "polars-groupby",
    currentTask: "t1",
    cellId: "c2",
    currentCode: "print(1)",
};

function mountCoach(props: Record<string, unknown> = {}) {
    return mount(WorkspaceCoach, {
        props: { context: CONTEXT, ...props },
    });
}

describe("WorkspaceCoach", () => {
    beforeEach(() => {
        mockedSend.mockReset();
        mockedSend.mockImplementation(async ({ onDone }) => {
            onDone?.("因为 orders 列没生成", null, 11);
        });
    });

    it("hides the ambient card when every assertion passed", () => {
        const wrapper = mountCoach({
            assertions: [assertion({ status: "passed", actual: null })],
        });
        expect(wrapper.text()).not.toContain("我看到了什么");
    });

    it("renders failed assertions with their server-reported actual value", () => {
        const wrapper = mountCoach({
            assertions: [
                assertion({ status: "passed", actual: null, id: "t1-rows" }),
                assertion(),
            ],
        });
        const text = wrapper.text();
        expect(text).toContain("我看到了什么");
        expect(text).toContain("聚合结果包含三列");
        expect(text).toContain("缺少列 ['orders']");
        // 通过的那条不该出现在证据卡里
        expect(text).not.toContain("t1-rows");
    });

    it("treats error/timeout/skipped as not-passed for the ambient card", () => {
        const wrapper = mountCoach({
            assertions: [
                assertion({ id: "a", status: "error", actual: "KeyError: 'x'" }),
                assertion({ id: "b", status: "skipped", actual: null, detail: "未求值" }),
            ],
        });
        const text = wrapper.text();
        expect(text).toContain("KeyError: 'x'");
        expect(text).toContain("未求值");
    });

    it("asks about the failure by naming the failed assertions", async () => {
        const wrapper = mountCoach({ assertions: [assertion()] });
        const button = wrapper
            .findAll("button")
            .find((item) => item.text().includes("这条断言为什么不通过"));
        expect(button).toBeTruthy();
        await button!.trigger("click");

        expect(mockedSend).toHaveBeenCalledTimes(1);
        const payload = mockedSend.mock.calls[0]![0].payload;
        expect(payload.message).toContain("聚合结果包含三列");
        expect(payload.message).toContain("不要直接给我完整代码");
    });

    it("sends the typed question with the workspace context", async () => {
        const wrapper = mountCoach();
        const textarea = wrapper.find("textarea");
        await textarea.setValue("为什么我的分组结果是空的？");
        const send = wrapper
            .findAll("button")
            .find((item) => item.text().includes("发送"));
        await send!.trigger("click");

        const payload = mockedSend.mock.calls[0]![0].payload;
        expect(payload.message).toBe("为什么我的分组结果是空的？");
        expect(payload.context).toEqual(CONTEXT);
    });

    it("offers concrete suggestions instead of an empty box", () => {
        const wrapper = mountCoach({ assertions: [assertion()] });
        const text = wrapper.text();
        expect(text).toContain("这条断言为什么不通过？");
        expect(text).toContain("下一步该练什么？");
    });

    it("shows the thinking placeholder while waiting for the reply", async () => {
        let release: (() => void) | null = null;
        mockedSend.mockImplementation(
            ({ onDone }) =>
                new Promise<void>((resolve) => {
                    release = () => {
                        onDone?.("完整回答", null, 3);
                        resolve();
                    };
                }),
        );

        const wrapper = mountCoach();
        const pending = wrapper
            .findAll("button")
            .find((item) => item.text().includes("下一步该练什么？"))!
            .trigger("click");
        await vi.waitFor(() => expect(wrapper.text()).toContain("正在思考…"));

        release!();
        await pending;
        await vi.waitFor(() => expect(wrapper.text()).toContain("完整回答"));
        expect(wrapper.text()).not.toContain("正在思考…");
    });

    it("renders the teaching hint level next to the answer", async () => {
        mockedSend.mockImplementation(async ({ onDone }) => {
            onDone?.(
                "先看 region 列",
                {
                    state: "verification_failed",
                    attemptId: 9,
                    evidenceSummary: "断言未通过",
                    diagnosis: "列缺失",
                    hintLevel: 2,
                    nextAction: "retry_exercise",
                },
                12,
            );
        });

        const wrapper = mountCoach();
        await wrapper
            .findAll("button")
            .find((item) => item.text().includes("下一步该练什么？"))!
            .trigger("click");
        await vi.waitFor(() => expect(wrapper.text()).toContain("先看 region 列"));
        expect(wrapper.text()).toContain("提示层级 L2");
        expect(wrapper.text()).toContain("断言未通过");
    });

    it("surfaces request errors inside the panel", async () => {
        mockedSend.mockImplementation(async ({ onError }) => {
            onError?.(new Error("网络断了"));
        });
        const wrapper = mountCoach();
        await wrapper
            .findAll("button")
            .find((item) => item.text().includes("下一步该练什么？"))!
            .trigger("click");
        await vi.waitFor(() => expect(wrapper.text()).toContain("网络断了"));
    });

    it("sends on Ctrl+Enter", async () => {
        const wrapper = mountCoach();
        const textarea = wrapper.find("textarea");
        await textarea.setValue("你好");
        await textarea.trigger("keydown", { key: "Enter", ctrlKey: true });
        await vi.waitFor(() => expect(mockedSend).toHaveBeenCalledTimes(1));
    });

    it("clears the conversation when the focused cell changes", async () => {
        const wrapper = mountCoach();
        await wrapper
            .findAll("button")
            .find((item) => item.text().includes("下一步该练什么？"))!
            .trigger("click");
        await vi.waitFor(() => expect(wrapper.text()).toContain("因为 orders 列没生成"));

        await wrapper.setProps({ context: { ...CONTEXT, cellId: "c3" } });
        await vi.waitFor(() => expect(wrapper.text()).not.toContain("因为 orders 列没生成"));
    });
});
