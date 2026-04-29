import { get } from '@/api/index'
import type {
  LessonSummary,
  LessonDetail,
  PaginatedResponse,
  LessonCategory,
  LessonDifficulty,
} from '@/types/api'

// =====================================================
// 课程列表查询参数
// =====================================================

export interface LessonListParams {
  page?: number
  pageSize?: number
  category?: LessonCategory
  difficulty?: LessonDifficulty
  keyword?: string
}

// =====================================================
// 课程 API
// =====================================================

/**
 * 获取课程列表（支持分页、分类、难度过滤）
 */
export function fetchLessons(params?: LessonListParams) {
  return get<PaginatedResponse<LessonSummary>>('/lessons', params as Record<string, unknown>)
}

/**
 * 获取所有课程（不分页，用于侧边栏目录）
 */
export function fetchAllLessons(category?: LessonCategory) {
  return get<LessonSummary[]>('/lessons/all', category ? { category } : undefined)
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

/**
 * 获取推荐课程（根据最后学习位置推荐下一节）
 */
export function fetchRecommendedLessons(lastSlug?: string) {
  return get<LessonSummary[]>('/lessons/recommended', lastSlug ? { lastSlug } : undefined)
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
