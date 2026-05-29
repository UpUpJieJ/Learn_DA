// =====================================================
// 通用 API 响应结构（与后端 StdResp 对齐）
// =====================================================

export interface ApiResponse<T = unknown> {
    code: number;
    msg: string;
    data: T;
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
// 本地状态
// =====================================================

export interface LocalPreferences {
    editorTheme: "vs-dark" | "light";
    editorFontSize: number;
    language: "zh" | "en";
}

export interface LearningProgress {
    completedLessons: string[];
    lastVisitedSlug: string | null;
    updatedAt: number;
}

export interface PlaygroundDraft {
    code: string;
    language: "python" | "sql";
    updatedAt: number;
}

export type PlaygroundDrafts = Record<string, PlaygroundDraft>;

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

// =====================================================
// Analytics 模块
// =====================================================

/** 行为事件类型 */
export type EventType =
    | "code_run"
    | "code_save"
    | "lesson_complete"
    | "ai_help"
    | "lesson_start";

/** 事件上报请求 */
export interface EventTrackRequest {
    visitorId: string;
    eventType: EventType;
    lessonSlug?: string;
    durationSeconds?: number;
}

/** 事件上报响应 */
export interface EventTrackResponse {
    recorded: boolean;
}

/** 代码快照请求 */
export interface CodeSnapshotRequest {
    visitorId: string;
    lessonSlug?: string;
    code: string;
    language?: string;
    description?: string;
}

/** 代码快照响应 */
export interface CodeSnapshotResponse {
    snapshotId: number;
    version: number;
}

/** 代码快照列表项 */
export interface CodeSnapshotItem {
    id: number;
    lessonSlug?: string;
    code: string;
    language: string;
    version: number;
    description?: string;
    createdTime: string;
}

/** 首页统计数据 */
export interface HomeStats {
    totalLearners: number;
    todayActiveUsers: number;
    totalCodeRuns: number;
    totalLessons: number;
}

/** 用户画像 */
export interface UserProfile {
    totalLearningMinutes: number;
    lessonsCompleted: number;
    codeRuns: number;
    aiHelps: number;
    currentStreak: number;
    longestStreak: number;
    lastActiveDate: string | null;
    polarsScore: number;
    duckdbScore: number;
    sqlScore: number;
    dataProcessingScore: number;
    apiMasteryScore: number;
}

/** 课程学习统计 */
export interface LessonStat {
    slug: string;
    codeRuns: number;
    aiHelps: number;
    completed: boolean;
}

/** 用户课程统计 */
export interface UserLessonStats {
    completedLessons: string[];
    lessonDetails: LessonStat[];
}

/** 每日趋势数据 */
export interface DailyTrendItem {
    date: string;
    activeUsers: number;
    codeRuns: number;
    lessonsCompleted: number;
    aiHelps: number;
}

/** 推荐课程响应 */
export interface RecommendedLessonsResponse {
    recommended: LessonSummary | null;
    completedCount: number;
    totalCount: number;
}

/** 分类进度 */
export interface CategoryProgress {
    polars: number;
    duckdb: number;
    combined: number;
}
