import { get, post } from "./index";
import type {
    EventTrackRequest,
    EventTrackResponse,
    CodeSnapshotRequest,
    CodeSnapshotResponse,
    CodeSnapshotPage,
    HomeStats,
    UserProfile,
    UserLessonStats,
    DailyTrendItem,
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

/** 获取代码快照列表（分页） */
export function fetchCodeSnapshots(lessonSlug?: string, page: number = 1, pageSize: number = 20) {
    return get<CodeSnapshotPage>("/analytics/snapshots", {
        ...(lessonSlug ? { lessonSlug } : {}),
        page,
        page_size: pageSize,
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
export function fetchUserProfile() {
    return get<UserProfile>("/analytics/user-profile");
}

/** 获取用户课程统计 */
export function fetchUserLessonStats() {
    return get<UserLessonStats>("/analytics/user-lesson-stats");
}

/** 获取每日趋势 */
export function fetchDailyTrend(days: number = 30) {
    return get<DailyTrendItem[]>("/analytics/daily-trend", { days });
}

/** 获取分类进度 */
export function fetchCategoryProgress() {
    return get<CategoryProgress>("/analytics/category-progress");
}
