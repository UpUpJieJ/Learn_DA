import { post } from "@/api/index";
import type { ExecuteRequest, ExecuteResponse } from "@/types/api";

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
