<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useLocalStateStore } from "@/stores/localState";
import { getVisitorId } from "@/lib/visitorId";
import { getRecommendationContextLesson } from "@/lib/recommendation";
import {
  fetchUserProfile,
  fetchUserLessonStats,
  fetchDailyTrend,
  fetchRecommendedLessons,
  fetchCategoryProgress,
} from "@/api/analytics";
import { fetchCatalog, fetchLessons } from "@/api/learning";
import { getRecommendations } from "@/api/recommendation";
import type {
  UserProfile,
  UserLessonStats,
  DailyTrendItem,
  RecommendedLessonsResponse,
  CategoryProgress,
  RecommendationResponse,
  PlatformCatalog,
  LessonSummary,
} from "@/types/api";
import * as echarts from "echarts/core";
import { LineChart, RadarChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  RadarComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  RadarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  RadarComponent,
  CanvasRenderer,
]);

const router = useRouter();
const localStateStore = useLocalStateStore();
const visitorId = getVisitorId();

// =====================================================
// 状态
// =====================================================

const activeTab = ref<"overview" | "lessons" | "trend" | "ability">("overview");
const isLoading = ref(true);
const profile = ref<UserProfile | null>(null);
const lessonStats = ref<UserLessonStats | null>(null);
const lessons = ref<LessonSummary[]>([]);
const dailyTrend = ref<DailyTrendItem[]>([]);
const recommended = ref<RecommendedLessonsResponse | null>(null);
const categoryProgress = ref<CategoryProgress | null>(null);
const recommendation = ref<RecommendationResponse | null>(null);
const catalog = ref<PlatformCatalog | null>(null);

const tabs = [
  { key: "overview", label: "学习概览", icon: "📊" },
  { key: "lessons", label: "课程统计", icon: "📚" },
  { key: "trend", label: "趋势分析", icon: "📈" },
  { key: "ability", label: "能力雷达", icon: "🎯" },
] as const;

// =====================================================
// 数据加载
// =====================================================

async function loadAllData() {
  isLoading.value = true;
  try {
    const currentLesson = getRecommendationContextLesson({
      lastVisitedSlug: localStateStore.progress.lastVisitedSlug,
    });
    const results = await Promise.all([
      fetchUserProfile(visitorId).catch(() => null),
      fetchUserLessonStats(visitorId).catch(() => null),
      fetchDailyTrend(30).catch(() => null),
      fetchRecommendedLessons(visitorId).catch(() => null),
      fetchCategoryProgress(visitorId).catch(() => null),
      getRecommendations({
        visitorId,
        completedLessons: localStateStore.progress.completedLessons,
        currentLesson,
      }).catch(() => null),
      fetchCatalog().catch(() => null),
      fetchLessons().catch(() => [] as LessonSummary[]),
    ]);
    if (results[0]) profile.value = results[0];
    if (results[1]) lessonStats.value = results[1];
    if (results[2]) dailyTrend.value = results[2];
    if (results[3]) recommended.value = results[3];
    if (results[4]) categoryProgress.value = results[4];
    if (results[5]) recommendation.value = results[5];
    if (results[6]) catalog.value = results[6];
    lessons.value = results[7] ?? [];
  } catch {
    // 静默处理
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadAllData);

// =====================================================
// 格式化工具
// =====================================================

function formatMinutes(min: number): string {
  if (min < 60) return `${min} 分钟`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h} 小时 ${m} 分钟` : `${h} 小时`;
}

// =====================================================
// ECharts - 趋势折线图
// =====================================================

const trendChartRef = ref<HTMLElement | null>(null);
let trendChart: echarts.ECharts | null = null;

function renderTrendChart() {
  if (!trendChartRef.value || dailyTrend.value.length === 0) return;

  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value);
  }

  const dates = dailyTrend.value.map((d) => d.date.slice(5)); // MM-DD
  trendChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["活跃用户", "代码运行", "课程完成", "AI 助手"], top: 0 },
    grid: { left: "3%", right: "4%", bottom: "3%", top: "40px", containLabel: true },
    xAxis: { type: "category", data: dates, boundaryGap: false },
    yAxis: { type: "value" },
    series: [
      { name: "活跃用户", type: "line", smooth: true, data: dailyTrend.value.map((d) => d.activeUsers), itemStyle: { color: "#3b82f6" } },
      { name: "代码运行", type: "line", smooth: true, data: dailyTrend.value.map((d) => d.codeRuns), itemStyle: { color: "#10b981" } },
      { name: "课程完成", type: "line", smooth: true, data: dailyTrend.value.map((d) => d.lessonsCompleted), itemStyle: { color: "#f59e0b" } },
      { name: "AI 助手", type: "line", smooth: true, data: dailyTrend.value.map((d) => d.aiHelps), itemStyle: { color: "#8b5cf6" } },
    ],
  });
}

// =====================================================
// ECharts - 能力雷达图
// =====================================================

const radarChartRef = ref<HTMLElement | null>(null);
let radarChart: echarts.ECharts | null = null;

function renderRadarChart() {
  if (!radarChartRef.value || !profile.value) return;

  if (!radarChart) {
    radarChart = echarts.init(radarChartRef.value);
  }

  radarChart.setOption({
    radar: {
      indicator: [
        { name: "Polars", max: 100 },
        { name: "DuckDB", max: 100 },
        { name: "SQL", max: 100 },
        { name: "数据处理", max: 100 },
        { name: "API 熟练度", max: 100 },
      ],
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: [
              profile.value.polarsScore,
              profile.value.duckdbScore,
              profile.value.sqlScore,
              profile.value.dataProcessingScore,
              profile.value.apiMasteryScore,
            ],
            name: "能力值",
            areaStyle: { color: "rgba(59, 130, 246, 0.2)" },
            lineStyle: { color: "#3b82f6" },
            itemStyle: { color: "#3b82f6" },
          },
        ],
      },
    ],
  });
}

// 切换 tab 时渲染对应图表
watch(activeTab, (tab) => {
  if (tab === "trend") {
    setTimeout(renderTrendChart, 100);
  } else if (tab === "ability") {
    setTimeout(renderRadarChart, 100);
  }
});

// =====================================================
// 课程完成率
// =====================================================

const categoryList = computed(() => {
  const progress = categoryProgress.value ?? {};
  const totals = lessons.value.reduce<Record<string, number>>((acc, lesson) => {
    acc[lesson.category] = (acc[lesson.category] ?? 0) + 1;
    return acc;
  }, {});
  const byCategory = new Map<string, { key: string; label: string; color?: string }>();

  catalog.value?.tracks
    .filter((track) => track.category)
    .forEach((track) => {
      byCategory.set(track.category!, {
        key: track.category!,
        label: track.label,
        color: track.color,
      });
    });

  Object.keys(progress).forEach((category) => {
    if (!byCategory.has(category)) {
      byCategory.set(category, {
        key: category,
        label: category,
      });
    }
  });

  return Array.from(byCategory.values()).map((item) => {
    const count = progress[item.key] ?? 0;
    const total = totals[item.key] ?? 0;
    return {
      ...item,
      count,
      total,
      percent: total > 0 ? Math.min(100, Math.round((count / total) * 100)) : 0,
      barClass: categoryBarClass(item.color ?? item.key),
    };
  });
});

function categoryBarClass(color: string): string {
  const classes: Record<string, string> = {
    blue: "bg-blue-500",
    yellow: "bg-yellow-500",
    purple: "bg-purple-500",
    emerald: "bg-emerald-500",
    green: "bg-emerald-500",
    orange: "bg-orange-500",
    red: "bg-red-500",
    slate: "bg-slate-500",
    polars: "bg-blue-500",
    duckdb: "bg-yellow-500",
    combined: "bg-purple-500",
    python: "bg-emerald-500",
  };
  return classes[color] ?? "bg-slate-500";
}

const completionRate = computed(() => {
  if (!recommended.value || recommended.value.totalCount === 0) return 0;
  return Math.round((recommended.value.completedCount / recommended.value.totalCount) * 100);
});

// =====================================================
// 下一步学习建议
// =====================================================

function goToLesson(slug: string) {
  router.push(`/learn/${slug}`);
}

function getRecommendationStyle(rec: any) {
  const type = rec.type;

  // 回补建议 - 橙色警示
  if (type === "review_lesson") {
    return {
      containerClass: "bg-gradient-to-r from-orange-50 to-amber-50 border-orange-200",
      labelClass: "text-orange-700",
      buttonClass: "bg-orange-600 hover:bg-orange-700",
      badgeClass: "bg-orange-100",
      icon: "⚠️",
      emoji: "📖",
      label: "建议回补前置课程",
    };
  }

  // 分支建议 - 紫色高亮
  if (type === "branch_path") {
    return {
      containerClass: "bg-gradient-to-r from-purple-50 to-indigo-50 border-purple-200",
      labelClass: "text-purple-700",
      buttonClass: "bg-purple-600 hover:bg-purple-700",
      badgeClass: "bg-purple-100",
      icon: "🔀",
      emoji: "🎯",
      label: "学习路径分支点",
    };
  }

  // 回流建议 - 绿色温馨
  if (type === "resume_session") {
    return {
      containerClass: "bg-gradient-to-r from-emerald-50 to-green-50 border-emerald-200",
      labelClass: "text-emerald-700",
      buttonClass: "bg-emerald-600 hover:bg-emerald-700",
      badgeClass: "bg-emerald-100",
      icon: "👋",
      emoji: "🔄",
      label: "欢迎回来继续学习",
    };
  }

  // 顺学建议 - 蓝色默认
  return {
    containerClass: "bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-100",
    labelClass: "text-blue-700",
    buttonClass: "bg-blue-600 hover:bg-blue-700",
    badgeClass: "bg-blue-100",
    icon: "💡",
    emoji: "📚",
    label: "下一步学习建议",
  };
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- 顶部标题栏 -->
    <div class="bg-white border-b border-slate-200">
      <div class="max-w-6xl mx-auto px-6 py-6">
        <h1 class="text-2xl font-bold text-slate-800">学习看板</h1>
        <p class="text-sm text-slate-500 mt-1">追踪你的学习进度和成长轨迹</p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="flex items-center justify-center py-32">
      <div class="flex flex-col items-center gap-4">
        <div class="w-10 h-10 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin" />
        <p class="text-sm text-slate-500">加载中…</p>
      </div>
    </div>

    <template v-else>
      <!-- Tab 导航 -->
      <div class="bg-white border-b border-slate-100 sticky top-0 z-10">
        <div class="max-w-6xl mx-auto px-6 flex gap-1">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-all"
            :class="
              activeTab === tab.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            "
            @click="activeTab = tab.key"
          >
            <span>{{ tab.icon }}</span>
            <span>{{ tab.label }}</span>
          </button>
        </div>
      </div>

      <div class="max-w-6xl mx-auto px-6 py-8">
        <!-- ===================== 学习概览 ===================== -->
        <div v-if="activeTab === 'overview'" class="space-y-6">
          <!-- 统计卡片 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white rounded-2xl border border-slate-100 p-5">
              <div class="text-xs text-slate-400 mb-1">累计学习时长</div>
              <div class="text-2xl font-bold text-slate-800">
                {{ formatMinutes(profile?.totalLearningMinutes ?? 0) }}
              </div>
            </div>
            <div class="bg-white rounded-2xl border border-slate-100 p-5">
              <div class="text-xs text-slate-400 mb-1">完成课程</div>
              <div class="text-2xl font-bold text-emerald-600">
                {{ profile?.lessonsCompleted ?? 0 }}
              </div>
            </div>
            <div class="bg-white rounded-2xl border border-slate-100 p-5">
              <div class="text-xs text-slate-400 mb-1">代码运行</div>
              <div class="text-2xl font-bold text-blue-600">
                {{ profile?.codeRuns ?? 0 }}
              </div>
            </div>
            <div class="bg-white rounded-2xl border border-slate-100 p-5">
              <div class="text-xs text-slate-400 mb-1">AI 助手</div>
              <div class="text-2xl font-bold text-purple-600">
                {{ profile?.aiHelps ?? 0 }}
              </div>
            </div>
          </div>

          <!-- 连续学习 + 进度 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- 连续学习 -->
            <div class="bg-white rounded-2xl border border-slate-100 p-6">
              <h3 class="text-sm font-semibold text-slate-700 mb-4">🔥 连续学习</h3>
              <div class="flex items-end gap-6">
                <div>
                  <div class="text-4xl font-bold text-orange-500">
                    {{ profile?.currentStreak ?? 0 }}
                  </div>
                  <div class="text-xs text-slate-400 mt-1">当前连续天数</div>
                </div>
                <div>
                  <div class="text-xl font-bold text-slate-600">
                    {{ profile?.longestStreak ?? 0 }}
                  </div>
                  <div class="text-xs text-slate-400 mt-1">最长连续天数</div>
                </div>
              </div>
            </div>

            <!-- 课程完成率 -->
            <div class="bg-white rounded-2xl border border-slate-100 p-6">
              <h3 class="text-sm font-semibold text-slate-700 mb-4">📋 课程完成率</h3>
              <div class="flex items-center gap-6">
                <div class="relative w-20 h-20">
                  <svg class="w-20 h-20 -rotate-90" viewBox="0 0 36 36">
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#e2e8f0"
                      stroke-width="3"
                    />
                    <path
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none"
                      stroke="#10b981"
                      stroke-width="3"
                      :stroke-dasharray="`${completionRate}, 100`"
                      stroke-linecap="round"
                    />
                  </svg>
                  <div class="absolute inset-0 flex items-center justify-center text-lg font-bold text-emerald-600">
                    {{ completionRate }}%
                  </div>
                </div>
                <div>
                  <div class="text-sm text-slate-600">
                    已完成 <span class="font-bold text-slate-800">{{ recommended?.completedCount ?? 0 }}</span> / {{ recommended?.totalCount ?? 0 }} 课
                  </div>
                  <button
                    v-if="recommended?.recommended"
                    class="mt-2 text-xs text-blue-600 hover:text-blue-700 font-medium"
                    @click="router.push(`/learn/${recommended.recommended.slug}`)"
                  >
                    继续学习：{{ recommended.recommended.title }} →
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 下一步学习建议 (Phase 3) -->
          <div
            v-if="recommendation?.primary"
            class="rounded-2xl border p-6"
            :class="getRecommendationStyle(recommendation.primary).containerClass"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-lg">{{ getRecommendationStyle(recommendation.primary).icon }}</span>
                  <h3 class="text-sm font-semibold" :class="getRecommendationStyle(recommendation.primary).labelClass">
                    {{ getRecommendationStyle(recommendation.primary).label }}
                  </h3>
                </div>
                <h4 class="text-lg font-bold text-slate-800 mb-1">
                  {{ recommendation.primary.targetTitle }}
                </h4>
                <p class="text-sm text-slate-600 mb-4">
                  {{ recommendation.primary.reason }}
                </p>
                <button
                  class="px-4 py-2 text-white text-sm font-medium rounded-lg transition-colors"
                  :class="getRecommendationStyle(recommendation.primary).buttonClass"
                  @click="goToLesson(recommendation.primary.targetSlug)"
                >
                  {{ recommendation.primary.actionLabel }}
                </button>
              </div>
              <div class="flex-shrink-0">
                <div
                  class="w-12 h-12 rounded-full flex items-center justify-center text-2xl"
                  :class="getRecommendationStyle(recommendation.primary).badgeClass"
                >
                  {{ getRecommendationStyle(recommendation.primary).emoji }}
                </div>
              </div>
            </div>

            <!-- 备选建议 -->
            <div
              v-if="recommendation.alternatives && recommendation.alternatives.length > 0"
              class="mt-4 pt-4 border-t border-slate-200/50"
            >
              <p class="text-xs text-slate-500 font-medium mb-2">其他选择：</p>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="alt in recommendation.alternatives"
                  :key="alt.targetSlug"
                  class="px-3 py-1.5 text-xs font-medium rounded-lg bg-white/70 border border-slate-200 text-slate-700 hover:border-slate-300 hover:shadow-sm transition-all"
                  @click="goToLesson(alt.targetSlug)"
                >
                  {{ alt.targetTitle }}
                </button>
              </div>
            </div>
          </div>

          <!-- 推荐课程 (旧版，保留兼容) -->
          <div v-else-if="recommended?.recommended" class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-2xl border border-blue-100 p-6">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-sm font-semibold text-blue-700 mb-1">📌 推荐下一步</h3>
                <p class="text-lg font-bold text-slate-800">{{ recommended.recommended.title }}</p>
                <p class="text-sm text-slate-500 mt-1">{{ recommended.recommended.description }}</p>
              </div>
              <button
                class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors shrink-0"
                @click="router.push(`/learn/${recommended.recommended.slug}`)"
              >
                开始学习
              </button>
            </div>
          </div>
        </div>

        <!-- ===================== 课程统计 ===================== -->
        <div v-if="activeTab === 'lessons'" class="space-y-4">
          <div v-if="!lessonStats || lessonStats.lessonDetails.length === 0" class="text-center py-16">
            <div class="text-4xl mb-4">📚</div>
            <p class="text-slate-500">还没有学习记录，去开始第一课吧！</p>
            <button
              class="mt-4 px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-500"
              @click="router.push('/learn')"
            >
              去学习
            </button>
          </div>
          <div v-else class="grid gap-3">
            <div
              v-for="item in lessonStats.lessonDetails"
              :key="item.slug"
              class="bg-white rounded-xl border border-slate-100 p-4 flex items-center justify-between"
            >
              <div class="flex items-center gap-3">
                <span
                  class="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
                  :class="item.completed ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400'"
                >
                  {{ item.completed ? '✓' : '○' }}
                </span>
                <div>
                  <div class="text-sm font-medium text-slate-700">{{ item.slug }}</div>
                  <div class="text-xs text-slate-400 mt-0.5">
                    代码运行 {{ item.codeRuns }} 次 · AI 助手 {{ item.aiHelps }} 次
                  </div>
                </div>
              </div>
              <button
                class="text-xs text-blue-600 hover:text-blue-700 font-medium"
                @click="router.push(`/learn/${item.slug}`)"
              >
                {{ item.completed ? '复习' : '学习' }} →
              </button>
            </div>
          </div>
        </div>

        <!-- ===================== 趋势分析 ===================== -->
        <div v-if="activeTab === 'trend'" class="space-y-4">
          <div v-if="dailyTrend.length === 0" class="text-center py-16">
            <div class="text-4xl mb-4">📈</div>
            <p class="text-slate-500">暂无趋势数据</p>
          </div>
          <div v-else class="bg-white rounded-2xl border border-slate-100 p-6">
            <h3 class="text-sm font-semibold text-slate-700 mb-4">近 {{ dailyTrend.length }} 天趋势</h3>
            <div ref="trendChartRef" class="w-full h-80" />
          </div>
        </div>

        <!-- ===================== 能力雷达 ===================== -->
        <div v-if="activeTab === 'ability'" class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- 雷达图 -->
            <div class="bg-white rounded-2xl border border-slate-100 p-6">
              <h3 class="text-sm font-semibold text-slate-700 mb-4">能力雷达图</h3>
              <div ref="radarChartRef" class="w-full h-72" />
            </div>

            <!-- 分类进度 -->
            <div class="bg-white rounded-2xl border border-slate-100 p-6">
              <h3 class="text-sm font-semibold text-slate-700 mb-4">分类学习进度</h3>
              <div class="space-y-5">
                <div v-for="cat in categoryList" :key="cat.key">
                  <div class="flex items-center justify-between mb-1.5">
                    <span class="text-sm text-slate-600">{{ cat.label }}</span>
                    <span class="text-xs text-slate-400">
                      完成 {{ cat.count }} / {{ cat.total }} 课
                    </span>
                  </div>
                  <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all duration-500"
                      :class="cat.barClass"
                      :style="{ width: `${cat.percent}%` }"
                    />
                  </div>
                </div>
              </div>

              <!-- 能力分列表 -->
              <div class="mt-6 pt-4 border-t border-slate-100 space-y-2">
                <div v-for="score in [
                  { label: 'Polars', value: profile?.polarsScore ?? 0 },
                  { label: 'DuckDB', value: profile?.duckdbScore ?? 0 },
                  { label: 'SQL', value: profile?.sqlScore ?? 0 },
                  { label: '数据处理', value: profile?.dataProcessingScore ?? 0 },
                  { label: 'API 熟练度', value: profile?.apiMasteryScore ?? 0 },
                ]" :key="score.label"
                  class="flex items-center justify-between text-sm"
                >
                  <span class="text-slate-500">{{ score.label }}</span>
                  <span class="font-mono font-medium text-slate-700">{{ score.value.toFixed(1) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
