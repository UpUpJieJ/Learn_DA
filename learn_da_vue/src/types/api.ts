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
    /** Phase 2: 正式练习定义（可选，有则优先于 practiceObjective） */
    exercise?: ExerciseDefinition | null;
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
    /** Phase 2: 练习执行（可选） */
    lessonSlug?: string;
    exerciseId?: string;
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
    /** Phase 2: 练习执行结果 */
    attemptId?: number;
    verification?: ExerciseVerification | null;
}

/** Phase 2: 练习验证结果 */
export interface ExerciseVerification {
    status: VerificationStatus;
    failureReason?: string | null;
    validatorType?: string | null;
}

export type VerificationStatus = "passed" | "failed" | "unverifiable" | "not_run";

/** Phase 2: 练习定义 */
export interface ExerciseDefinition {
    id: string;
    title: string;
    language: string;
    starterCode: string;
    objective: string;
    hints: string[];
    validator: {
        type: string;
        expected?: string | string[] | Record<string, unknown> | null;
    };
}

/** Phase 2: 练习尝试摘要 */
export interface ExerciseAttemptSummary {
    id: number;
    attemptId: number;
    exerciseId: string;
    lessonSlug: string;
    executionStatus: ExecuteStatus;
    verificationStatus: VerificationStatus;
    failureReason?: string | null;
    createdTime?: string | null;
    durationMs?: number | null;
}

/** Phase 2: 练习恢复响应 */
export interface ExerciseResumeResponse {
    exerciseId: string;
    lessonSlug: string;
    code: string;
    language: string;
    isResumed: boolean;
    lastAttempt?: ExerciseAttemptSummary | null;
    exerciseTitle: string;
    objective: string;
    hints: string[];
    starterCode: string;
}

/** Phase 2: Dashboard 可验证练习指标 */
export interface PracticeStats {
    passedExercises: number;
    totalAttempts: number;
    recentAttempts: ExerciseAttemptSummary[];
    resumableExercises: Array<{
        exerciseId: string;
        lessonSlug: string;
        lastStatus: VerificationStatus;
    }>;
    errorCategories: Record<string, number>;
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

/** 阶段 3：下一步动作（服务端权威决定） */
export type TeachingNextAction =
    | "inspect_result"
    | "retry_exercise"
    | "confirm_lesson"
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

export interface PlaygroundDraft {
    code: string;
    language: "python" | "sql";
    updatedAt: number;
}

export type PlaygroundDrafts = Record<string, PlaygroundDraft>;

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

/** 分类进度 */
export type CategoryProgress = Record<string, number>;

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

// =====================================================
// Phase 3: 学习建议系统
// =====================================================

/** 建议类型 */
export type RecommendationType =
    | "next_lesson" // 顺学建议：继续下一课
    | "review_lesson" // 回补建议：回看前置课
    | "branch_path" // 分支建议：切换学习路径
    | "resume_session"; // 回流建议：恢复中断的学习

/** 建议理由代码 */
export type RecommendationReasonCode =
    | "sequential_progress" // 顺序推进
    | "prerequisite_weak" // 前置知识薄弱
    | "stuck_on_practice" // 练习卡住
    | "path_completed" // 路径完成
    | "long_absence" // 长时间未学习
    | "incomplete_practice"; // 未完成的练习

/** 学习建议 */
export interface LearningRecommendation {
    type: RecommendationType;
    targetSlug: string;
    targetTitle: string;
    reason: string;
    reasonCode: RecommendationReasonCode;
    priority: number;
    actionLabel: string;
    context?: Record<string, unknown> | null;
}

/** 建议响应 */
export interface RecommendationResponse {
    primary: LearningRecommendation | null;
    alternatives: LearningRecommendation[];
}
