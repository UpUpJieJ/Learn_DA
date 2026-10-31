import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
    createSession,
    fetchSession,
    requestHint as requestHintApi,
    runCell as runCellApi,
    submitTask as submitTaskApi,
    updateCell as updateCellApi,
    type AssertionResult,
    type HintResponse,
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
    /** 正在要提示的任务（避免连点同时发两次） */
    const hintingTaskId = ref<string | null>(null);
    /** 每个任务已经拿到的提示（按层累积，新到旧） */
    const hints = ref<Record<string, HintResponse[]>>({});
    const saveState = ref<"idle" | "dirty" | "saving" | "saved" | "error">("idle");

    let generation = 0;
    const timers = new Map<string, ReturnType<typeof setTimeout>>();
    let pendingCode = new Map<string, string>();
    const saves = new Map<string, Promise<boolean>>();
    const savingCode = new Map<string, string>();
    const localEdits = new Map<string, string>();

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
        reset();
        const epoch = generation;
        loading.value = true;
        error.value = null;
        runs.value = {};
        try {
            const result = await createSession(lessonSlug);
            if (epoch === generation) snapshot.value = result;
        } catch (err) {
            if (epoch !== generation) return;
            error.value = err instanceof Error ? err.message : "加载工作区失败";
            snapshot.value = null;
        } finally {
            if (epoch === generation) loading.value = false;
        }
    }

    function applySnapshot(result: SessionSnapshot) {
        for (const cell of result.cells) {
            const pending = localEdits.get(cell.cellId) ?? pendingCode.get(cell.cellId) ?? savingCode.get(cell.cellId);
            if (pending !== undefined) cell.code = pending;
        }
        snapshot.value = result;
    }

    async function refresh(sessionId: number) {
        const epoch = generation;
        const result = await fetchSession(sessionId);
        if (epoch === generation && snapshot.value?.sessionId === sessionId) applySnapshot(result);
    }

    /** 本地立即生效，网络去抖；返回是否真的改了内容。 */
    function editCell(cellId: string, code: string): boolean {
        const cell = snapshot.value?.cells.find((item) => item.cellId === cellId);
        if (!cell || cell.code === code) return false;
        cell.code = code;
        localEdits.set(cellId, code);
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

    async function flush(cellId: string): Promise<boolean> {
        const epoch = generation;
        const active = saves.get(cellId);
        if (active) {
            if (!(await active) || epoch !== generation) return false;
            return flush(cellId);
        }
        const sessionId = snapshot.value?.sessionId;
        const code = pendingCode.get(cellId);
        if (!sessionId || code === undefined) return true;
        const timer = timers.get(cellId);
        if (timer) clearTimeout(timer);
        timers.delete(cellId);
        pendingCode.delete(cellId);
        savingCode.set(cellId, code);
        saveState.value = "saving";
        const operation = (async () => {
            try {
                const result = await updateCellApi(sessionId, cellId, code);
                if (epoch !== generation) return false;
                // Preserve other pending/in-flight edits while merging server statuses.
                applySnapshot(result);
                saveState.value = pendingCode.size ? "dirty" : "saved";
                return true;
            } catch (err) {
                if (epoch !== generation) return false;
                if (!pendingCode.has(cellId)) pendingCode.set(cellId, code);
                saveState.value = "error";
                error.value = err instanceof Error ? err.message : "保存失败";
                return false;
            } finally {
                if (epoch === generation) {
                    saves.delete(cellId);
                    savingCode.delete(cellId);
                }
            }
        })();
        saves.set(cellId, operation);
        return operation;
    }

    /** 切走页面前把没发出去的编辑立刻提交。 */
    async function flushAll() {
        for (const [cellId, timer] of timers) {
            clearTimeout(timer);
            timers.delete(cellId);
        }
        const ids = new Set([...pendingCode.keys(), ...saves.keys()]);
        const results = await Promise.all([...ids].map((cellId) => flush(cellId)));
        return results.every(Boolean);
    }

    async function runCell(cellId: string) {
        const epoch = generation;
        const sessionId = snapshot.value?.sessionId;
        if (!sessionId || runningCellId.value) return null;
        // 先占位再 flush：flush 也是异步，占位晚了连点两下会并发跑两次。
        runningCellId.value = cellId;
        error.value = null;
        try {
            if (!(await flushAll())) return null;
            if (epoch !== generation) return null;
            const result = await runCellApi(sessionId, cellId, randomId());
            if (epoch !== generation) return null;
            runs.value = { ...runs.value, [cellId]: { ...result, cellId } };
            if (snapshot.value) await refresh(sessionId);
            return result;
        } catch (err) {
            if (epoch !== generation) return null;
            error.value = err instanceof Error ? err.message : "执行失败";
            return null;
        } finally {
            if (epoch === generation) runningCellId.value = null;
        }
    }

    async function submitTask(taskId: string) {
        const epoch = generation;
        const sessionId = snapshot.value?.sessionId;
        if (!sessionId || submittingTaskId.value) return null;
        const task = tasks.value.find((item) => item.taskId === taskId);
        if (!task) return null;
        submittingTaskId.value = taskId;
        error.value = null;
        try {
            if (!(await flushAll())) return null;
            if (epoch !== generation) return null;
            const result = await submitTaskApi(sessionId, taskId, randomId());
            if (epoch !== generation) return null;
            runs.value = { ...runs.value, [task.cellId]: { ...result, cellId: task.cellId } };
            if (snapshot.value) await refresh(sessionId);
            return result;
        } catch (err) {
            if (epoch !== generation) return null;
            error.value = err instanceof Error ? err.message : "提交失败";
            return null;
        } finally {
            if (epoch === generation) submittingTaskId.value = null;
        }
    }

    function assertionsFor(cellId: string): AssertionResult[] {
        return runs.value[cellId]?.assertions ?? [];
    }

    function hintsFor(taskId: string): HintResponse[] {
        return hints.value[taskId] ?? [];
    }

    /**
     * 要一层提示。
     *
     * 层级完全由服务端按「距上次提示的失败次数 + 已用层数」算，前端不传层级，
     * 所以越层请求天然无效；拿到后把该任务的任务状态刷新（hintsUsed 会变）。
     */
    async function requestHint(taskId: string) {
        const epoch = generation;
        const sessionId = snapshot.value?.sessionId;
        if (!sessionId || hintingTaskId.value) return null;
        hintingTaskId.value = taskId;
        error.value = null;
        try {
            const hint = await requestHintApi(sessionId, taskId);
            if (epoch !== generation) return null;
            hints.value = {
                ...hints.value,
                [taskId]: [...(hints.value[taskId] ?? []), hint],
            };
            if (snapshot.value) await refresh(sessionId);
            return hint;
        } catch (err) {
            if (epoch !== generation) return null;
            error.value = err instanceof Error ? err.message : "获取提示失败";
            return null;
        } finally {
            if (epoch === generation) hintingTaskId.value = null;
        }
    }

    async function destroy(): Promise<boolean> {
        const sessionId = snapshot.value?.sessionId;
        const drafts = new Map([...savingCode, ...pendingCode]);
        const active = [...saves.values()];
        reset();
        await Promise.all(active);
        if (!sessionId) return true;
        try {
            await Promise.all([...drafts].map(([cellId, code]) => updateCellApi(sessionId, cellId, code)));
            return true;
        } catch {
            return false;
        }
    }

    function reset() {
        generation++;
        loading.value = false;
        for (const timer of timers.values()) clearTimeout(timer);
        timers.clear();
        pendingCode = new Map();
        saves.clear();
        savingCode.clear();
        localEdits.clear();
        snapshot.value = null;
        runs.value = {};
        hints.value = {};
        error.value = null;
        saveState.value = "idle";
        runningCellId.value = null;
        submittingTaskId.value = null;
        hintingTaskId.value = null;
    }

    return {
        snapshot,
        loading,
        error,
        runs,
        hints,
        runningCellId,
        submittingTaskId,
        hintingTaskId,
        saveState,
        tasks,
        cells,
        passedTasks,
        staleFrom,
        allPassed,
        taskForCell,
        assertionsFor,
        hintsFor,
        load,
        refresh,
        editCell,
        flush,
        flushAll,
        destroy,
        runCell,
        submitTask,
        requestHint,
        reset,
    };
});