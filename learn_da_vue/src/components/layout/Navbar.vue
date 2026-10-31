<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLearnerStateStore } from '@/stores/learnerState'
import { useWorkspaceStore } from '@/stores/workspace'

const router = useRouter()
const route = useRoute()
const workspaceStore = useWorkspaceStore()
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
watch([() => route.path, () => workspaceStore.tasks.map((task) => task.status).join(',')], () => {
  void learnerStateStore.syncFromServer()
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
        <RouterLink
          class="flex items-center gap-3 group shrink-0 focus-visible:outline-2 focus-visible:outline-brand-600"
          to="/"
          aria-label="Learn DA 首页"
        >
          <!-- Logo 图标 -->
          <div
            class="w-8 h-8 rounded-control bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-card group-hover:shadow-pop transition-shadow"
          >
            <span class="text-base leading-none select-none">🦆</span>
          </div>

          <!-- 品牌文字 -->
          <div class="hidden sm:block">
            <span class="text-sm font-bold text-ink-900 leading-none">
              Learn DA
            </span>
            <span class="hidden md:block text-xs text-ink-500 leading-none mt-0.5">
              交互式数据分析学习平台
            </span>
          </div>
        </RouterLink>

        <!-- ============================================
             中间：导航链接
        ============================================= -->
        <div class="flex items-center gap-1">
          <button
            v-for="item in navItems"
            :key="item.path"
            :aria-label="item.name"
            :aria-current="isActive(item) ? 'page' : undefined"
            class="flex items-center gap-1.5 px-3.5 py-2 rounded-control text-sm font-medium transition-all duration-150"
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
              class="hidden sm:inline-block w-1 h-1 rounded-pill bg-brand-500"
            />
          </button>
        </div>

        <!-- ============================================
             右侧：学习进度
        ============================================= -->
        <div class="flex items-center gap-2 shrink-0">

          <!-- 学习进度 badge -->
          <div
            v-if="progressText"
            class="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-pill bg-ok-50 border border-ok-600/30 text-ok-700 text-xs font-medium cursor-default"
          >
            <svg class="w-3.5 h-3.5 text-ok-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ progressText }}
          </div>

          <!-- 分隔线 -->
          <div class="hidden md:block w-px h-5 bg-line" />


        </div>
      </div>
    </div>

    <!-- ============================================
         移动端底部导航提示条（仅在 md 以下显示）
    ============================================= -->
    <div
      v-if="route.path.startsWith('/lesson/')"
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
