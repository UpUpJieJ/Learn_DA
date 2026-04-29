<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-6 text-center">
    <!-- 数字装饰 -->
    <div class="relative mb-8 select-none">
      <span
        class="text-[10rem] font-black text-slate-100 leading-none tracking-tighter"
      >
        404
      </span>
      <div
        class="absolute inset-0 flex items-center justify-center"
      >
        <span class="text-6xl">🦆</span>
      </div>
    </div>

    <!-- 标题 -->
    <h1 class="text-2xl font-bold text-slate-800 mb-3">
      页面未找到
    </h1>

    <!-- 描述 -->
    <p class="text-slate-500 max-w-sm mb-8 leading-relaxed">
      你访问的页面不存在或已被移动。别担心，你可以从下面的入口重新出发。
    </p>

    <!-- 操作按钮 -->
    <div class="flex flex-wrap gap-3 justify-center">
      <button
        class="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-all duration-200 shadow-md shadow-blue-200 hover:-translate-y-px active:translate-y-0"
        @click="router.push('/')"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
        返回首页
      </button>

      <button
        class="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold border border-slate-200 hover:border-slate-300 transition-all duration-200 hover:-translate-y-px active:translate-y-0"
        @click="router.push('/learn')"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
        去学习中心
      </button>

      <button
        class="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold border border-slate-200 hover:border-slate-300 transition-all duration-200 hover:-translate-y-px active:translate-y-0"
        @click="router.push('/playground')"
      >
        <svg class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        打开 Playground
      </button>
    </div>

    <!-- 返回上一页 -->
    <button
      class="mt-8 text-sm text-slate-400 hover:text-slate-600 transition-colors flex items-center gap-1"
      @click="router.back()"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      返回上一页
    </button>
  </div>
</template>
