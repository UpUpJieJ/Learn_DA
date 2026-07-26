import { get } from "./index";
import type { LearnerProgressSummary } from "@/types/api";

// =====================================================
// 阶段 1：统一学习事实 - Learner State API（只读）
//
// 状态变更不在这里：完成 / 撤销 / 开始统一通过 `trackEvent` 上报到
// /analytics/track，由后端在同一事务内联动 LearnerState 投影，
// 避免事件日志与状态投影分裂成两条写路径。
//
// 身份遵循阶段 0 签名匿名 session 约定，visitor_id 由 session cookie 注入，
// 前端通过 withCredentials 携带 cookie，不需要传 visitorId。
// =====================================================

/** 获取学习者完整进度投影 */
export function fetchLearnerProgress() {
  return get<LearnerProgressSummary>("/learner-state/progress");
}
