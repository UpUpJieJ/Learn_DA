// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import { ApiError } from "@/api/index";
import Lab from "../Lab.vue";
import type { ExecuteResponse } from "@/types/api";

// 只隔离网络层：Lab 页面本身（状态机、快捷键、行号）必须按真实实现跑。
const { executeCode } = vi.hoisted(() => ({ executeCode: vi.fn() }));

vi.mock("@/api/playground", () => ({ executeCode }));

function successResponse(overrides: Partial<ExecuteResponse> = {}): ExecuteResponse {
    return {
        status: "success",
        stdout: "shape: (4, 3)\n",
        stderr: "",
        executionTime: 42,
        resultType: "text",
        dataframe: null,
        ...overrides,
    };
}

function mountLab(): VueWrapper {
    return mount(Lab, {
        global: { stubs: { RouterLink: RouterLinkStub } },
    });
}

function buttonByText(wrapper: VueWrapper, label: string) {
    const button = wrapper.findAll("button").find((item) => item.text() === label);
    if (!button) throw new Error(`找不到按钮：${label}`);
    return button;
}

describe("Lab 实验室页面", () => {
    beforeEach(() => {
        executeCode.mockReset();
    });

    it("渲染标题、不判定说明和带行号的编辑器", () => {
        const wrapper = mountLab();

        expect(wrapper.text()).toContain("实验室");
        expect(wrapper.text()).toContain("不判定");
        expect(wrapper.text()).toContain("课程里做题");

        const textarea = wrapper.get("textarea");
        expect(textarea.element.value).toContain("import polars as pl");
        // 行号列：默认示例有 N 行，就有 N 个行号格子
        const gutter = wrapper.get("div[aria-hidden='true']");
        expect(gutter.element.children).toHaveLength(
            textarea.element.value.split("\n").length,
        );
        expect(gutter.text()).toContain("1");
    });

    it("点运行调用 executeCode 并渲染 stdout 与耗时", async () => {
        executeCode.mockResolvedValue(successResponse());
        const wrapper = mountLab();

        await wrapper.get("textarea").setValue('print("hi")');
        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();

        expect(executeCode).toHaveBeenCalledTimes(1);
        const payload = executeCode.mock.calls[0]?.[0] as Record<string, unknown>;
        expect(payload.code).toBe('print("hi")');
        expect(payload.language).toBe("python");
        expect(payload.source).toBe("playground");
        expect(typeof payload.requestId).toBe("string");

        expect(wrapper.text()).toContain("shape: (4, 3)");
        expect(wrapper.text()).toContain("42ms");
        expect(wrapper.text()).toContain("成功");
    });

    it("503（HTTP 错误分支）显示服务不可用提示，不崩", async () => {
        executeCode.mockRejectedValue(new ApiError("Execution service unavailable", 503));
        const wrapper = mountLab();

        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();

        expect(wrapper.text()).toContain("执行服务不可用，请稍后再试");
        expect(wrapper.text()).toContain("失败");
    });

    it("后端返回 status=unavailable 时同样显示服务不可用提示", async () => {
        executeCode.mockResolvedValue(
            successResponse({
                status: "unavailable",
                stdout: "",
                stderr: "",
                executionTime: 0,
                resultType: "error",
            }),
        );
        const wrapper = mountLab();

        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();

        expect(wrapper.text()).toContain("执行服务不可用，请稍后再试");
    });

    it("Ctrl+Enter 触发放运行，单独 Enter 不触发", async () => {
        executeCode.mockResolvedValue(successResponse());
        const wrapper = mountLab();
        const textarea = wrapper.get("textarea");

        await textarea.trigger("keydown", { key: "Enter" });
        await flushPromises();
        expect(executeCode).not.toHaveBeenCalled();

        await textarea.trigger("keydown", { key: "Enter", ctrlKey: true });
        await flushPromises();
        expect(executeCode).toHaveBeenCalledTimes(1);

        await textarea.trigger("keydown", { key: "Enter", metaKey: true });
        await flushPromises();
        expect(executeCode).toHaveBeenCalledTimes(2);
    });

    it("运行中按钮进入 loading 且不可重复提交", async () => {
        let resolveRun: (value: ExecuteResponse) => void = () => {};
        executeCode.mockImplementation(
            () =>
                new Promise<ExecuteResponse>((resolve) => {
                    resolveRun = resolve;
                }),
        );
        const wrapper = mountLab();

        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();

        const running = buttonByText(wrapper, "运行");
        expect(running.attributes("disabled")).toBeDefined();
        expect(running.attributes("aria-busy")).toBe("true");
        expect(wrapper.text()).toContain("运行中…");

        await running.trigger("click");
        expect(executeCode).toHaveBeenCalledTimes(1);

        resolveRun(successResponse());
        await flushPromises();
        expect(wrapper.text()).toContain("shape: (4, 3)");
        // 跑完回到可再次运行（代码非空）
        expect(buttonByText(wrapper, "运行").attributes("disabled")).toBeUndefined();
    });

    it("无输出时显示占位提示，清空输出后回到占位", async () => {
        executeCode.mockResolvedValue(successResponse());
        const wrapper = mountLab();

        expect(wrapper.text()).toContain("运行后在这里看到输出");

        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("shape: (4, 3)");

        await buttonByText(wrapper, "清空输出").trigger("click");
        await flushPromises();
        expect(wrapper.text()).not.toContain("shape: (4, 3)");
        expect(wrapper.text()).toContain("运行后在这里看到输出");
    });

    it("代码里的 stderr 原样展示在输出区", async () => {
        executeCode.mockResolvedValue(
            successResponse({
                status: "error",
                stdout: "",
                stderr: "ZeroDivisionError: division by zero",
                executionTime: 5,
                resultType: "error",
            }),
        );
        const wrapper = mountLab();

        await buttonByText(wrapper, "运行").trigger("click");
        await flushPromises();

        expect(wrapper.text()).toContain("ZeroDivisionError: division by zero");
        expect(wrapper.text()).toContain("失败");
    });

    it("侧栏给出数据集参考，且不提供可用文件路径", () => {
        const wrapper = mountLab();

        expect(wrapper.text()).toContain("数据集参考");
        expect(wrapper.text()).toContain("orders.csv");
        expect(wrapper.text()).toContain("5000 行 · 11 列");
        expect(wrapper.text()).toContain("customers.csv");
        expect(wrapper.text()).toContain("orders_dirty.csv");
        // 静态说明：实验室不挂载数据集，别写成"可以读 data/ecommerce/..."的假承诺
        expect(wrapper.text()).toContain("不挂载");
    });

    it("「用内联数据试试」把自造 DataFrame 示例塞进编辑器", async () => {
        const wrapper = mountLab();
        const textarea = wrapper.get("textarea");

        await buttonByText(wrapper, "用内联数据试试").trigger("click");
        await flushPromises();

        expect(textarea.element.value).toContain("import polars as pl");
        expect(textarea.element.value).toContain("group_by");
        expect(textarea.element.value).not.toContain("data/ecommerce");
    });
});