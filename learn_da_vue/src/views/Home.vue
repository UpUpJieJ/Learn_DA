<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLocalStateStore } from '@/stores/localState'
import { learningTracks, platformCopy } from '@/lib/learningTracks'
import { fetchHomeStats } from '@/api/analytics'
import type { HomeStats } from '@/types/api'

const router = useRouter()
const localStateStore = useLocalStateStore()

// ---- 动画控制 ----
const heroVisible = ref(false)
const cardsVisible = ref(false)

onMounted(() => {
  setTimeout(() => (heroVisible.value = true), 50)
  setTimeout(() => (cardsVisible.value = true), 300)
  loadHomeStats()
})

// ---- 平台统计数据（从后端获取） ----
const homeStats = ref<HomeStats | null>(null)

async function loadHomeStats() {
  try {
    homeStats.value = await fetchHomeStats()
  } catch {
    // 静默失败，使用默认值
  }
}

// ---- 学习路径数据 ----
const learningPaths = learningTracks.map((track) => ({
  id: track.key,
  title: track.label,
  subtitle: track.subtitle,
  description: track.description,
  targetAudience: track.targetAudience,
  learningOutcome: track.learningOutcome,
  recommendedStart: track.recommendedStart,
  tags: track.tags,
  color: track.color,
  slug: track.route,
  lessonCount: track.lessonCount,
}))

// ---- 统计数据（优先展示后端实时数据） ----
const stats = computed(() => {
  if (homeStats.value) {
    return [
      { label: '课程总数', value: `${homeStats.value.totalLessons}` },
      { label: '学习路径', value: `${learningPaths.length}` },
      { label: '今日活跃', value: homeStats.value.todayActiveUsers > 0 ? `${homeStats.value.todayActiveUsers}` : '—' },
      { label: '代码运行', value: homeStats.value.totalCodeRuns > 0 ? `${homeStats.value.totalCodeRuns}` : '—' },
    ]
  }
  return [
    { label: '课程总数', value: '11' },
    { label: '学习路径', value: `${learningPaths.length}` },
    { label: '今日活跃', value: '—' },
    { label: '代码运行', value: '—' },
  ]
})

const lastVisitedSlug = computed(() => localStateStore.progress.lastVisitedSlug)
const hasLearningProgress = computed(() => !!lastVisitedSlug.value)

// ---- 操作 ----
function continueLearning() {
  const slug = lastVisitedSlug.value
  if (slug) {
    router.push(`/learn/${slug}`)
  } else {
    router.push('/learn')
  }
}

function goToLearning() {
  router.push('/learn')
}

function goToTrack(category: 'polars' | 'duckdb' | 'combined') {
  router.push(`/learn?category=${category}`)
}

const colorMap: Record<string, string> = {
  blue: 'from-blue-500 to-blue-700',
  yellow: 'from-yellow-400 to-orange-500',
  purple: 'from-purple-500 to-indigo-600',
}

const colorBg: Record<string, string> = {
  blue: 'bg-blue-50 border-blue-100',
  yellow: 'bg-yellow-50 border-yellow-100',
  purple: 'bg-purple-50 border-purple-100',
}

const colorTag: Record<string, string> = {
  blue: 'bg-blue-100 text-blue-700',
  yellow: 'bg-yellow-100 text-yellow-700',
  purple: 'bg-purple-100 text-purple-700',
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- ================================================
         Hero 区域
    ================================================= -->
    <section
      class="relative overflow-hidden bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 text-white"
    >
      <!-- 背景装饰 -->
      <div class="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          class="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-blue-600 opacity-10 blur-3xl"
        />
        <div
          class="absolute -bottom-32 -left-32 w-80 h-80 rounded-full bg-indigo-500 opacity-10 blur-3xl"
        />
        <!-- 网格背景 -->
        <svg
          class="absolute inset-0 w-full h-full opacity-5"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" stroke-width="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <div
        class="relative max-w-6xl mx-auto px-6 py-20 md:py-28 flex flex-col items-center text-center transition-all duration-700"
        :class="heroVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'"
      >
        <!-- Badge -->
        <span
          class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/10 border border-white/20 text-sm font-medium text-blue-200 mb-6 backdrop-blur-sm"
        >
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          {{ platformCopy.title }}
        </span>

        <!-- 标题 -->
        <h1 class="text-4xl md:text-6xl font-bold tracking-tight mb-6 leading-tight">
          {{ platformCopy.heroTitle }}
          <br />
          <span
            class="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent"
          >{{ platformCopy.heroTitleHighlight }}</span>
        </h1>

        <!-- 副标题 -->
        <p
          class="text-lg md:text-xl text-slate-300 max-w-2xl mb-4 leading-relaxed"
        >
          {{ platformCopy.heroSubtitle }}
        </p>

        <p class="text-sm text-slate-400 mb-6">
          {{ platformCopy.currentScope }}
        </p>

        <!-- 统计数据 -->
        <div class="flex flex-wrap justify-center gap-8 mt-6 mb-10">
          <div
            v-for="stat in stats"
            :key="stat.label"
            class="text-center"
          >
            <div class="text-2xl font-bold text-white">{{ stat.value }}</div>
            <div class="text-xs text-slate-400 mt-0.5">{{ stat.label }}</div>
          </div>
        </div>

        <!-- CTA 按钮组 -->
        <div class="flex flex-wrap gap-4 justify-center">
          <button
            class="flex items-center gap-2 px-7 py-3.5 rounded-xl bg-blue-500 hover:bg-blue-400 text-white font-semibold text-base transition-all duration-200 shadow-lg shadow-blue-500/30 hover:shadow-blue-400/40 hover:-translate-y-0.5 active:translate-y-0"
            @click="hasLearningProgress ? continueLearning() : goToTrack('polars')"
          >
            <span>{{ hasLearningProgress ? '继续学习' : '从推荐路径开始' }}</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>

          <button
            class="flex items-center gap-2 px-7 py-3.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-base border border-white/20 hover:border-white/30 transition-all duration-200 backdrop-blur-sm hover:-translate-y-0.5 active:translate-y-0"
            @click="goToLearning"
          >
            <span>查看全部学习路径</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        </div>

        <div class="mt-5 flex flex-wrap justify-center gap-3 text-xs text-slate-400">
          <button class="rounded-full border border-white/10 px-3 py-1 hover:border-blue-300/30 hover:text-blue-200 transition-colors" @click="goToTrack('polars')">
            Pandas 基础 → Polars
          </button>
          <button class="rounded-full border border-white/10 px-3 py-1 hover:border-yellow-300/30 hover:text-yellow-200 transition-colors" @click="goToTrack('duckdb')">
            SQL 基础 → DuckDB
          </button>
          <button class="rounded-full border border-white/10 px-3 py-1 hover:border-purple-300/30 hover:text-purple-200 transition-colors" @click="goToTrack('combined')">
            两者都会 → 组合实战
          </button>
        </div>
      </div>
    </section>

    <!-- ================================================
         学习路径卡片
    ================================================= -->
    <section class="max-w-6xl mx-auto px-6 py-16">
      <div class="text-center mb-12">
        <h2 class="text-3xl font-bold text-slate-800 mb-3">选择你的迁移学习路径</h2>
        <p class="text-slate-500 max-w-xl mx-auto">
          根据你的技术背景，选择最适合的起点开始学习。
        </p>
      </div>

      <!-- 推荐起步路径 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
        <div
          class="flex items-center gap-3 p-4 rounded-xl bg-blue-50 border border-blue-100 cursor-pointer hover:shadow-md transition-all"
          @click="router.push('/learn?category=polars')"
        >
          <span class="text-2xl">🐼</span>
          <div>
            <p class="text-sm font-semibold text-blue-800">我会 Pandas → 先学 Polars</p>
            <p class="text-xs text-blue-600/70">Pandas 用户的最短迁移路径</p>
          </div>
        </div>
        <div
          class="flex items-center gap-3 p-4 rounded-xl bg-yellow-50 border border-yellow-100 cursor-pointer hover:shadow-md transition-all"
          @click="router.push('/learn?category=duckdb')"
        >
          <span class="text-2xl">🗃️</span>
          <div>
            <p class="text-sm font-semibold text-yellow-800">我会 SQL → 先学 DuckDB</p>
            <p class="text-xs text-yellow-600/70">SQL 用户的本地分析升级</p>
          </div>
        </div>
        <div
          class="flex items-center gap-3 p-4 rounded-xl bg-purple-50 border border-purple-100 cursor-pointer hover:shadow-md transition-all"
          @click="goToTrack('combined')"
        >
          <span class="text-2xl">⚡</span>
          <div>
            <p class="text-sm font-semibold text-purple-800">我都会 → 进入组合实战</p>
            <p class="text-xs text-purple-600/70">构建完整数据分析管道</p>
          </div>
        </div>
      </div>

      <div
        class="grid grid-cols-1 md:grid-cols-3 gap-6 transition-all duration-700"
        :class="cardsVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'"
      >
        <div
          v-for="path in learningPaths"
          :key="path.id"
          class="group relative rounded-2xl border p-6 cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:shadow-xl"
          :class="colorBg[path.color]"
          @click="router.push(path.slug)"
        >
          <!-- 顶部渐变条 -->
          <div
            class="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r"
            :class="colorMap[path.color]"
          />

          <!-- 标题 -->
          <div class="flex items-start gap-4 mb-4">
            <div>
              <h3 class="text-xl font-bold text-slate-800">{{ path.title }}</h3>
              <p class="text-sm text-slate-500 mt-0.5">{{ path.subtitle }}</p>
            </div>
          </div>

          <!-- 适合谁 -->
          <div class="mb-3">
            <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">适合谁</p>
            <p class="text-sm text-slate-600 leading-relaxed">{{ path.targetAudience }}</p>
          </div>

          <!-- 你将获得什么 -->
          <div class="mb-4">
            <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">你将获得什么</p>
            <p class="text-sm text-slate-600 leading-relaxed">{{ path.learningOutcome }}</p>
          </div>

          <!-- 标签 -->
          <div class="flex flex-wrap gap-2 mb-5">
            <span
              v-for="tag in path.tags"
              :key="tag"
              class="px-2.5 py-1 rounded-full text-xs font-medium"
              :class="colorTag[path.color]"
            >
              {{ tag }}
            </span>
          </div>

          <!-- 底部：推荐起点 + 课程数 + 箭头 -->
          <div class="mt-auto pt-4 border-t border-black/5">
            <p class="text-xs text-blue-600/70 mb-2">💡 {{ path.recommendedStart }}</p>
            <div class="flex items-center justify-between">
              <span class="text-xs text-slate-400">{{ path.lessonCount }} 节课程</span>
              <span
                class="flex items-center gap-1 text-sm font-medium text-slate-500 group-hover:text-blue-600 transition-colors"
              >
                开始学习
                <svg
                  class="w-4 h-4 transition-transform group-hover:translate-x-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ================================================
         迁移价值说明
    ================================================= -->
    <section class="bg-white border-y border-slate-100 py-16">
      <div class="max-w-6xl mx-auto px-6">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-slate-800 mb-3">为什么选择迁移学习</h2>
          <p class="text-slate-500">从你已有的技术栈出发，用最短路径掌握新工具</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="flex flex-col items-start p-6 rounded-2xl bg-blue-50/50 border border-blue-100">
            <span class="text-3xl mb-4">🐼</span>
            <h4 class="font-semibold text-slate-800 mb-2">Polars 更适合表达式化与高性能处理</h4>
            <p class="text-sm text-slate-500 leading-relaxed">
              重点不是背性能口号，而是学会用表达式、惰性执行和清晰的数据管道，替代熟悉但更重的 Pandas 写法。
            </p>
          </div>
          <div class="flex flex-col items-start p-6 rounded-2xl bg-yellow-50/50 border border-yellow-100">
            <span class="text-3xl mb-4">🦆</span>
            <h4 class="font-semibold text-slate-800 mb-2">DuckDB 让本地 SQL 分析更轻更近</h4>
            <p class="text-sm text-slate-500 leading-relaxed">
              直接对 CSV、Parquet 和内存数据做查询，把你已有的 SQL 习惯延续到本地分析工作流里。
            </p>
          </div>
          <div class="flex flex-col items-start p-6 rounded-2xl bg-purple-50/50 border border-purple-100">
            <span class="text-3xl mb-4">⚡</span>
            <h4 class="font-semibold text-slate-800 mb-2">组合使用效率更高</h4>
            <p class="text-sm text-slate-500 leading-relaxed">
              用 Polars 做清洗与转换，用 DuckDB 做 SQL 分析，重点学会什么时候切换工具，而不是孤立记 API。
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- ================================================
         底部 CTA
    ================================================= -->
    <section class="max-w-6xl mx-auto px-6 py-16">
      <div class="rounded-3xl border border-slate-200 bg-gradient-to-r from-white to-slate-100 p-8 md:p-10">
        <div class="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div class="max-w-2xl">
            <p class="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">准备开始</p>
            <h2 class="text-2xl font-bold text-slate-900 md:text-3xl">
              从你最熟悉的技术栈出发，完成第一条迁移路径
            </h2>
            <p class="mt-3 text-sm leading-relaxed text-slate-500 md:text-base">
              不需要从零学起，直接沿着一条路径推进，把已有的 Pandas / SQL 经验迁移到更现代的数据分析工作流。
            </p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button
              class="rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-700"
              @click="goToLearning"
            >
              查看全部路径
            </button>
            <button
              class="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900"
              @click="hasLearningProgress ? continueLearning() : goToTrack('duckdb')"
            >
              {{ hasLearningProgress ? '继续学习' : '从 DuckDB 路径开始' }}
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
