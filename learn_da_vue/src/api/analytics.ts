import { get, post } from "./index";
import type {
    EventTrackRequest,
    EventTrackResponse,
    CodeSnapshotRequest,
    CodeSnapshotResponse,
    CodeSnapshotItem,
    HomeStats,
    UserProfile,
    UserLessonStats,
    DailyTrendItem,
    RecommendedLessonsResponse,
    CategoryProgress,
} from "@/types/api";

// =====================================================
// 行为事件采集
// =====================================================

/** 上报学习行为事件 */
export function trackEvent(data: EventTrackRequest) {
    return post<EventTrackResponse>("/analytics/track", data);
}

/** 保存代码快照 */
export function saveCodeSnapshot(data: CodeSnapshotRequest) {
    return post<CodeSnapshotResponse>("/analytics/snapshot", data);
}

/** 获取代码快照列表 */
export function fetchCodeSnapshots(visitorId: string, lessonSlug?: string) {
    return get<CodeSnapshotItem[]>("/analytics/snapshots", {
        visitorId,
        ...(lessonSlug ? { lessonSlug } : {}),
    });
}

// =====================================================
// 首页统计
// =====================================================

/** 获取首页统计数据 */
export function fetchHomeStats() {
    return get<HomeStats>("/analytics/home-stats");
}

// =====================================================
// Dashboard 数据
// =====================================================

/** 获取用户画像 */
export function fetchUserProfile(visitorId: string) {
    return get<UserProfile>("/analytics/user-profile", { visitorId });
}

/** 获取用户课程统计 */
export function fetchUserLessonStats(visitorId: string) {
    return get<UserLessonStats>("/analytics/user-lesson-stats", { visitorId });
}

/** 获取每日趋势 */
export function fetchDailyTrend(days: number = 30) {
    return get<DailyTrendItem[]>("/analytics/daily-trend", { days });
}

/** 获取推荐课程 */
export function fetchRecommendedLessons(visitorId: string) {
    return get<RecommendedLessonsResponse>("/analytics/recommended-lessons", {
        visitorId,
    });
}

/** 获取分类进度 */
export function fetchCategoryProgress(visitorId: string) {
    return get<CategoryProgress>("/analytics/category-progress", { visitorId });
}
