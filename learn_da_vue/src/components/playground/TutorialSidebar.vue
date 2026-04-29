<script setup lang="ts">
import { ref, computed } from 'vue'
import type { LessonSummary, LessonDetail } from '@/types/api'

interface Props {
  lessons: LessonSummary[]
  currentLesson: LessonDetail | null
  isLoading: boolean
  isCollapsed: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', slug: string): void
  (e: 'loadCode', code: string): void
  (e: 'toggleCollapse'): void
  (e: 'prev'): void
  (e: 'next'): void
}>()

const searchQuery = ref('')
const selectedCategory = ref<string>('all')

const categories = computed(() => {
  const cats = new Set<string>()
  props.lessons.forEach(l => cats.add(l.category))
  return ['all', ...Array.from(cats)]
})

const categoryLabels: Record<string, string> = {
  all: '全部',
  polars: '🐻‍❄️ Polars',
  duckdb: '🦆 DuckDB',
  combined: '⚡ 组合',
}

const filteredLessons = computed(() => {
  let result = props.lessons
  if (selectedCategory.value !== 'all') {
    result = result.filter(l => l.category === selectedCategory.value)
  }
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(l => 
      l.title.toLowerCase().includes(query) ||
      l.description.toLowerCase().includes(query)
    )
  }
  return result
})

const difficultyColors: Record<string, string> = {
  beginner: 'bg-emerald-500/20 text-emerald-400',
  intermediate: 'bg-blue-500/20 text-blue-400',
  advanced: 'bg-purple-500/20 text-purple-400',
}

const difficultyLabels: Record<string, string> = {
  beginner: '入门',
  intermediate: '进阶',
  advanced: '高级',
}

function selectLesson(slug: string) {
  emit('select', slug)
}

function loadCode() {
  if (props.currentLesson?.codeExample) {
    emit('loadCode', props.currentLesson.codeExample)
  }
}

function toggleCollapse() {
  emit('toggleCollapse')
}

function goPrev() {
  emit('prev')
}

function goNext() {
  emit('next')
}
</script>

<template>
  <div 
    class="h-full flex flex-col bg-[#1a1a2e] border-r border-white/10 transition-all duration-300"
    :class="isCollapsed ? 'w-12' : 'w-72'"
  >
    <!-- 折叠状态 -->
    <div v-if="isCollapsed" class="flex flex-col items-center py-4 gap-4">
      <button
        class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10"
        @click="toggleCollapse"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>

    <!-- 展开状态 -->
    <template v-else>
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <h2 class="text-sm font-semibold text-slate-200">交互式教程</h2>
        <button class="p-1.5 text-slate-400 hover:text-white" @click="toggleCollapse">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      </div>

      <div class="px-3 py-3 space-y-3 border-b border-white/10">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索教程..."
          class="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-slate-200 placeholder-slate-500"
        >
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="cat in categories"
            :key="cat"
            class="px-2 py-1 rounded text-xs"
            :class="selectedCategory === cat ? 'bg-blue-500/20 text-blue-400' : 'bg-white/5 text-slate-400'"
            @click="selectedCategory = cat"
          >
            {{ categoryLabels[cat] || cat }}
          </button>
        </div>
      </div>

      <div v-if="currentLesson" class="px-3 py-3 border-b border-white/10 bg-white/5">
        <div class="flex items-center gap-2 mb-2">
          <h3 class="text-sm font-medium text-slate-200">{{ currentLesson.title }}</h3>
          <span class="text-[10px] px-1.5 py-0.5 rounded" :class="difficultyColors[currentLesson.difficulty]">
            {{ difficultyLabels[currentLesson.difficulty] }}
          </span>
        </div>
        <div class="flex gap-2">
          <button
            v-if="currentLesson.codeExample"
            class="flex-1 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg"
            @click="loadCode"
          >
            加载代码
          </button>
          <button v-if="currentLesson.prevLesson" @click="goPrev">←</button>
          <button v-if="currentLesson.nextLesson" @click="goNext">→</button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto py-2">
        <div class="space-y-1 px-2">
          <button
            v-for="lesson in filteredLessons"
            :key="lesson.slug"
            class="w-full text-left px-3 py-2 rounded-lg"
            :class="currentLesson?.slug === lesson.slug ? 'bg-blue-500/20' : 'hover:bg-white/5'"
            @click="selectLesson(lesson.slug)"
          >
            <h4 class="text-sm font-medium text-slate-300">{{ lesson.title }}</h4>
            <p class="text-xs text-slate-500">{{ lesson.description }}</p>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
