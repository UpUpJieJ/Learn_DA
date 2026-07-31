import { post, get } from "@/api/index";
import type {
    ExecuteRequest,
    ExecuteResponse,
    ExerciseAttemptSummary,
    ExerciseResumeResponse,
} from "@/types/api";

// =====================================================
// Playground API
// =====================================================

/**
 * 执行代码（提交到沙箱运行）
 * POST /playground/execute
 */
export function executeCode(payload: ExecuteRequest) {
    return post<ExecuteResponse>("/playground/execute", {
        code: payload.code,
        language: payload.language ?? "python",
        requestId: payload.requestId,
        source: payload.source,
        lessonSlug: payload.lessonSlug,
        exerciseId: payload.exerciseId,
    });
}

/**
 * 格式化代码（Black 格式化 Python 代码）
 * POST /playground/format
 */
export interface FormatRequest {
    code: string;
    language?: "python";
}

export interface FormatResponse {
    formatted: string;
    changed: boolean;
}

export function formatCode(payload: FormatRequest) {
    return post<FormatResponse>("/playground/format", {
        code: payload.code,
        language: payload.language ?? "python",
    });
}

// =====================================================
// Phase 2: 练习 API
// =====================================================

/**
 * 恢复练习
 * GET /playground/exercises/{exerciseId}/resume
 */
export function resumeExercise(exerciseId: string, lessonSlug: string) {
    return get<ExerciseResumeResponse>(
        `/playground/exercises/${exerciseId}/resume`,
        { lessonSlug },
    );
}

/**
 * 获取练习尝试列表
 * GET /playground/exercises/{exerciseId}/attempts
 */
export function listExerciseAttempts(
    exerciseId: string,
    lessonSlug: string,
    limit = 20,
) {
    return get<ExerciseAttemptSummary[]>(
        `/playground/exercises/${exerciseId}/attempts`,
        { lessonSlug, limit },
    );
}

/**
 * 获取练习统计
 * GET /playground/exercises/{exerciseId}/stats
 */
export interface ExerciseStats {
    totalAttempts: number;
    hasPassed: boolean;
    lastPassedAt: string | null;
    recentErrors: Record<string, number>;
}

export function getExerciseStats(exerciseId: string, lessonSlug: string) {
    return get<ExerciseStats>(
        `/playground/exercises/${exerciseId}/stats`,
        { lessonSlug },
    );
}
