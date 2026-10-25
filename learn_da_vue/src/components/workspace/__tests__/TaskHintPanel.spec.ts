// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import TaskHintPanel from "../TaskHintPanel.vue";
import type { HintResponse, WorkspaceTask } from "@/api/workspace";

function task(overrides: Partial<WorkspaceTask> = {}): WorkspaceTask {
    return {
        taskId: "t1",
        title: "按区域聚合",
        cellId: "c2",
        objective: "按 region 汇总 revenue 与 orders，并按 revenue 降序",
        status: "failed",
        hintLevel: 1,
        hintsUsed: 0,
        hintMaxLevel: 3,
        ...overrides,
    };
}

function hint(overrides: Partial<HintResponse> = {}): HintResponse {
    return {
        taskId: "t1",
        level: 1,
        maxLevel: 3,
        hintsUsed: 1,
        content: "先对照 columns 和 shape",
        hasNext: true,
        ...overrides,
    };
}

function mountPanel(props: Record<string, unknown> = {}) {
    return mount(TaskHintPanel, {
        props: { task: task(), hints: [], loading: false, ...props },
    });
}

describe("TaskHintPanel", () => {
    it("还没用过提示时显示可要几层，按钮文案是「给点提示」", () => {
        const wrapper = mountPanel();

        expect(wrapper.text()).toContain("可要 3 层");
        expect(wrapper.text()).toContain("给点提示");
        expect(wrapper.text()).toContain("不会直接给整格答案");
    });

    it("点按钮把 taskId 抛给父组件（层级由服务端决定，前端不传）", async () => {
        const wrapper = mountPanel();
        await wrapper.find("button").trigger("click");

        expect(wrapper.emitted("request")).toEqual([["t1"]]);
    });

    it("loading 时按钮禁用，避免连点要出两层", () => {
        const wrapper = mountPanel({ loading: true });
        const button = wrapper.find("button");

        expect(button.attributes("disabled")).toBeDefined();
        expect(button.attributes("aria-busy")).toBe("true");
    });

    it("已用过的提示按层渲染，带 L1/L2 标记与正文", () => {
        const wrapper = mountPanel({
            task: task({ hintsUsed: 2 }),
            hints: [
                hint({ level: 1, content: "先对照 columns" }),
                hint({ level: 2, content: "服务端实际值：缺少列", hasNext: false }),
            ],
        });

        expect(wrapper.text()).toContain("已用 2/3 层");
        expect(wrapper.text()).toContain("L1");
        expect(wrapper.text()).toContain("L2");
        expect(wrapper.text()).toContain("先对照 columns");
        expect(wrapper.text()).toContain("最后一层");
    });

    it("刷新后本地没有提示正文时，不假装有内容，只提示可以继续要", () => {
        const wrapper = mountPanel({ task: task({ hintsUsed: 1 }), hints: [] });

        expect(wrapper.findAll("li")).toHaveLength(0);
        expect(wrapper.text()).toContain("刷新后不再重复显示");
    });

    it("按钮文案随已用层数变化", () => {
        expect(mountPanel().text()).toContain("给点提示");
        expect(mountPanel({ task: task({ hintsUsed: 1 }) }).text()).toContain("再要一层提示");
    });

    it("正文渲染 Markdown（列表会变成 li）", () => {
        const wrapper = mountPanel({
            hints: [hint({ content: "- 第一点\n- 第二点" })],
        });

        expect(wrapper.html()).toContain("<li>");
    });
});
