// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import ConfirmDialog from "../ConfirmDialog.vue";
import EmptyState from "../EmptyState.vue";

afterEach(() => {
    document.body.innerHTML = "";
});

describe("ConfirmDialog", () => {
    it("open=false 不渲染任何内容", () => {
        mount(ConfirmDialog, {
            props: { open: false, title: "确认？", confirmText: "删除" },
        });

        expect(document.body.querySelector("[role='dialog']")).toBeNull();
    });

    it("open=true 渲染标题、说明与两个动作", () => {
        mount(ConfirmDialog, {
            props: {
                open: true,
                title: "删除这个格？",
                description: "删除后需要重新添加。",
                confirmText: "删除",
            },
        });

        const dialog = document.body.querySelector("[role='dialog']");
        expect(dialog?.textContent).toContain("删除这个格？");
        expect(dialog?.textContent).toContain("删除后需要重新添加。");
        expect(dialog?.textContent).toContain("取消");
        expect(dialog?.textContent).toContain("删除");
    });

    it("ESC 触发 cancel（禁用 window.confirm 之后的键盘可达路径）", async () => {
        const wrapper = mount(ConfirmDialog, {
            attachTo: document.body,
            props: { open: true, title: "确认？", confirmText: "确定" },
        });

        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        await wrapper.vm.$nextTick();

        expect(wrapper.emitted("cancel")).toHaveLength(1);
        expect(wrapper.emitted("confirm")).toBeUndefined();
    });

    it("点遮罩取消，点确认按钮才 confirm", async () => {
        const wrapper = mount(ConfirmDialog, {
            attachTo: document.body,
            props: { open: true, title: "确认？", confirmText: "确定" },
        });

        const backdrop = document.body.querySelector(".fixed.inset-0") as HTMLElement;
        backdrop.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await wrapper.vm.$nextTick();
        expect(wrapper.emitted("cancel")).toHaveLength(1);

        const confirmButton = Array.from(document.body.querySelectorAll("button")).find((btn) =>
            btn.textContent?.includes("确定"),
        ) as HTMLButtonElement;
        confirmButton.click();
        await wrapper.vm.$nextTick();
        expect(wrapper.emitted("confirm")).toHaveLength(1);
    });
});

describe("EmptyState", () => {
    it("渲染标题、提示，并给出可执行动作", async () => {
        const wrapper = mount(EmptyState, {
            props: { title: "还没有学习记录", hint: "完成第一个任务就会出现在这里", cta: "去选一门课" },
        });

        expect(wrapper.text()).toContain("还没有学习记录");
        expect(wrapper.text()).toContain("完成第一个任务就会出现在这里");
        expect(wrapper.text()).toContain("去选一门课");

        await wrapper.find("button").trigger("click");
        expect(wrapper.emitted("action")).toHaveLength(1);
    });

    it("hint 可省略，但 cta 仍然渲染（空态不允许只有一句话）", () => {
        const wrapper = mount(EmptyState, {
            props: { title: "暂无数据", cta: "重试" },
        });

        expect(wrapper.find("button").text()).toBe("重试");
    });
});