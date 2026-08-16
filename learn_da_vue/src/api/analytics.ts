import { get, post } from "./index";
import type {
    EventTrackRequest,
    EventTrackResponse,
    HomeStats,
    UserProfile,
    UserLessonStats,
    DailyTrendItem,
    CategoryProgress,
    PracticeStats,
} from "@/types/api";

// =====================================================
// 行为事件采集
// =====================================================

/** 上报学习行为事件 */
export function trackEvent(data: EventTrackRequest) {
    return post<EventTrackResponse>("/analytics/track", data);
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

/** 获取可验证练习指标 */
export function fetchPracticeStats() {
    return get<PracticeStats>("/analytics/practice-stats");
}
