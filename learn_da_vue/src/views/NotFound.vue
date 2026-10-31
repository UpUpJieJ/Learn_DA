<script setup lang="ts">
import { useRouter } from 'vue-router'
import { AppButton, EmptyState } from '@/components/ui'
const router = useRouter()
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-6 py-16">
    <EmptyState title="页面未找到" hint="这个页面不存在或已移动，请从课程地图继续。" icon="?" cta="去课程地图" @action="router.push('/learn')" />
    <div class="mt-6 flex justify-center gap-3">
      <AppButton variant="secondary" @click="router.push('/')">返回首页</AppButton>
      <AppButton variant="ghost" @click="router.push('/lab')">打开实验室</AppButton>
    </div>
  </div>
</template>
