import { get } from '@/api/index'
import type { LessonDetail } from '@/types/api'

/** Workspace lesson prose; task state is read from /workspace. */
export function fetchLessonBySlug(slug: string) {
  return get<LessonDetail>(`/lessons/${slug}`)
}
