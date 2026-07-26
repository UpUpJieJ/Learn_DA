import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { EventType, LearnerProgressSummary } from '@/types/api'
import { fetchLearnerProgress } from '@/api/learnerState'
import { trackEvent } from '@/api/analytics'

// =====================================================
// localStorage 缓存（降级存储）
// 阶段 1：localStorage 降级为离线缓存，服务器 Learner State 是唯一权威。
// =====================================================

const CACHE_KEY = 'learn_da:learner_progress'

function loadCache(): LearnerProgressSummary | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as LearnerProgressSummary
  } catch {
    return null
  }
}

function saveCache(data: LearnerProgressSummary): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data))
  } catch {
    // 静默失败
  }
}

/** 幂等键。crypto.randomUUID 只在安全上下文可用，降级为时间戳 + 随机数。 */
function newEventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** 待重试的状态变更事件。eventId 随 op 一起保存，重试不会重复计数。 */
interface PendingOp {
  eventType: EventType
  slug: string
  eventId: string
}

// =====================================================
// Learner State Store
//
// 写路径：所有状态变更统一通过 /analytics/track 上报，后端在同一事务内
// 联动 LearnerState 投影。本 store 只做乐观更新 + 失败重试队列。
// =====================================================

export const useLearnerStateStore = defineStore('learnerState', () => {
  // ---- 状态 ----
  const progress = ref<LearnerProgressSummary | null>(loadCache())
  const isSynced = ref(false)
  const lastSyncAt = ref<number>(0)
  const pendingOps = ref<PendingOp[]>([])

  // ---- Computed ----
  const completedLessons = computed<string[]>(() => {
    return progress.value?.completedLessons ?? []
  })

  const lastVisitedSlug = computed<string | null>(() => {
    return progress.value?.lastVisitedSlug ?? null
  })

  const totalCompleted = computed<number>(() => {
    return progress.value?.totalCompleted ?? 0
  })

  // ---- 查询方法 ----
  function isLessonCompleted(slug: string): boolean {
    return completedLessons.value.includes(slug)
  }

  // ---- 同步方法 ----
  async function syncFromServer(): Promise<void> {
    // 先补发离线期间积压的变更，再拉取服务器投影，
    // 否则服务器数据会覆盖掉尚未送达的本地乐观状态。
    await flushPendingOps()
    try {
      const data = await fetchLearnerProgress()
      progress.value = data
      isSynced.value = true
      lastSyncAt.value = Date.now()
      saveCache(data)
    } catch {
      // 服务器不可用，使用 localStorage 缓存降级
      isSynced.value = false
    }
  }

  // ---- 写操作 ----

  /**
   * 上报一个状态变更事件；失败时入队等待下次 sync 重试。
   * 返回是否已成功送达服务器。
   */
  async function emitStateEvent(
    eventType: EventType,
    slug: string,
  ): Promise<boolean> {
    const op: PendingOp = { eventType, slug, eventId: newEventId() }
    try {
      await trackEvent({
        eventType: op.eventType,
        lessonSlug: op.slug,
        eventId: op.eventId,
      })
      return true
    } catch {
      pendingOps.value.push(op)
      return false
    }
  }

  async function completeLesson(slug: string): Promise<boolean> {
    updateLocalComplete(slug, true)
    return emitStateEvent('lesson_complete', slug)
  }

  async function uncompleteLesson(slug: string): Promise<boolean> {
    updateLocalComplete(slug, false)
    return emitStateEvent('lesson_uncomplete', slug)
  }

  async function recordLessonStart(slug: string): Promise<boolean> {
    if (progress.value) {
      progress.value.lastVisitedSlug = slug
      saveCache(progress.value)
    }
    return emitStateEvent('lesson_start', slug)
  }

  // ---- 内部方法 ----
  function updateLocalComplete(slug: string, completed: boolean) {
    if (!progress.value) {
      progress.value = {
        completedLessons: [],
        lastVisitedSlug: null,
        lessonDetails: [],
        totalCompleted: 0,
        totalStarted: 0,
      }
    }
    const list = progress.value.completedLessons
    if (completed && !list.includes(slug)) {
      list.push(slug)
    } else if (!completed) {
      progress.value.completedLessons = list.filter((s) => s !== slug)
    }
    progress.value.totalCompleted = progress.value.completedLessons.length
    saveCache(progress.value)
  }

  async function flushPendingOps(): Promise<void> {
    const ops = [...pendingOps.value]
    pendingOps.value = []
    for (const op of ops) {
      try {
        // 复用原 eventId：后端按 event_id 去重，重试不会重复计入画像与投影
        await trackEvent({
          eventType: op.eventType,
          lessonSlug: op.slug,
          eventId: op.eventId,
        })
      } catch {
        pendingOps.value.push(op)
      }
    }
  }

  // ---- 返回 ----
  return {
    // state
    progress,
    isSynced,
    lastSyncAt,

    // computed
    completedLessons,
    lastVisitedSlug,
    totalCompleted,

    // methods
    isLessonCompleted,
    syncFromServer,
    completeLesson,
    uncompleteLesson,
    recordLessonStart,
  }
})
