import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchProgress, type ProgressPayload } from '@/api/workspace'

/** Navigation is a read-only projection of authoritative workspace progress. */
export const useLearnerStateStore = defineStore('learnerState', () => {
  const progress = ref<ProgressPayload | null>(null)
  const isSynced = ref(false)
  let generation = 0
  const completedLessons = computed(() => progress.value?.lessons.filter((lesson) => lesson.status === 'completed').map((lesson) => lesson.lessonSlug) ?? [])
  const totalCompleted = computed(() => completedLessons.value.length)
  const lastVisitedSlug = computed(() => [...(progress.value?.lessons ?? [])]
    .filter((lesson) => lesson.lastActivityAt)
    .sort((left, right) => String(right.lastActivityAt).localeCompare(String(left.lastActivityAt)))[0]?.lessonSlug ?? null)
  async function syncFromServer(): Promise<void> {
    const requestGeneration = ++generation
    try {
      const data = await fetchProgress()
      if (requestGeneration !== generation) return
      progress.value = data
      isSynced.value = true
    } catch {
      if (requestGeneration === generation) isSynced.value = false
    }
  }

  return { progress, isSynced, completedLessons, totalCompleted, lastVisitedSlug, syncFromServer }
})
