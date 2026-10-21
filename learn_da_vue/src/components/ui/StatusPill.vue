<script setup lang="ts">
import { computed } from "vue";
import { taskStatusMeta, type TaskStatusMeta } from "./status";

// =====================================================
// StatusPill：任务/练习状态药丸（四态 + 需复核 + 已跳过）
// 状态映射集中在 ./status.ts，页面不要自己拼颜色。
// =====================================================

const props = withDefaults(
    defineProps<{
        status: string;
        /** 覆盖默认文案（如"3/3 已通过"） */
        label?: string;
        size?: "sm" | "md";
        showDot?: boolean;
    }>(),
    { size: "sm", showDot: true },
);

const meta = computed<TaskStatusMeta>(() => taskStatusMeta(props.status));
</script>

<template>
    <span
        class="inline-flex items-center rounded-pill border font-medium whitespace-nowrap"
        :class="[meta.pillClass, size === 'sm' ? 'gap-1.5 px-2 py-0.5 text-xs' : 'gap-2 px-2.5 py-1 text-[13px]']"
    >
        <span v-if="showDot" class="size-1.5 shrink-0 rounded-pill" :class="meta.dotClass" aria-hidden="true" />
        {{ label ?? meta.label }}
    </span>
</template>