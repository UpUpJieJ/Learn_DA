import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { cancelAllRequests } from '@/api/index'

// =====================================================
// 路由表定义（全部懒加载，代码分割）
// =====================================================

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: {
      title: '首页',
      keepAlive: false,
    },
  },
  {
    path: '/learn',
    name: 'Learning',
    component: () => import('@/views/Learning.vue'),
    meta: {
      title: '学习中心',
      keepAlive: true,
    },
  },
  {
    path: '/learn/:slug',
    name: 'LessonDetail',
    component: () => import('@/views/LessonDetail.vue'),
    meta: {
      title: '课程详情',
      keepAlive: false,
    },
    props: true,
  },
  {
    path: '/playground/:slug?',
    name: 'Playground',
    component: () => import('@/views/Playground.vue'),
    meta: {
      title: 'Playground',
      keepAlive: true,
    },
    props: true,
  },
  // ---- 404 兜底 ----
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: {
      title: '页面未找到',
    },
  },
]

// =====================================================
// 创建路由实例
// =====================================================

// 禁用浏览器自动恢复滚动位置，由应用完全控制
// 避免刷新后出现“自动滚动到底部”的异常体验
if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual'
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  // 路由切换后滚动到顶部；若有 savedPosition（浏览器前进/后退）则恢复原位
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    return { top: 0, behavior: 'smooth' }
  },
})

// =====================================================
// 全局前置守卫
// =====================================================

router.beforeEach((to, _from, next) => {
  // 1. 取消上一个页面尚未完成的请求，避免数据污染
  cancelAllRequests('路由切换')

  // 2. 动态设置页面标题
  const siteTitle = import.meta.env.VITE_APP_TITLE ?? '数据分析学习平台'
  const pageTitle = to.meta?.title as string | undefined
  document.title = pageTitle ? `${pageTitle} · ${siteTitle}` : siteTitle

  next()
})

// =====================================================
// 全局后置钩子
// =====================================================

router.afterEach((to, _from, failure) => {
  if (failure) {
    console.error('[Router] 导航失败:', failure)
    return
  }

  // 记录最后访问的课程 slug（仅在课程详情页）
  if (to.name === 'LessonDetail' && to.params.slug) {
    try {
      // 使用动态导入避免循环依赖（store 内部可能也 import router）
      import('@/stores/localState').then(({ useLocalStateStore }) => {
        // 注意：store 必须在 pinia 激活后才能调用
        const localStateStore = useLocalStateStore()
        localStateStore.setLastVisitedLesson(to.params.slug as string)
      })
    } catch (e) {
      // store 尚未初始化时静默忽略
    }
  }
})

export default router
