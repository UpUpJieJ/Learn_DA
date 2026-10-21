import { get, post, put } from "./index";

/** 单元格状态：stale=需要（重新）执行，ok=上次执行成功，failed=上次执行失败 */
export type CellStatus = "stale" | "ok" | "failed";
export type CellKind = "starter" | "task" | "scratch";
export type TaskStatus = "todo" | "passed" | "failed" | "skipped";
export type RunVerdict = "passed" | "execution_failed" | "assertion_failed";

export interface WorkspaceCell {
    cellId: string;
    position: number;
    kind: CellKind;
    taskId: string | null;
    language: string;
    code: string;
    status: CellStatus;
    hasAssertions: boolean;
}

export interface WorkspaceTask {
    taskId: string;
    title: string;
    cellId: string;
    objective: string;
    status: TaskStatus;
}

export interface SessionSnapshot {
    sessionId: number;
    lessonSlug: string;
    contentVersion: string;
    cells: WorkspaceCell[];
    tasks: WorkspaceTask[];
    datasets: string[];
    staleFrom: string | null;
}

export interface AssertionResult {
    id: string;
    type: string;
    title: string;
    status: "passed" | "failed" | "error" | "timeout" | "skipped";
    actual: string | null;
    detail: string | null;
    durationMs: number;
}

export interface CellRunResult {
    cellId: string;
    status: string;
    stdout: string;
    stderr: string;
    errorType: string | null;
    durationMs: number;
    truncated: boolean;
}

export interface RunResponse {
    requestId: string;
    sessionId: number;
    cellId: string;
    verdict: RunVerdict;
    cells: CellRunResult[];
    assertions: AssertionResult[];
    assertionsSkipped: boolean;
    taskStatus: TaskStatus | null;
    durationMs: number;
    error: string;
}

const BASE = "/workspace/sessions";

export function createSession(lessonSlug: string) {
    return post<SessionSnapshot>(BASE, { lessonSlug });
}

export function fetchSession(sessionId: number) {
    return get<SessionSnapshot>(`${BASE}/${sessionId}`);
}

export function updateCell(sessionId: number, cellId: string, code: string) {
    return put<SessionSnapshot>(`${BASE}/${sessionId}/cells/${cellId}`, { code });
}

export function runCell(sessionId: number, cellId: string, requestId: string) {
    return post<RunResponse>(
        `${BASE}/${sessionId}/cells/${cellId}/run`,
        { requestId },
        { timeout: 60000 },
    );
}

export function submitTask(sessionId: number, taskId: string, requestId: string) {
    return post<RunResponse>(
        `${BASE}/${sessionId}/tasks/${taskId}/submit`,
        { requestId },
        { timeout: 60000 },
    );
}