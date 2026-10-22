// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const fetchReport = vi.fn();
const push = vi.fn();

vi.mock("@/api/workspace", () => ({
    fetchReport: (...args: unknown[]) => fetchReport(...args),
}));

vi.mock("vue-router", () => ({
    useRouter: () => ({ push }),
}));

import Report from "@/views/Report.vue";
import type { ReportPayload } from "@/api/workspace";

// =====================================================
// 造数据：只覆盖页面真正读到的字段，数值刻意设计成可手算
// =====================================================

function summary(overrides: Partial<ReportPayload["summary"]> = {}): ReportPayload["summary"] {
    return {
        lessonsTotal: 13,
        lessonsStarted: 2,
        lessonsCompleted: 1,
        tasksTotal: 4,
        tasksPassed: 2,
        attemptsTotal: 5,
        tasksFirstTry: 1,
        activeDays: 2,
        streakDays: 1,
        lastActiveAt: "2026-10-22T10:00:00+00:00",
        daysSinceActive: 0,
        ...overrides,
    };
}

function payload(overrides: Partial<ReportPayload> = {}): ReportPayload {
    return {
        lessonProgress: [],
        tracks: [
            {
                track: "polars",
                label: "Polars 数据处理",
                totalTasks: 4,
                passedTasks: 2,
                lessons: 3,
                completedLessons: 1,
                ratio: 0.5,
            },
            {
                // totalTasks === 0：必须显示"暂无任务"，不能画假进度条
                track: "duckdb",
                label: "DuckDB 分析",
                totalTasks: 0,
                passedTasks: 0,
                lessons: 1,
                completedLessons: 0,
                ratio: 0,
            },
        ],
        summary: summary(),
        errorPatterns: [
            {
                lessonSlug: "polars-groupby",
                lessonTitle: "分组聚合",
                taskId: "t2",
                taskTitle: "按区域汇总",
                assertionId: "a1",
                title: "行数应为 4",
                status: "failed",
                count: 3,
                lastActual: "shape=(6, 3)",
            },
        ],
        recent: [
            {
                lessonSlug: "polars-groupby",
                lessonTitle: "分组聚合",
                taskId: "t1",
                taskTitle: "读取订单",
                status: "passed",
                attemptNo: 1,
                createdAt: "2026-10-22T09:00:00+00:00",
            },
            {
                lessonSlug: "polars-groupby",
                lessonTitle: "分组聚合",
                taskId: "t2",
                taskTitle: "按区域汇总",
                status: "failed",
                attemptNo: 2,
                createdAt: null,
            },
        ],
        windowDays: 3,
        generatedAt: "2026-10-22T12:00:00+00:00",
        ...overrides,
    };
}

beforeEach(() => {
    fetchReport.mockReset();
    push.mockReset();
});

describe("Report", () => {
    it("loading 时先渲染骨架屏，不渲染任何指标", async () => {
        fetchReport.mockImplementation(() => new Promise(() => {}));

        const wrapper = mount(Report);
        await flushPromises();

        expect(wrapper.text()).toContain("学习报告");
        expect(wrapper.findAll(".animate-pulse").length).toBeGreaterThan(0);
        expect(wrapper.text()).not.toContain("能力分布");
    });

    it("有数据时渲染五项指标、能力分布、卡点与最近提交", async () => {
        fetchReport.mockResolvedValue(payload());

        const wrapper = mount(Report);
        await flushPromises();
        const text = wrapper.text();

        // 指标区
        expect(text).toContain("已通过任务");
        expect(text).toContain("2 / 4");
        expect(text).toContain("完成课程");
        expect(text).toContain("1 / 13");
        expect(text).toContain("连续学习");
        expect(text).toContain("累计活跃");
        expect(text).toContain("2 天");
        expect(text).toContain("一次通过率");
        // 一次通过 1 / 已尝试 3（已通过 2 + 卡点里 1 个失败任务）= 33%
        expect(text).toContain("33%");
        expect(text).toContain("一次通过任务数 / 已尝试任务数");

        // 能力分布：有任务显进度，没任务显"暂无任务"
        expect(text).toContain("Polars 数据处理");
        expect(text).toContain("2 / 4 任务");
        expect(text).toContain("完成课程 1 / 3");
        expect(text).toContain("暂无任务");

        // 卡点
        expect(text).toContain("常见卡点");
        expect(text).toContain("分组聚合");
        expect(text).toContain("按区域汇总");
        expect(text).toContain("行数应为 4");
        expect(text).toContain("失败 3 次");
        expect(text).toContain("shape=(6, 3)");

        // 最近提交
        expect(text).toContain("最近提交");
        expect(text).toContain("第 1 次");
        expect(text).toContain("第 2 次");
        expect(text).toContain("已通过");
        expect(text).toContain("未通过");
        // createdAt 为 null 显示 —
        expect(text).toContain("—");
    });

    it("点常见卡点整条能跳到对应课程工作区", async () => {
        fetchReport.mockResolvedValue(payload());

        const wrapper = mount(Report);
        await flushPromises();

        const target = wrapper
            .findAll("button")
            .find((btn) => btn.text().includes("行数应为 4"));
        expect(target).toBeTruthy();

        await target!.trigger("click");
        expect(push).toHaveBeenCalledWith("/lesson/polars-groupby");
    });

    it("最近提交的每一行也能点回课程", async () => {
        fetchReport.mockResolvedValue(payload());

        const wrapper = mount(Report);
        await flushPromises();

        const target = wrapper
            .findAll("button")
            .find((btn) => btn.text().includes("读取订单"));
        expect(target).toBeTruthy();

        await target!.trigger("click");
        expect(push).toHaveBeenCalledWith("/lesson/polars-groupby");
    });

    it("attemptsTotal === 0 时只显示空态，不渲染空表", async () => {
        fetchReport.mockResolvedValue(
            payload({
                summary: summary({
                    attemptsTotal: 0,
                    tasksPassed: 0,
                    tasksFirstTry: 0,
                    lessonsStarted: 0,
                    lessonsCompleted: 0,
                    activeDays: 0,
                    streakDays: 0,
                    lastActiveAt: null,
                    daysSinceActive: null,
                }),
                tracks: [],
                errorPatterns: [],
                recent: [],
            }),
        );

        const wrapper = mount(Report);
        await flushPromises();
        const text = wrapper.text();

        expect(text).toContain("还没有学习记录");
        expect(text).toContain("完成第一个任务后");
        expect(text).toContain("去课程地图");
        expect(text).not.toContain("能力分布");
        expect(text).not.toContain("常见卡点");
        expect(text).not.toContain("最近提交");

        await wrapper.find("button").trigger("click");
        expect(push).toHaveBeenCalledWith("/learn");
    });

    it("接口失败时显示错误文案与重试，重试成功后渲染数据", async () => {
        fetchReport
            .mockRejectedValueOnce(new Error("报告服务挂了"))
            .mockResolvedValueOnce(payload());

        const wrapper = mount(Report);
        await flushPromises();

        expect(wrapper.text()).toContain("报告加载失败");
        expect(wrapper.text()).toContain("报告服务挂了");

        const retryButton = wrapper.findAll("button").find((btn) => btn.text() === "重试");
        expect(retryButton).toBeTruthy();

        await retryButton!.trigger("click");
        await flushPromises();

        expect(fetchReport).toHaveBeenCalledTimes(2);
        expect(wrapper.text()).not.toContain("报告加载失败");
        expect(wrapper.text()).toContain("能力分布");
    });
});