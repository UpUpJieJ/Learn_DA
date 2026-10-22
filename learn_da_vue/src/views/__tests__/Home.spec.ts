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

import Home from "@/views/Home.vue";
import type { LessonProgress, ReportPayload } from "@/api/workspace";

// =====================================================
// 造数据：只覆盖页面真正读到的字段
// =====================================================

function lesson(overrides: Partial<LessonProgress> = {}): LessonProgress {
    return {
        lessonSlug: "polars-groupby",
        title: "Polars 分组聚合",
        track: "polars_basics",
        order: 3,
        difficulty: "入门",
        estimatedMinutes: 20,
        totalTasks: 2,
        passedTasks: 1,
        status: "in_progress",
        currentTaskId: "t2",
        attempts: 3,
        lastActivityAt: "2026-10-22T10:00:00+00:00",
        ...overrides,
    };
}

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
        lessonProgress: [
            lesson(),
            lesson({
                lessonSlug: "polars-basics",
                title: "Polars 入门",
                totalTasks: 3,
                passedTasks: 0,
                currentTaskId: "t1",
                lastActivityAt: "2026-10-21T10:00:00+00:00",
            }),
            lesson({
                lessonSlug: "python-functions",
                title: "Python 函数",
                totalTasks: 3,
                passedTasks: 0,
                status: "not_started",
                currentTaskId: null,
                attempts: 0,
                lastActivityAt: null,
            }),
            lesson({
                lessonSlug: "duckdb-analytics",
                title: "DuckDB 分析",
                totalTasks: 3,
                passedTasks: 0,
                status: "not_started",
                currentTaskId: null,
                attempts: 0,
                lastActivityAt: null,
            }),
        ],
        tracks: [
            {
                track: "polars_basics",
                label: "Polars 基础",
                totalTasks: 8,
                passedTasks: 2,
                lessons: 3,
                completedLessons: 0,
                ratio: 0.25,
            },
        ],
        summary: summary(),
        errorPatterns: [],
        recent: [],
        windowDays: 30,
        generatedAt: "2026-10-22T12:00:00+00:00",
        ...overrides,
    };
}

beforeEach(() => {
    fetchReport.mockReset();
    push.mockReset();
});

describe("Home（今日）", () => {
    it("把最近动过的那门课放在主卡，并带上当前任务深链", async () => {
        fetchReport.mockResolvedValue(payload());
        const wrapper = mount(Home);
        await flushPromises();

        const text = wrapper.text();
        expect(text).toContain("继续上次");
        expect(text).toContain("Polars 分组聚合");
        expect(text).toContain("1/2 个任务");
        expect(text).not.toContain("从这里开始");

        const primary = wrapper.findAll("button").find((item) => item.text() === "继续");
        expect(primary).toBeTruthy();
        await primary!.trigger("click");
        expect(push).toHaveBeenCalledWith({ path: "/lesson/polars-groupby", query: { task: "t2" } });
    });

    it("没有学习记录时降级为「从这里开始」，并且不带任务深链", async () => {
        fetchReport.mockResolvedValue(
            payload({
                summary: summary({ attemptsTotal: 0, tasksPassed: 0, tasksFirstTry: 0, streakDays: 0, lessonsCompleted: 0 }),
                errorPatterns: [],
                lessonProgress: [
                    lesson({
                        lessonSlug: "polars-basics",
                        title: "Polars 入门",
                        totalTasks: 3,
                        passedTasks: 0,
                        status: "not_started",
                        currentTaskId: null,
                        attempts: 0,
                        lastActivityAt: null,
                    }),
                ],
            }),
        );
        const wrapper = mount(Home);
        await flushPromises();

        const text = wrapper.text();
        expect(text).toContain("从这里开始");
        expect(text).toContain("还没有学习记录");

        const cta = wrapper.findAll("button").find((item) => item.text() === "开始学习");
        expect(cta).toBeTruthy();
        await cta!.trigger("click");
        expect(push).toHaveBeenCalledWith({ path: "/lesson/polars-basics", query: undefined });
    });

    it("指标带用真实计数，一次通过率按已通过任务算", async () => {
        fetchReport.mockResolvedValue(payload());
        const wrapper = mount(Home);
        await flushPromises();

        const text = wrapper.text();
        expect(text).toContain("已通过任务");
        expect(text).toContain("/ 4");
        expect(text).toContain("完成课程");
        expect(text).toContain("一次通过率");
        expect(text).toContain("50%"); // tasksFirstTry 1 / tasksPassed 2
        expect(text).toContain("连续学习");
    });

    it("有卡点时展示卡点卡，并能跳回那个任务", async () => {
        fetchReport.mockResolvedValue(
            payload({
                errorPatterns: [
                    {
                        lessonSlug: "polars-cleaning",
                        lessonTitle: "数据清洗",
                        taskId: "t2",
                        taskTitle: "去重与规范",
                        assertionId: "t2-region",
                        title: "region 取值集合",
                        status: "failed",
                        count: 3,
                        lastActual: "缺少列 ['region']",
                    },
                ],
            }),
        );
        const wrapper = mount(Home);
        await flushPromises();

        const text = wrapper.text();
        expect(text).toContain("上次卡住的地方");
        expect(text).toContain("数据清洗 › 去重与规范");
        expect(text).toContain("失败 3 次");
        expect(text).toContain("缺少列 ['region']");

        const back = wrapper.findAll("button").find((item) => item.text() === "回去看看");
        expect(back).toBeTruthy();
        await back!.trigger("click");
        expect(push).toHaveBeenCalledWith({ path: "/lesson/polars-cleaning", query: { task: "t2" } });
    });

    it("「接下来」最多两门，且不含主卡那门", async () => {
        fetchReport.mockResolvedValue(payload());
        const wrapper = mount(Home);
        await flushPromises();

        const section = wrapper.findAll("section").find((item) => item.text().startsWith("接下来"));
        expect(section).toBeTruthy();
        expect(section!.text()).toContain("Polars 入门");
        expect(section!.text()).toContain("Python 函数");
        expect(section!.text()).not.toContain("DuckDB 分析");
        expect(section!.text()).not.toContain("Polars 分组聚合");
    });

    it("路径进度只用后端给的真实比例", async () => {
        fetchReport.mockResolvedValue(payload());
        const wrapper = mount(Home);
        await flushPromises();

        const bars = wrapper.findAll('div[style*="width"]');
        expect(bars.length).toBeGreaterThan(0);
        expect(bars.some((bar) => bar.attributes("style")?.includes("width: 25%"))).toBe(true);
        expect(wrapper.text()).toContain("2/8");
    });

    it("超过三天没练会在概览里点出来", async () => {
        fetchReport.mockResolvedValue(payload({ summary: summary({ daysSinceActive: 4 }) }));
        const wrapper = mount(Home);
        await flushPromises();
        expect(wrapper.text()).toContain("已经 4 天没练了");
    });

    it("全部做完时主卡退回复习，不留空位", async () => {
        fetchReport.mockResolvedValue(
            payload({
                lessonProgress: [
                    lesson({
                        lessonSlug: "polars-basics",
                        title: "Polars 入门",
                        totalTasks: 3,
                        passedTasks: 3,
                        status: "completed",
                        currentTaskId: null,
                    }),
                ],
            }),
        );
        const wrapper = mount(Home);
        await flushPromises();

        expect(wrapper.text()).toContain("Polars 入门");
        expect(wrapper.text()).toContain("继续上次");
        const cta = wrapper.findAll("button").find((item) => item.text() === "复习");
        expect(cta).toBeTruthy();
        await cta!.trigger("click");
        expect(push).toHaveBeenCalledWith({ path: "/lesson/polars-basics", query: undefined });
    });

    it("加载失败时给出重试", async () => {
        fetchReport.mockRejectedValueOnce(new Error("网络断了")).mockResolvedValueOnce(payload());
        const wrapper = mount(Home);
        await flushPromises();
        expect(wrapper.text()).toContain("加载失败");
        expect(wrapper.text()).toContain("网络断了");

        const retry = wrapper.findAll("button").find((item) => item.text() === "重试");
        expect(retry).toBeTruthy();
        await retry!.trigger("click");
        await flushPromises();
        expect(fetchReport).toHaveBeenCalledTimes(2);
        expect(wrapper.text()).toContain("继续上次");
    });

    it("没有课程时给空态和动作", async () => {
        fetchReport.mockResolvedValue(payload({ lessonProgress: [], tracks: [] }));
        const wrapper = mount(Home);
        await flushPromises();

        expect(wrapper.text()).toContain("还没有可以练习的课");
        const cta = wrapper.findAll("button").find((item) => item.text() === "打开实验室");
        expect(cta).toBeTruthy();
        await cta!.trigger("click");
        expect(push).toHaveBeenCalledWith("/lab");
    });
});