// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import StatusPill from "../StatusPill.vue";
import { countCompleted, taskStatusMeta } from "../status";

describe("taskStatusMeta", () => {
    it("六种状态都有文案，且只有通过算完成", () => {
        const kinds = ["todo", "in_progress", "needs_review", "passed", "failed", "skipped"] as const;

        expect(kinds.map((kind) => taskStatusMeta(kind).label)).toEqual([
            "未开始",
            "进行中",
            "需复核",
            "已通过",
            "未通过",
            "已跳过",
        ]);
        expect(kinds.filter((kind) => taskStatusMeta(kind).completed)).toEqual(["passed"]);
    });

    it("未知状态降级为未开始（后端加了前端没跟上的状态不会白屏）", () => {
        expect(taskStatusMeta("some_future_state").label).toBe("未开始");
    });

    it("countCompleted 只统计 passed", () => {
        expect(countCompleted(["passed", "failed", "passed", "todo"])).toEqual({ done: 2, total: 4 });
        expect(countCompleted([])).toEqual({ done: 0, total: 0 });
    });
});

describe("StatusPill", () => {
    it("按状态给出语义色，不再是裸 slate/emerald", () => {
        const passed = mount(StatusPill, { props: { status: "passed" } });
        expect(passed.text()).toContain("已通过");
        expect(passed.classes().join(" ")).toContain("bg-ok-50");

        const failed = mount(StatusPill, { props: { status: "failed" } });
        expect(failed.text()).toContain("未通过");
        expect(failed.classes().join(" ")).toContain("bg-err-50");
    });

    it("需复核用警示色（避免学习者以为已经过了）", () => {
        const wrapper = mount(StatusPill, { props: { status: "needs_review" } });

        expect(wrapper.text()).toContain("需复核");
        expect(wrapper.classes().join(" ")).toContain("bg-warn-50");
    });

    it("支持覆盖文案，用于课程级汇总（如 3/3 已通过）", () => {
        const wrapper = mount(StatusPill, { props: { status: "passed", label: "3/3 已通过" } });

        expect(wrapper.text()).toContain("3/3 已通过");
    });

    it("showDot=false 时不渲染圆点", () => {
        const wrapper = mount(StatusPill, { props: { status: "todo", showDot: false } });

        expect(wrapper.find("span[aria-hidden='true']").exists()).toBe(false);
    });
});