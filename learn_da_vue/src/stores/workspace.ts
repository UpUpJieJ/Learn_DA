import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
    createSession,
    fetchSession,
    runCell as runCellApi,
    submitTask as submitTaskApi,
    updateCell as updateCellApi,
    type AssertionResult,
    type RunResponse,
    type SessionSnapshot,
} from "@/api/workspace";
import { randomId } from "@/lib/uuid";

/** 保存去抖：编辑后 800ms 没再输入才提交，避免每个按键都打网络。 */
const SAVE_DEBOUNCE_MS = 800;

export interface CellRunView extends RunResponse {
    /** 本次执行对应的输出块位置（按 cellId 归并，便于在单元格内渲染） */
    cellId: string;
}

export const useWorkspaceStore = defineStore("workspace", () => {
    const snapshot = ref<SessionSnapshot | null>(null);
    const loading = ref(false);
    const error = ref<string | null>(null);
    const runs = ref<Record<string, CellRunView>>({});
    const runningCellId = ref<string | null>(null);
    const submittingTaskId = ref<string | null>(null);
    const saveState = ref<"idle" | "dirty" | "saving" | "saved" | "error">("idle");

    const timers = new Map<string, ReturnType<typeof setTimeout>>();
    let pendingCode = new Map<string, string>();

    const tasks = computed(() => snapshot.value?.tasks ?? []);
    const cells = computed(() => snapshot.value?.cells ?? []);
    const passedTasks = computed(
        () => tasks.value.filter((task) => task.status === "passed").length,
    );
    const staleFrom = computed(() => snapshot.value?.staleFrom ?? null);
    const allPassed = computed(
        () => tasks.value.length > 0 && passedTasks.value === tasks.value.length,
    );

    function taskForCell(cellId: string) {
        return tasks.value.find((task) => task.cellId === cellId) ?? null;
    }

    async function load(lessonSlug: string) {
        loading.value = true;
        error.value = null;
        runs.value = {};
        try {
            snapshot.value = await createSession(lessonSlug);
        } catch (err) {
            error.value = err instanceof Error ? err.message : "加载工作区失败";
            snapshot.value = null;
        } finally {
            loading.value = false;
        }
    }

    async function refresh(sessionId: number) {
        snapshot.value = await fetchSession(sessionId);
    }

    /** 本地立即生效，网络去抖；返回是否真的改了内容。 */
    function editCell(cellId: string, code: string): boolean {
        const cell = snapshot.value?.cells.find((item) => item.cellId === cellId);
        if (!cell || cell.code === code) return false;
        cell.code = code;
        pendingCode.set(cellId, code);
        saveState.value = "dirty";

        const existing = timers.get(cellId);
        if (existing) clearTimeout(existing);
        timers.set(
            cellId,
            setTimeout(() => {
                timers.delete(cellId);
                void flush(cellId);
            }, SAVE_DEBOUNCE_MS),
        );
        return true;
    }

    async function flush(cellId: string) {
        const sessionId = snapshot.value?.sessionId;
        const code = pendingCode.get(cellId);
        if (!sessionId || code === undefined) return;
        pendingCode.delete(cellId);
        saveState.value = "saving";
        try {
            snapshot.value = await updateCellApi(sessionId, cellId, code);
            saveState.value = pendingCode.size ? "dirty" : "saved";
        } catch (err) {
            pendingCode.set(cellId, code);
            saveState.value = "error";
            error.value = err instanceof Error ? err.message : "保存失败";
        }
    }

    /** 切走页面前把没发出去的编辑立刻提交。 */
    async function flushAll() {
        for (const [cellId, timer] of timers) {
            clearTimeout(timer);
            timers.delete(cellId);
        }
        await Promise.all([...pendingCode.keys()].map((cellId) => flush(cellId)));
    }

    async function runCell(cellId: string) {
        const sessionId = snapshot.value?.sessionId;
        if (!sessionId || runningCellId.value) return null;
        // 先占位再 flush：flush 也是异步，占位晚了连点两下会并发跑两次。
        runningCellId.value = cellId;
        error.value = null;
        try {
            await flush(cellId);
            const result = await runCellApi(sessionId, cellId, randomId());
            runs.value = { ...runs.value, [cellId]: { ...result, cellId } };
            if (snapshot.value) await refresh(sessionId);
            return result;
        } catch (err) {
            error.value = err instanceof Error ? err.message : "执行失败";
            return null;
        } finally {
            runningCellId.value = null;
        }
    }

    async function submitTask(taskId: string) {
        const sessionId = snapshot.value?.sessionId;
        if (!sessionId || submittingTaskId.value) return null;
        const task = tasks.value.find((item) => item.taskId === taskId);
        if (!task) return null;
        submittingTaskId.value = taskId;
        error.value = null;
        try {
            await flush(task.cellId);
            const result = await submitTaskApi(sessionId, taskId, randomId());
            runs.value = { ...runs.value, [task.cellId]: { ...result, cellId: task.cellId } };
            if (snapshot.value) await refresh(sessionId);
            return result;
        } catch (err) {
            error.value = err instanceof Error ? err.message : "提交失败";
            return null;
        } finally {
            submittingTaskId.value = null;
        }
    }

    function assertionsFor(cellId: string): AssertionResult[] {
        return runs.value[cellId]?.assertions ?? [];
    }

    function reset() {
        for (const timer of timers.values()) clearTimeout(timer);
        timers.clear();
        pendingCode = new Map();
        snapshot.value = null;
        runs.value = {};
        error.value = null;
        saveState.value = "idle";
        runningCellId.value = null;
        submittingTaskId.value = null;
    }

    return {
        snapshot,
        loading,
        error,
        runs,
        runningCellId,
        submittingTaskId,
        saveState,
        tasks,
        cells,
        passedTasks,
        staleFrom,
        allPassed,
        taskForCell,
        assertionsFor,
        load,
        refresh,
        editCell,
        flush,
        flushAll,
        runCell,
        submitTask,
        reset,
    };
});