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

// ---- 特性亮点 ----
const features = [
  {
    icon: '🖊️',
    title: '在线代码编辑器',
    desc: '内嵌 Monaco Editor（VSCode 同款），支持 Python 语法高亮与智能提示。',
  },
  {
    icon: '▶️',
    title: '一键运行沙箱',
    desc: '代码在安全隔离的沙箱中执行，当前支持 Polars、DuckDB 相关练习。',
  },
  {
    icon: '🤖',
    title: 'AI Agent 助手',
    desc: '内嵌 AI 助手，可解释代码、排查错误、生成示例，全程陪伴学习。',
  },
  {
    icon: '📊',
    title: 'DataFrame 可视化',
    desc: '执行结果自动渲染为表格，直观展示数据结构与内容。',
  },
]

// ---- 统计数据（优先展示后端实时数据） ----
const stats = computed(() => {
  if (homeStats.value) {
    return [
      { label: '课程总数', value: `${homeStats.value.totalLessons}` },
      { label: '学习人数', value: homeStats.value.totalLearners > 0 ? `${homeStats.value.totalLearners}` : '—' },
      { label: '代码运行', value: homeStats.value.totalCodeRuns > 0 ? `${homeStats.value.totalCodeRuns}` : '—' },
      { label: '完全免费', value: '✓' },
    ]
  }
  return [
    { label: '课程总数', value: '11' },
    { label: '学习人数', value: '—' },
    { label: '代码运行', value: '—' },
    { label: '完全免费', value: '✓' },
  ]
})

const lastVisitedSlug = computed(() => localStateStore.progress.lastVisitedSlug)

// ---- 操作 ----
function goToPlayground() {
  router.push('/playground')
}

function continueLearning() {
  const slug = lastVisitedSlug.value
  if (slug) {
    router.push(`/learn/${slug}`)
  } else {
    router.push('/learn')
  }
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
            @click="router.push('/learn?category=polars')"
          >
            <span>开始 Polars 迁移学习</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>

          <button
            class="flex items-center gap-2 px-7 py-3.5 rounded-xl bg-yellow-500 hover:bg-yellow-400 text-yellow-900 font-semibold text-base transition-all duration-200 shadow-lg shadow-yellow-500/30 hover:shadow-yellow-400/40 hover:-translate-y-0.5 active:translate-y-0"
            @click="router.push('/learn?category=duckdb')"
          >
            <span>开始 DuckDB 迁移学习</span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>

          <button
            v-if="lastVisitedSlug"
            class="flex items-center gap-2 px-7 py-3.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-semibold text-base border border-white/20 hover:border-white/30 transition-all duration-200 backdrop-blur-sm hover:-translate-y-0.5 active:translate-y-0"
            :title="`继续学习 ${lastVisitedSlug}`"
            @click="continueLearning"
          >
            <svg class="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            </svg>
            <span>继续上次学习</span>
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
          @click="router.push('/learn')"
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
         功能特性
    ================================================= -->
    <section class="bg-white border-y border-slate-100 py-16">
      <div class="max-w-6xl mx-auto px-6">
        <div class="text-center mb-12">
          <h2 class="text-3xl font-bold text-slate-800 mb-3">平台特性</h2>
          <p class="text-slate-500">专为数据分析学习设计的一站式环境</p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div
            v-for="feature in features"
            :key="feature.title"
            class="flex flex-col items-start p-6 rounded-2xl bg-slate-50 border border-slate-100 hover:border-blue-100 hover:bg-blue-50/50 transition-colors duration-200"
          >
            <span class="text-3xl mb-4">{{ feature.icon }}</span>
            <h4 class="font-semibold text-slate-800 mb-2">{{ feature.title }}</h4>
            <p class="text-sm text-slate-500 leading-relaxed">{{ feature.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ================================================
         快速预览：Playground 示例
    ================================================= -->
    <section class="max-w-6xl mx-auto px-6 py-16">
      <div class="flex flex-col lg:flex-row gap-10 items-center">
        <!-- 文字说明 -->
        <div class="flex-1 min-w-0">
          <span
            class="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-blue-600 mb-4"
          >
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
            </svg>
            在线 Playground
          </span>
          <h2 class="text-3xl font-bold text-slate-800 mb-4 leading-snug">
            边写边学，<br />所见即所得
          </h2>
          <p class="text-slate-500 leading-relaxed mb-6">
            打开 Playground 页面，直接在浏览器中编写并执行 Python 代码。
            代码运行在安全的沙箱环境中，结果以表格或文本形式实时展示，无需任何本地配置。
          </p>
          <ul class="space-y-3 mb-8">
            <li
              v-for="item in ['Monaco 编辑器，完整语法高亮', '快捷键 Ctrl+Enter 一键运行', 'DataFrame 结果自动渲染为表格', 'AI 助手实时答疑与代码纠错']"
              :key="item"
              class="flex items-center gap-2.5 text-sm text-slate-600"
            >
              <svg class="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
              {{ item }}
            </li>
          </ul>
          <button
            class="flex items-center gap-2 px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-700 text-white font-semibold text-sm transition-all duration-200 hover:-translate-y-0.5"
            @click="goToPlayground"
          >
            立即尝试 Playground
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        </div>

        <!-- 代码预览卡片 -->
        <div class="flex-1 min-w-0 w-full">
          <div class="rounded-2xl overflow-hidden shadow-2xl border border-slate-700 bg-[#1e1e1e]">
            <!-- 伪装标题栏 -->
            <div class="flex items-center gap-2 px-4 py-3 bg-[#2d2d2d] border-b border-slate-700">
              <span class="w-3 h-3 rounded-full bg-red-500" />
              <span class="w-3 h-3 rounded-full bg-yellow-500" />
              <span class="w-3 h-3 rounded-full bg-emerald-500" />
              <span class="ml-3 text-xs text-slate-400 font-mono">playground.py</span>
            </div>
            <!-- 代码内容 -->
            <pre
              class="text-sm font-mono leading-relaxed p-5 overflow-x-auto text-slate-200 select-none"
            ><span class="text-blue-400">import</span> polars <span class="text-blue-400">as</span> pl
<span class="text-blue-400">import</span> duckdb

<span class="text-slate-500"># 用 Polars 加载数据</span>
df = pl.DataFrame({
    <span class="text-yellow-300">"city"</span>: [<span class="text-yellow-300">"北京"</span>, <span class="text-yellow-300">"上海"</span>, <span class="text-yellow-300">"深圳"</span>],
    <span class="text-yellow-300">"sales"</span>: [<span class="text-emerald-400">120</span>, <span class="text-emerald-400">95</span>, <span class="text-emerald-400">148</span>],
    <span class="text-yellow-300">"growth"</span>: [<span class="text-emerald-400">0.12</span>, <span class="text-emerald-400">0.08</span>, <span class="text-emerald-400">0.25</span>],
})

<span class="text-slate-500"># 用 DuckDB 做 SQL 分析</span>
result = duckdb.sql(<span class="text-yellow-300">"""
    SELECT city, sales,
           ROUND(growth * 100, 1) AS growth_pct
    FROM df
    ORDER BY sales DESC
"""</span>).pl()

<span class="text-blue-400">print</span>(result)</pre>
            <!-- 模拟输出 -->
            <div class="px-5 pb-4 border-t border-slate-700 pt-3">
              <p class="text-xs text-slate-500 font-mono mb-2">▶ 输出结果</p>
              <pre
                class="text-xs font-mono text-emerald-400 leading-relaxed"
              >┌────────┬───────┬────────────┐
│ city   │ sales │ growth_pct │
│ str    │ i64   │ f64        │
╞════════╪═══════╪════════════╡
│ 深圳   │   148 │       25.0 │
│ 北京   │   120 │       12.0 │
│ 上海   │    95 │        8.0 │
└────────┴───────┴────────────┘</pre>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ================================================
         底部 CTA
    ================================================= -->
  </div>
</template>
