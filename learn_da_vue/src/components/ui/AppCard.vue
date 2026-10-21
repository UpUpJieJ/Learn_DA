<script setup lang="ts">
import { computed } from "vue";

// =====================================================
// AppCard：卡片外壳（圆角 rounded-card、阴影 shadow-card 唯一来源）
// 改造前各页卡片圆角有 5 档、阴影有 5 档。
// =====================================================

const props = withDefaults(
    defineProps<{
        title?: string;
        /** 标题右侧的次要信息（如"3/5 完成"） */
        meta?: string;
        /** 内容是否加内距；表格类内容通常传 false 自己控制 */
        padded?: boolean;
        /** 紧凑模式（列表项用） */
        dense?: boolean;
    }>(),
    { padded: true, dense: false },
);

const bodyClass = computed(() => (props.padded ? (props.dense ? "p-3" : "p-5") : "p-0"));
</script>

<template>
    <section class="rounded-card border border-line bg-surface-card shadow-card">
        <header
            v-if="title || $slots.header || $slots.actions"
            class="flex items-center justify-between gap-3 border-b border-line px-5 py-3"
        >
            <slot name="header">
                <h2 class="text-[15px] font-semibold text-ink-900">{{ title }}</h2>
            </slot>
            <span v-if="meta" class="text-xs text-ink-500">{{ meta }}</span>
            <slot name="actions" />
        </header>
        <div :class="bodyClass">
            <slot />
        </div>
        <footer v-if="$slots.footer" class="border-t border-line px-5 py-3">
            <slot name="footer" />
        </footer>
    </section>
</template>