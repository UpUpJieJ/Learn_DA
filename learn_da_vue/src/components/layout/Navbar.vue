<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLocalStateStore } from '@/stores/localState'
import { useLearnerStateStore } from '@/stores/learnerState'
import { platformCopy } from '@/lib/learningTracks'

const router = useRouter()
const route = useRoute()
const localStateStore = useLocalStateStore()
const learnerStateStore = useLearnerStateStore()

// =====================================================
// 导航项配置
// =====================================================

const navItems = [
  {
    name: '首页',
    path: '/',
    icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0
            01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />`,
    exact: true,
  },
  {
    name: '课程',
    path: '/learn',
    icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168
            18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747
            0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />`,
    exact: false,
  },
  {
    name: '实验室',
    path: '/lab',
    icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1
            1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />`,
    exact: true,
  },
  {
    name: '报告',
    path: '/report',
    icon: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />`,
    exact: true,
  },
]

// =====================================================
// 活跃路由判断
// =====================================================

function isActive(item: (typeof navItems)[0]): boolean {
  if (item.exact) {
    return route.path === item.path
  }
  return route.path.startsWith(item.path)
}

// =====================================================
// 学习进度摘要
// =====================================================

const progressText = computed(() => {
  const count = learnerStateStore.totalCompleted
  return count > 0 ? `已完成 ${count} 课` : null
})
</script>

<template>
  <nav
    class="sticky top-0 z-50 bg-surface-card/90 backdrop-blur-md border-b border-line shadow-card"
  >
    <div class="max-w-7xl mx-auto px-4 sm:px-6">
      <div class="flex items-center justify-between h-14">

        <!-- ============================================
             左侧：Logo + 品牌名
        ============================================= -->
        <div
          class="flex items-center gap-3 cursor-pointer group shrink-0"
          @click="router.push('/')"
        >
          <!-- Logo 图标 -->
          <div
            class="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-card group-hover:shadow-pop transition-shadow"
          >
            <span class="text-base leading-none select-none">🦆</span>
          </div>

          <!-- 品牌文字 -->
          <div class="hidden sm:block">
            <span class="text-sm font-bold text-ink-900 leading-none">
              {{ platformCopy.name }}
            </span>
            <span class="hidden md:block text-xs text-ink-300 leading-none mt-0.5">
              {{ platformCopy.title }}
            </span>
          </div>
        </div>

        <!-- ============================================
             中间：导航链接
        ============================================= -->
        <div class="flex items-center gap-1">
          <button
            v-for="item in navItems"
            :key="item.path"
            class="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-150"
            :class="
              isActive(item)
                ? 'bg-brand-50 text-brand-700'
                : 'text-ink-700 hover:text-ink-900 hover:bg-surface-raised'
            "
            @click="router.push(item.path)"
          >
            <!-- 图标 -->
            <svg
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              v-html="item.icon"
            />
            <!-- 文字（小屏隐藏） -->
            <span class="hidden sm:inline">{{ item.name }}</span>

            <!-- 活跃指示点 -->
            <span
              v-if="isActive(item)"
              class="hidden sm:inline-block w-1 h-1 rounded-full bg-brand-500"
            />
          </button>
        </div>

        <!-- ============================================
             右侧：进度 + 主题
        ============================================= -->
        <div class="flex items-center gap-2 shrink-0">

          <!-- 学习进度 badge -->
          <div
            v-if="progressText"
            class="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-ok-50 border border-ok-600/30 text-ok-700 text-xs font-medium cursor-default"
          >
            <svg class="w-3.5 h-3.5 text-ok-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ progressText }}
          </div>

          <!-- 分隔线 -->
          <div class="hidden md:block w-px h-5 bg-line" />

          <!-- 主题切换按钮 -->
          <button
            class="w-8 h-8 rounded-lg flex items-center justify-center text-ink-500 hover:text-ink-700 hover:bg-surface-raised transition-colors"
            :title="localStateStore.editorTheme === 'vs-dark' ? '切换到亮色主题' : '切换到暗色主题'"
            @click="localStateStore.toggleEditorTheme()"
          >
            <!-- 暗色模式图标 -->
            <svg
              v-if="localStateStore.editorTheme === 'vs-dark'"
              class="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
              />
            </svg>
            <!-- 亮色模式图标 -->
            <svg
              v-else
              class="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
              />
            </svg>
          </button>

          <!-- 侧边栏切换（学习详情页时展示） -->
          <button
            v-if="route.path.startsWith('/lesson/')"
            class="w-8 h-8 rounded-lg flex items-center justify-center text-ink-500 hover:text-ink-700 hover:bg-surface-raised transition-colors"
            :title="localStateStore.isSidebarOpen ? '收起侧边栏' : '展开侧边栏'"
            @click="localStateStore.toggleSidebar()"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" />
            </svg>
          </button>

        </div>
      </div>
    </div>

    <!-- ============================================
         移动端底部导航提示条（仅在 md 以下显示）
    ============================================= -->
    <div
      v-if="route.path.startsWith('/lesson/') && learnerStateStore.lastVisitedSlug"
      class="sm:hidden border-t border-line px-4 py-2 bg-surface-page flex items-center justify-between text-xs text-ink-500"
    >
      <span class="flex items-center gap-1">
        <svg class="w-3.5 h-3.5 text-ok-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4" />
        </svg>
        {{ progressText ?? '开始学习' }}
      </span>
      <button
        class="text-brand-600 font-medium"
        @click="router.push('/learn')"
      >
        课程列表 →
      </button>
    </div>
  </nav>
</template>
