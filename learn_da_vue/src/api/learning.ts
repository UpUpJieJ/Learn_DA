import { get } from '@/api/index'
import type {
  LessonSummary,
  LessonDetail,
  LessonCategory,
  LessonDifficulty,
} from '@/types/api'

// =====================================================
// 课程列表查询参数
// =====================================================

export interface LessonListParams {
  category?: LessonCategory
  difficulty?: LessonDifficulty
  keyword?: string
}

// =====================================================
// 课程 API
// =====================================================

/**
 * 获取课程列表（支持分类、难度、关键词过滤）
 */
export function fetchLessons(params?: LessonListParams) {
  return get<LessonSummary[]>('/lessons', params as Record<string, unknown>)
}

/**
 * 根据 slug 获取课程详情
 */
export function fetchLessonBySlug(slug: string) {
  return get<LessonDetail>(`/lessons/${slug}`)
}

/**
 * 获取课程分类统计（每个分类下的课程数）
 */
export interface CategoryStat {
  category: LessonCategory
  label: string
  count: number
}

export function fetchCategoryStats() {
  return get<CategoryStat[]>('/lessons/categories')
}

// =====================================================
// 示例代码 API
// =====================================================

import type { ExampleSummary, ExampleDetail } from '@/types/api'

/**
 * 获取所有示例代码列表
 */
export function fetchExamples() {
  return get<ExampleSummary[]>('/examples')
}

/**
 * 根据 slug 获取示例代码详情
 */
export function fetchExample(slug: string) {
  return get<ExampleDetail>(`/examples/${slug}`)
}
