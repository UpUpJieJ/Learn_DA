import { get } from "./index";
import type { RecommendationResponse } from "@/types/api";

/**
 * 获取用户的下一步学习建议
 */
export async function getRecommendations(params: {
  visitorId: string;
  completedLessons: string[]; // slug 列表
  currentLesson?: string; // 当前课程 slug
}): Promise<RecommendationResponse> {
  return get<RecommendationResponse>("/learning/recommendations", {
    visitor_id: params.visitorId,
    completed_lessons: params.completedLessons.join(","),
    current_lesson: params.currentLesson,
  });
}
