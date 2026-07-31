import { get } from "./index";
import type { RecommendationResponse } from "@/types/api";

/**
 * 获取用户的下一步学习建议
 * 完成状态由服务器端 Learner State 提供，不再需要客户端传入
 */
export async function getRecommendations(params: {
  currentLesson?: string;
}): Promise<RecommendationResponse> {
  return get<RecommendationResponse>("/recommendations", {
    current_lesson: params.currentLesson,
  });
}
