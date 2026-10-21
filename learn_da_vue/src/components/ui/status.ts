// =====================================================
// 任务/练习状态的四态定义与样式映射
//
// 状态语义来自后端 TaskAttempt / ExerciseAttempt：
//   todo         未开始
//   in_progress  进行中（有运行记录但未提交）
//   needs_review 曾通过、但上游 cell 变更导致需复核
//   passed       已通过
//   failed       提交判定未通过
//   skipped      学习者主动跳过
//
// 样式字符串必须写全（Tailwind 扫描源码文本，拼接无效），
// 且只用语义 token（ok / warn / err / brand / ink）。
// =====================================================

export type TaskStatusKind =
    | "todo"
    | "in_progress"
    | "needs_review"
    | "passed"
    | "failed"
    | "skipped";

export interface TaskStatusMeta {
    label: string;
    /** 容器（药丸）样式 */
    pillClass: string;
    /** 圆点样式 */
    dotClass: string;
    /** 是否算作"完成"（通过才计入完成率） */
    completed: boolean;
}

export const TASK_STATUS_META: Record<TaskStatusKind, TaskStatusMeta> = {
    todo: {
        label: "未开始",
        pillClass: "border-line bg-surface-raised text-ink-500",
        dotClass: "bg-ink-300",
        completed: false,
    },
    in_progress: {
        label: "进行中",
        pillClass: "border-brand-200 bg-brand-50 text-brand-700",
        dotClass: "bg-brand-500",
        completed: false,
    },
    needs_review: {
        label: "需复核",
        pillClass: "border-warn-500/40 bg-warn-50 text-warn-700",
        dotClass: "bg-warn-500",
        completed: false,
    },
    passed: {
        label: "已通过",
        pillClass: "border-ok-600/40 bg-ok-50 text-ok-700",
        dotClass: "bg-ok-500",
        completed: true,
    },
    failed: {
        label: "未通过",
        pillClass: "border-err-500/40 bg-err-50 text-err-700",
        dotClass: "bg-err-500",
        completed: false,
    },
    skipped: {
        label: "已跳过",
        pillClass: "border-line bg-surface-card text-ink-500",
        dotClass: "bg-ink-300",
        completed: false,
    },
};

/** 未知状态（后端新增而前端未跟上）一律降级为"未开始"，不抛错、不白屏。 */
export function taskStatusMeta(kind: string): TaskStatusMeta {
    return TASK_STATUS_META[kind as TaskStatusKind] ?? TASK_STATUS_META.todo;
}

/** 一门课完成任务数 / 总任务数。 */
export function countCompleted(statuses: readonly string[]): { done: number; total: number } {
    const done = statuses.filter((s) => taskStatusMeta(s).completed).length;
    return { done, total: statuses.length };
}