// =====================================================
// 通用 API 响应结构（与后端 StdResp 对齐）
// =====================================================

export interface ApiResponse<T = unknown> {
    code: number;
    msg: string;
    data: T;
}

/** 分页元数据 */
export interface PaginationMeta {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
}

/** 带分页的响应 */
export interface PaginatedResponse<T> {
    items: T[];
    meta: PaginationMeta;
}

// =====================================================
// 学习模块 - 课程相关
// =====================================================

export type LessonDifficulty = "beginner" | "intermediate" | "advanced";
export type LessonCategory = "polars" | "duckdb" | "combined";

export interface LessonSummary {
    id: number;
    slug: string;
    title: string;
    description: string;
    category: LessonCategory;
    difficulty: LessonDifficulty;
    estimatedMinutes: number;
    order: number;
    tags: string[];
}

export interface LessonDetail extends LessonSummary {
    content: string;
    codeExample: string;
    prevLesson: LessonNav | null;
    nextLesson: LessonNav | null;
}

export interface LessonNav {
    slug: string;
    title: string;
}

// =====================================================
// Playground 模块
// =====================================================

export interface ExecuteRequest {
    code: string;
    language?: "python" | "sql";
}

export type ExecuteStatus = "success" | "error" | "timeout" | "mocked";
export type ExecuteResultType = "text" | "dataframe" | "error";

export type DataFrameCell = string | number | boolean | null;

export interface DataFrameResult {
    columns: string[];
    rows: Record<string, DataFrameCell>[];
    rowCount: number;
    truncated: boolean;
}

export interface ExecuteResponse {
    status: ExecuteStatus;
    stdout: string;
    stderr: string;
    executionTime: number;
    usedSandbox: string;
    resultType: ExecuteResultType;
    dataframe: DataFrameResult | null;
}

// =====================================================
// AI Agent 模块
// =====================================================

/** 对话角色 */
export type MessageRole = "user" | "assistant" | "system";

/** 单条对话消息 */
export interface ChatMessage {
    id: string;
    role: MessageRole;
    content: string;
    timestamp: number;
    isStreaming?: boolean;
}

/** Agent 上下文（可携带当前代码 / 错误） */
export interface AgentContext {
    currentCode?: string;
    lastError?: string;
    currentLesson?: string;
    lessonTitle?: string;
    lessonCategory?: LessonCategory;
    lessonContent?: string;
    stdout?: string;
    stderr?: string;
}

export type AgentToolName =
    | "generate_example_code"
    | "generate_exercise"
    | "fix_code"
    | "explain_code"
    | "suggest_next_step"
    | "general_chat";

export interface AgentRouteInfo {
    toolName: AgentToolName;
    confidence: number;
    reason: string;
    matchedKeyword?: string | null;
}

export interface AgentResultSection {
    title: string;
    content: string;
}

export interface AgentCodeBlock {
    language?: string | null;
    code: string;
}

export interface AgentStructuredResult {
    kind: AgentToolName;
    sections: AgentResultSection[];
    codeBlocks: AgentCodeBlock[];
}

/** Agent 对话请求 */
export interface AgentChatRequest {
    message: string;
    history: Pick<ChatMessage, "role" | "content">[];
    context?: AgentContext;
}

/** Agent 对话响应 */
export interface AgentChatResponse {
    reply: string;
    suggestedCode?: string;
    references?: string[];
    toolName?: AgentToolName;
    model?: string;
    usedFallback?: boolean;
    route?: AgentRouteInfo | null;
    structuredResult?: AgentStructuredResult | null;
}

// =====================================================
// 用户 / 本地状态
// =====================================================

export interface UserPreferences {
    editorTheme: "vs-dark" | "light";
    editorFontSize: number;
    language: "zh" | "en";
}

export interface LearningProgress {
    completedLessons: string[];
    lastVisitedSlug: string | null;
    updatedAt: number;
}

// =====================================================
// 学习模块 - 示例代码相关
// =====================================================

export interface ExampleSummary {
    slug: string;
    title: string;
    topic: string;
    summary: string;
}

export interface ExampleDetail extends ExampleSummary {
    code: string;
    expectedOutput: string;
}
