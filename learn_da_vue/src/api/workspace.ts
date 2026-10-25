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
    /** 下一次点「给点提示」能拿到的层级（服务端按真实失败次数算） */
    hintLevel: number;
    /** 该任务已经用过几层提示 */
    hintsUsed: number;
    /** 层级上限（当前固定 3） */
    hintMaxLevel: number;
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

/** 分层提示（ladder）：请求体为空，层级由服务端每次重算，客户端无法指定。 */
export interface HintResponse {
    taskId: string;
    level: number;
    maxLevel: number;
    hintsUsed: number;
    content: string;
    hasNext: boolean;
}

export function requestHint(sessionId: number, taskId: string) {
    return post<HintResponse>(
        `${BASE}/${sessionId}/tasks/${taskId}/hint`,
        {},
        { timeout: 30000 },
    );
}

// =====================================================
// 课程地图进度与学习报告（改版 P1 / P3）
// =====================================================

export interface LessonProgress {
    lessonSlug: string;
    title: string;
    track: string | null;
    order: number;
    difficulty: string | null;
    estimatedMinutes: number | null;
    totalTasks: number;
    passedTasks: number;
    status: "not_started" | "in_progress" | "completed";
    currentTaskId: string | null;
    attempts: number;
    lastActivityAt: string | null;
}

export interface TrackProgress {
    track: string;
    label: string;
    totalTasks: number;
    passedTasks: number;
    lessons: number;
    completedLessons: number;
    /** 0–1 的小数（后端 round(passedTasks / totalTasks, 3)），渲染百分比时需 ×100 */
    ratio?: number;
}

export interface ProgressPayload {
    lessons: LessonProgress[];
    tracks: TrackProgress[];
    summary: {
        lessonsTotal: number;
        lessonsStarted: number;
        lessonsCompleted: number;
        tasksTotal: number;
        tasksPassed: number;
        attemptsTotal: number;
    };
}

export interface ErrorPattern {
    lessonSlug: string;
    lessonTitle: string;
    taskId: string;
    taskTitle: string;
    assertionId: string;
    title: string;
    status: string;
    count: number;
    lastActual: string;
}

export interface RecentAttempt {
    lessonSlug: string;
    lessonTitle: string;
    taskId: string;
    taskTitle: string;
    status: TaskStatus;
    attemptNo: number;
    createdAt: string | null;
}

export interface ReportPayload {
    lessonProgress: LessonProgress[];
    tracks: TrackProgress[];
    summary: {
        lessonsTotal: number;
        lessonsStarted: number;
        lessonsCompleted: number;
        tasksTotal: number;
        tasksPassed: number;
        attemptsTotal: number;
        tasksFirstTry: number;
        activeDays: number;
        streakDays: number;
        lastActiveAt: string | null;
        daysSinceActive: number | null;
    };
    errorPatterns: ErrorPattern[];
    recent: RecentAttempt[];
    windowDays: number;
    generatedAt: string;
}

export function fetchProgress() {
    return get<ProgressPayload>("/workspace/progress");
}

export function fetchReport() {
    return get<ReportPayload>("/workspace/report");
}