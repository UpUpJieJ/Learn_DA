// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import AppButton from "../AppButton.vue";

describe("AppButton", () => {
    it("渲染插槽文案，默认是 primary 的实心按钮", () => {
        const wrapper = mount(AppButton, { slots: { default: "提交任务" } });

        expect(wrapper.text()).toBe("提交任务");
        expect(wrapper.attributes("type")).toBe("button");
        expect(wrapper.classes()).toContain("bg-brand-600");
        expect(wrapper.classes()).toContain("rounded-control");
    });

    it("点击触发 click 事件", async () => {
        const wrapper = mount(AppButton, { slots: { default: "运行" } });

        await wrapper.trigger("click");

        expect(wrapper.emitted("click")).toHaveLength(1);
    });

    it("loading 时禁用并标记 aria-busy，点击不触发", async () => {
        const wrapper = mount(AppButton, {
            props: { loading: true },
            slots: { default: "提交中" },
        });

        expect(wrapper.attributes("disabled")).toBeDefined();
        expect(wrapper.attributes("aria-busy")).toBe("true");
        expect(wrapper.find("svg.animate-spin").exists()).toBe(true);

        await wrapper.trigger("click");
        expect(wrapper.emitted("click")).toBeUndefined();
    });

    it("disabled 时点击不触发，且不显示 spinner", async () => {
        const wrapper = mount(AppButton, {
            props: { disabled: true },
            slots: { default: "不可用" },
        });

        expect(wrapper.find("svg.animate-spin").exists()).toBe(false);
        await wrapper.trigger("click");
        expect(wrapper.emitted("click")).toBeUndefined();
    });

    it("danger 把主按钮换成错误色（危险操作不靠文案提醒）", () => {
        const wrapper = mount(AppButton, {
            props: { danger: true },
            slots: { default: "删除" },
        });

        expect(wrapper.classes()).toContain("bg-err-600");
        expect(wrapper.classes()).not.toContain("bg-brand-600");
    });

    it("ghost + sm 只降视觉权重，不改变可点击性", async () => {
        const wrapper = mount(AppButton, {
            props: { variant: "ghost", size: "sm" },
            slots: { default: "要提示" },
        });

        expect(wrapper.classes()).toContain("h-8");
        await wrapper.trigger("click");
        expect(wrapper.emitted("click")).toHaveLength(1);
    });
});