<script setup lang="ts">
import AppButton from "./AppButton.vue";

// =====================================================
// EmptyState：空态必须给出下一步（cta 是必填的）
// 改造前的空态常常只有一个图标加一句话，学习者走到这里就断了。
// =====================================================

withDefaults(
    defineProps<{
        title: string;
        hint?: string;
        /** 必填：空态下可执行的动作文案 */
        cta: string;
        icon?: string;
    }>(),
    { icon: "◦" },
);

const emit = defineEmits<{ action: [] }>();
</script>

<template>
    <div class="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
        <div
            class="flex size-10 items-center justify-center rounded-pill bg-surface-raised text-lg text-ink-500"
            aria-hidden="true"
        >
            {{ icon }}
        </div>
        <p class="text-[15px] font-semibold text-ink-900">{{ title }}</p>
        <p v-if="hint" class="max-w-md text-sm text-ink-500">{{ hint }}</p>
        <AppButton variant="secondary" size="sm" @click="emit('action')">{{ cta }}</AppButton>
        <slot />
    </div>
</template>