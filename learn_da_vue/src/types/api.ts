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
export type LessonCategory = string;

export interface PlatformCatalog {
    platform: {
        name?: string;
        title?: string;
        subtitle?: string;
    };
    topics: CatalogTopic[];
    tracks: CatalogTrack[];
}

export interface CatalogTopic {
    key: string;
    label: string;
    description?: string;
    color?: string;
}

export interface CatalogTrack {
    key: string;
    topic: string;
    label: string;
    description?: string;
    startLesson?: string;
    category?: string;
    color?: string;
}

export interface LessonSummary {
    id: number;
    slug: string;
    title: string;
    description: string;
    topic: string;
    category: LessonCategory;
    difficulty: LessonDifficulty;
    estimatedMinutes: number;
    order: number;
    tags: string[];
    track: string;
    /** 改版 M1：这课是否带可交互工作区（多 cell + 任务） */
    hasWorkspace?: boolean;
}

export interface LessonDetail extends LessonSummary {
    content: string;
    codeExample: string;
    prevLesson: LessonNav | null;
    nextLesson: LessonNav | null;
    /** Phase 2: 训练目标（可选，无则降级为纯内容展示） */
    practiceObjective?: string;
    /** Phase 2: 完成标准（可选） */
    completionCriteria?: string[];
    prerequisites?: string[];
    recommendedNext?: string[];
    skillTags?: string[];
    isReviewFriendly?: boolean;
    isBranchPoint?: boolean;
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
    requestId?: string;
    source?: ExecutionSource;
}

export type ExecutionSource = "playground" | "agent_suggested";

export type ExecuteStatus = "success" | "error" | "timeout" | "rejected" | "unavailable";
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
    usedSandbox?: string;
    resultType: ExecuteResultType;
    dataframe: DataFrameResult | null;
    requestId?: string;
    executionId?: string;
    source?: ExecutionSource;
    errorType?: string | null;
    outputTruncated?: boolean;
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
    /** 阶段 3：该 assistant 消息附带的结构化教学反馈 */
    teachingFeedback?: TeachingFeedback | null;
    /** AgentInteraction 主键，用于提交用户反馈 */
    interactionId?: number | null;
    feedback?: AgentFeedbackValue | null;
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
    /** 阶段 3：可选 attempt 定位线索 */
    attemptId?: number;
    /** 改版 M4：当前任务（工作区 taskId），证据按任务定位 */
    currentTask?: string;
    /** 改版 E1：工作区会话与聚焦单元格，便于工具按会话定位 */
    sessionId?: number;
    cellId?: string;
    /** 改版 E1：最近的单元格执行摘要（客户端自报，仅供排错参考） */
    recentRuns?: AgentRecentRun[];
}

/**
 * 最近一次单元格执行的摘要。
 * 刻意不含完整代码与完整 stdout —— 判定权威在服务端证据，这里只帮模型定位。
 */
export interface AgentRecentRun {
    cellId: string;
    status: string;
    errorType?: string | null;
    /** stderr 首行（后端再截 400 字符） */
    stderrFirstLine?: string | null;
    /** 本次未通过的断言 id（后端限 8 条） */
    assertionsFailed?: string[];
}

/** Agent 对话请求 */
export interface AgentChatRequest {
    message: string;
    history: Pick<ChatMessage, "role" | "content">[];
    context?: AgentContext;
}

/** 阶段 3：教学反馈五态 */
export type TeachingState =
    | "execution_failed"
    | "verification_failed"
    | "passed_unconfirmed"
    | "unverifiable"
    | "no_evidence";

/** 阶段 3：下一步动作（服务端权威决定）
 *
 * ``next_task`` 取代了旧的 ``confirm_lesson``：改版 M4 起课程完成度由任务
 * 通过数推导，任务过了就直接去下一个任务，没有「确认完成本课」这一步。
 */
export type TeachingNextAction =
    | "inspect_result"
    | "retry_exercise"
    | "next_task"
    | "retry_later";

/** 阶段 3：结构化教学反馈 */
export interface TeachingFeedback {
    state: TeachingState;
    attemptId?: number | null;
    evidenceSummary: string;
    diagnosis: string;
    hintLevel: number;
    nextAction: TeachingNextAction;
}

/** Agent 对话响应 */
export interface AgentChatResponse {
    reply: string;
    suggestedCode?: string;
    references?: string[];
    model?: string;
    usedFallback?: boolean;
    /** 阶段 3：结构化教学反馈 */
    teachingFeedback?: TeachingFeedback | null;
    interactionId?: number | null;
}

export type AgentFeedbackValue = "helpful" | "not_helpful";

export interface AgentFeedbackResponse {
    recorded: boolean;
    interactionId: number;
}

// =====================================================
// 本地状态
// =====================================================

export interface LocalPreferences {
    editorTheme: "vs-dark" | "light";
    editorFontSize: number;
    language: "zh" | "en";
}

// =====================================================
// 学习模块 - 示例代码相关
// =====================================================

// =====================================================
// Analytics 模块
// =====================================================

/** 行为事件类型 */
export type EventType =
    | "code_run"
    | "code_save"
    | "lesson_complete"
    | "lesson_uncomplete"
    | "ai_help"
    | "lesson_start";

/**
 * 代码执行结果状态（仅 code_run 事件）。
 * 与 ExecuteStatus 保持同一组取值：上报时原样透传，不做归并，
 * 否则错误类型在服务端无法聚合。
 */
export type CodeRunStatus = ExecuteStatus;

/** 事件上报请求 */
export interface EventTrackRequest {
    eventType: EventType;
    lessonSlug?: string;
    durationSeconds?: number;
    /** 幂等键（前端生成 UUID），相同 eventId 重放不重复写入 */
    eventId?: string;
    /** 执行结果（仅 code_run）：success / error / timeout / rejected / unavailable */
    status?: CodeRunStatus;
}

/** 事件上报响应 */
export interface EventTrackResponse {
    recorded: boolean;
}

/** 代码快照请求 */
/** 代码快照响应 */
/** 代码快照列表项 */
/** 代码快照分页响应 */

// =====================================================
// 阶段 1：统一学习事实 - Learner State
// =====================================================

/** 单课进度详情 */
export interface LessonProgressDetail {
    lessonSlug: string;
    status: string; // started / completed / uncompleted
    completedAt: string | null;
    lastActivityAt: string | null;
    attemptCount: number;
    successCount: number;
    errorCount: number;
}

/** 学习者完整进度投影 */
export interface LearnerProgressSummary {
    completedLessons: string[];
    lastVisitedSlug: string | null;
    lessonDetails: LessonProgressDetail[];
    totalCompleted: number;
    totalStarted: number;
}

// 状态变更没有专用响应体：完成 / 撤销 / 开始统一走 EventTrackRequest
// 上报到 /analytics/track，由后端同事务联动 LearnerState 投影。
//
// 说明：Phase 3 的「学习建议」类型（RecommendationType / LearningRecommendation /
// RecommendationResponse）已随前端 `api/recommendation.ts` 一起删除 ——
// `/api/v1/recommendations` 后端仍在，但改版 P4 后前端改为读
// `/workspace/progress` 与 `/workspace/report`，没有任何页面消费建议接口。

