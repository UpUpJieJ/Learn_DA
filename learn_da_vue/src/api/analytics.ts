import { post } from "./index";
import type { EventTrackRequest, EventTrackResponse } from "@/types/api";

// =====================================================
// 行为事件采集
// =====================================================

/**
 * 上报学习行为事件
 *
 * 这是学习状态唯一写入口：完成 / 撤销 / 开始统一走这里，由后端同事务联动
 * LearnerState 投影。改版 P4 起「学习报告」页改为读 `/workspace/report`，
 * 旧的 Dashboard 取数函数（home-stats / user-profile / user-lesson-stats /
 * daily-trend / category-progress / practice-stats）已全部删除。
 */
export function trackEvent(data: EventTrackRequest) {
    return post<EventTrackResponse>("/analytics/track", data);
}
