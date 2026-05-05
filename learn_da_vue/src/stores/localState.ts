import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { LocalPreferences, LearningProgress } from '@/types/api'

// =====================================================
// 本地存储 Key 常量
// =====================================================

const STORAGE_KEY_PREFERENCES = 'learn_da:preferences'
const STORAGE_KEY_PROGRESS = 'learn_da:progress'

// =====================================================
// 本地存储工具函数
// =====================================================

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    console.warn(`[LocalStateStore] 读取本地存储失败: ${key}`)
    return fallback
  }
}

function saveToStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    console.warn(`[LocalStateStore] 写入本地存储失败: ${key}`)
  }
}

// =====================================================
// 默认值
// =====================================================

const DEFAULT_PREFERENCES: LocalPreferences = {
  editorTheme: 'vs-dark',
  editorFontSize: 14,
  language: 'zh',
}

const DEFAULT_PROGRESS: LearningProgress = {
  completedLessons: [],
  lastVisitedSlug: null,
  updatedAt: Date.now(),
}

// =====================================================
// Local State Store
// =====================================================

export const useLocalStateStore = defineStore('localState', () => {
  // ---- 本地偏好设置（持久化） ----
  const preferences = ref<LocalPreferences>(
    loadFromStorage(STORAGE_KEY_PREFERENCES, DEFAULT_PREFERENCES),
  )

  // ---- 本地学习进度（持久化） ----
  const progress = ref<LearningProgress>(
    loadFromStorage(STORAGE_KEY_PROGRESS, DEFAULT_PROGRESS),
  )

  // ---- Agent 面板展开状态（非持久化，页面级状态） ----
  const isAgentOpen = ref(false)

  // ---- 侧边栏展开状态（非持久化） ----
  const isSidebarOpen = ref(true)

  // =====================================================
  // 自动持久化：监听变化写入 localStorage
  // =====================================================

  watch(
    preferences,
    (val) => saveToStorage(STORAGE_KEY_PREFERENCES, val),
    { deep: true },
  )

  watch(
    progress,
    (val) => saveToStorage(STORAGE_KEY_PROGRESS, val),
    { deep: true },
  )

  // =====================================================
  // Computed
  // =====================================================

  /** 已完成课程数量 */
  const completedCount = computed(
    () => progress.value.completedLessons.length,
  )

  /** 是否完成某节课 */
  function isLessonCompleted(slug: string): boolean {
    return progress.value.completedLessons.includes(slug)
  }

  /** 编辑器主题 */
  const editorTheme = computed(() => preferences.value.editorTheme)

  /** 编辑器字体大小 */
  const editorFontSize = computed(() => preferences.value.editorFontSize)

  /** 当前界面语言 */
  const uiLanguage = computed(() => preferences.value.language)

  // =====================================================
  // Actions - 偏好设置
  // =====================================================

  /**
   * 切换编辑器主题（亮色/暗色）
   */
  function toggleEditorTheme() {
    preferences.value.editorTheme =
      preferences.value.editorTheme === 'vs-dark' ? 'light' : 'vs-dark'
  }

  /**
   * 设置编辑器主题
   */
  function setEditorTheme(theme: LocalPreferences['editorTheme']) {
    preferences.value.editorTheme = theme
  }

  /**
   * 设置编辑器字体大小（限制范围 10-24）
   */
  function setEditorFontSize(size: number) {
    preferences.value.editorFontSize = Math.min(24, Math.max(10, size))
  }

  /**
   * 增大字体
   */
  function increaseFontSize() {
    setEditorFontSize(preferences.value.editorFontSize + 1)
  }

  /**
   * 减小字体
   */
  function decreaseFontSize() {
    setEditorFontSize(preferences.value.editorFontSize - 1)
  }

  /**
   * 设置界面语言
   */
  function setLanguage(lang: LocalPreferences['language']) {
    preferences.value.language = lang
  }

  /**
   * 重置偏好设置为默认值
   */
  function resetPreferences() {
    preferences.value = { ...DEFAULT_PREFERENCES }
  }

  // =====================================================
  // Actions - 学习进度
  // =====================================================

  /**
   * 标记某节课为已完成
   */
  function markLessonCompleted(slug: string) {
    if (!progress.value.completedLessons.includes(slug)) {
      progress.value.completedLessons.push(slug)
      progress.value.updatedAt = Date.now()
    }
  }

  /**
   * 取消某节课的完成状态
   */
  function unmarkLessonCompleted(slug: string) {
    progress.value.completedLessons = progress.value.completedLessons.filter(
      (s) => s !== slug,
    )
    progress.value.updatedAt = Date.now()
  }

  /**
   * 切换某节课的完成状态
   */
  function toggleLessonCompleted(slug: string) {
    if (isLessonCompleted(slug)) {
      unmarkLessonCompleted(slug)
    } else {
      markLessonCompleted(slug)
    }
  }

  /**
   * 记录最后访问的课程 slug
   */
  function setLastVisitedLesson(slug: string) {
    progress.value.lastVisitedSlug = slug
    progress.value.updatedAt = Date.now()
  }

  /**
   * 重置所有学习进度
   */
  function resetProgress() {
    progress.value = { ...DEFAULT_PROGRESS, updatedAt: Date.now() }
  }

  // =====================================================
  // Actions - UI 状态
  // =====================================================

  /** 打开 Agent 面板 */
  function openAgent() {
    isAgentOpen.value = true
  }

  /** 关闭 Agent 面板 */
  function closeAgent() {
    isAgentOpen.value = false
  }

  /** 切换 Agent 面板开关 */
  function toggleAgent() {
    isAgentOpen.value = !isAgentOpen.value
  }

  /** 切换侧边栏开关 */
  function toggleSidebar() {
    isSidebarOpen.value = !isSidebarOpen.value
  }

  /** 设置侧边栏状态 */
  function setSidebarOpen(open: boolean) {
    isSidebarOpen.value = open
  }

  // =====================================================
  // 返回
  // =====================================================

  return {
    // state
    preferences,
    progress,
    isAgentOpen,
    isSidebarOpen,

    // computed
    completedCount,
    editorTheme,
    editorFontSize,
    uiLanguage,

    // computed functions
    isLessonCompleted,

    // actions - preferences
    toggleEditorTheme,
    setEditorTheme,
    setEditorFontSize,
    increaseFontSize,
    decreaseFontSize,
    setLanguage,
    resetPreferences,

    // actions - progress
    markLessonCompleted,
    unmarkLessonCompleted,
    toggleLessonCompleted,
    setLastVisitedLesson,
    resetProgress,

    // actions - ui
    openAgent,
    closeAgent,
    toggleAgent,
    toggleSidebar,
    setSidebarOpen,
  }
})
