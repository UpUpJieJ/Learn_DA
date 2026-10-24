import { post } from "@/api/index";
import type { ExecuteRequest, ExecuteResponse } from "@/types/api";

// =====================================================
// Playground API
// =====================================================

/**
 * 执行代码（提交到沙箱运行）
 * POST /playground/execute
 *
 * 只保留自由实验室（`/lab`）需要的普通执行分支：改版 M4 起课程练习走
 * `/workspace/sessions/{id}/cells/{cellId}/run`，练习时代的
 * `lessonSlug` / `exerciseId` 入参与 `/playground/format`、
 * `/playground/exercises/*` 三个端点已随旧链路下线。
 */
export function executeCode(payload: ExecuteRequest) {
    return post<ExecuteResponse>("/playground/execute", {
        code: payload.code,
        language: payload.language ?? "python",
        requestId: payload.requestId,
        source: payload.source,
    });
}
