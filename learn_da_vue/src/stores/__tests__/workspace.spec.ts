import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const createSession = vi.fn();
const fetchSession = vi.fn();
const updateCell = vi.fn();
const runCellApi = vi.fn();
const submitTaskApi = vi.fn();

vi.mock("@/api/workspace", () => ({
    createSession: (...args: unknown[]) => createSession(...args),
    fetchSession: (...args: unknown[]) => fetchSession(...args),
    updateCell: (...args: unknown[]) => updateCell(...args),
    runCell: (...args: unknown[]) => runCellApi(...args),
    submitTask: (...args: unknown[]) => submitTaskApi(...args),
}));

import { useWorkspaceStore } from "@/stores/workspace";

function snapshot(overrides: Record<string, unknown> = {}) {
    return {
        sessionId: 7,
        lessonSlug: "polars-groupby",
        contentVersion: "v1",
        cells: [
            {
                cellId: "c1",
                position: 0,
                kind: "starter",
                taskId: null,
                language: "python",
                code: "print(1)",
                status: "ok",
                hasAssertions: false,
            },
            {
                cellId: "c2",
                position: 1,
                kind: "task",
                taskId: "t1",
                language: "python",
                code: "TODO",
                status: "stale",
                hasAssertions: true,
            },
        ],
        tasks: [
            {
                taskId: "t1",
                title: "按区域聚合",
                cellId: "c2",
                objective: "聚合",
                status: "todo",
            },
        ],
        datasets: ["ecommerce/orders.csv"],
        staleFrom: "c2",
        ...overrides,
    };
}

function runResponse(overrides: Record<string, unknown> = {}) {
    return {
        requestId: "req-1",
        sessionId: 7,
        cellId: "c2",
        verdict: "passed",
        cells: [
            {
                cellId: "c1",
                status: "success",
                stdout: "1\n",
                stderr: "",
                errorType: null,
                durationMs: 12,
                truncated: false,
            },
            {
                cellId: "c2",
                status: "success",
                stdout: "ok\n",
                stderr: "",
                errorType: null,
                durationMs: 15,
                truncated: false,
            },
        ],
        assertions: [
            {
                id: "a1",
                type: "expr_true",
                title: "结果正确",
                status: "passed",
                actual: null,
                detail: null,
                durationMs: 1,
            },
        ],
        assertionsSkipped: false,
        taskStatus: "passed",
        durationMs: 30,
        error: "",
        ...overrides,
    };
}

describe("workspace store", () => {
    beforeEach(() => {
        setActivePinia(createPinia());
        vi.useRealTimers();
        createSession.mockReset();
        fetchSession.mockReset();
        updateCell.mockReset();
        runCellApi.mockReset();
        submitTaskApi.mockReset();
    });

    it("load 会创建会话并铺好格子与任务", async () => {
        createSession.mockResolvedValue(snapshot());
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        expect(createSession).toHaveBeenCalledWith("polars-groupby");
        expect(store.cells).toHaveLength(2);
        expect(store.tasks[0].taskId).toBe("t1");
        expect(store.staleFrom).toBe("c2");
        expect(store.passedTasks).toBe(0);
        expect(store.allPassed).toBe(false);
    });

    it("load 失败时记录错误且不留半截快照", async () => {
        createSession.mockRejectedValue(new Error("后端挂了"));
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        expect(store.error).toBe("后端挂了");
        expect(store.snapshot).toBeNull();
    });

    it("editCell 立刻改本地代码，flush 时才发请求", async () => {
        createSession.mockResolvedValue(snapshot());
        updateCell.mockResolvedValue(snapshot({ cells: snapshot().cells.map((c) => ({ ...c, code: "print(2)" })) }));
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        store.editCell("c2", "print(2)");
        expect(store.cells[1].code).toBe("print(2)");
        expect(store.saveState).toBe("dirty");
        expect(updateCell).not.toHaveBeenCalled();

        await store.flush("c2");
        expect(updateCell).toHaveBeenCalledWith(7, "c2", "print(2)");
        expect(store.saveState).toBe("saved");
    });

    it("editCell 内容没变时不打网络", async () => {
        createSession.mockResolvedValue(snapshot());
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        expect(store.editCell("c2", "TODO")).toBe(false);
        await store.flush("c2");
        expect(updateCell).not.toHaveBeenCalled();
    });

    it("submitTask 先落库未提交的编辑，再打球并刷新快照", async () => {
        createSession.mockResolvedValue(snapshot());
        updateCell.mockResolvedValue(snapshot());
        submitTaskApi.mockResolvedValue(runResponse());
        fetchSession.mockResolvedValue(
            snapshot({
                cells: snapshot().cells.map((c) => ({ ...c, status: "ok" })),
                tasks: [{ ...snapshot().tasks[0], status: "passed" }],
                staleFrom: null,
            }),
        );
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        store.editCell("c2", "print('ok')");
        await store.submitTask("t1");

        expect(updateCell).toHaveBeenCalledWith(7, "c2", "print('ok')");
        expect(submitTaskApi).toHaveBeenCalledTimes(1);
        expect(submitTaskApi.mock.calls[0].slice(0, 2)).toEqual([7, "t1"]);
        expect(typeof submitTaskApi.mock.calls[0][2]).toBe("string");
        expect(store.passedTasks).toBe(1);
        expect(store.allPassed).toBe(true);
        expect(store.assertionsFor("c2")).toHaveLength(1);
    });

    it("runCell 在已有执行在跑时直接返回 null", async () => {
        createSession.mockResolvedValue(snapshot());
        runCellApi.mockImplementation(
            () => new Promise((resolve) => setTimeout(() => resolve(runResponse()), 5)),
        );
        fetchSession.mockResolvedValue(snapshot());
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        const first = store.runCell("c2");
        expect(store.runningCellId).toBe("c2");
        expect(await store.runCell("c2")).toBeNull();
        await first;
        expect(runCellApi).toHaveBeenCalledTimes(1);
        expect(store.runningCellId).toBeNull();
    });

    it("执行失败时记录错误并复位 running 状态", async () => {
        createSession.mockResolvedValue(snapshot());
        runCellApi.mockRejectedValue(new Error("runner 挂了"));
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        const result = await store.runCell("c2");
        expect(result).toBeNull();
        expect(store.error).toBe("runner 挂了");
        expect(store.runningCellId).toBeNull();
    });

    it("assertionsSkipped 时任务不算通过", async () => {
        createSession.mockResolvedValue(snapshot());
        submitTaskApi.mockResolvedValue(
            runResponse({ verdict: "execution_failed", assertions: [], assertionsSkipped: true, taskStatus: "skipped" }),
        );
        fetchSession.mockResolvedValue(
            snapshot({ tasks: [{ ...snapshot().tasks[0], status: "skipped" }], staleFrom: "c2" }),
        );
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        await store.submitTask("t1");
        expect(store.tasks[0].status).toBe("skipped");
        expect(store.passedTasks).toBe(0);
        expect(store.staleFrom).toBe("c2");
    });

    it("reset 清空会话与执行结果", async () => {
        createSession.mockResolvedValue(snapshot());
        const store = useWorkspaceStore();
        await store.load("polars-groupby");

        store.reset();
        expect(store.snapshot).toBeNull();
        expect(store.cells).toEqual([]);
        expect(store.saveState).toBe("idle");
    });
});