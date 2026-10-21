<script setup lang="ts">
import { computed } from "vue";

// =====================================================
// AppButton：全站唯一按钮组件
//
// 改造前全站有 92 个手写 <button>，圆角/内距/主次色各不相同。
// 三档 variant 对应动作分级（§15.3）：
//   primary   每页唯一的实心主按钮（提交任务）
//   secondary 次要动作（运行、继续）
//   ghost     三级动作（要提示、问 AI）
// =====================================================

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const props = withDefaults(
    defineProps<{
        variant?: Variant;
        size?: Size;
        type?: "button" | "submit" | "reset";
        loading?: boolean;
        disabled?: boolean;
        block?: boolean;
        /** 危险动作（删除/撤销）：primary 换成 err 色 */
        danger?: boolean;
        /** 只有图标时给一个可读名字（同时成为 title） */
        label?: string;
    }>(),
    {
        variant: "primary",
        size: "md",
        type: "button",
        loading: false,
        disabled: false,
        block: false,
        danger: false,
    },
);

const emit = defineEmits<{ click: [event: MouseEvent] }>();

const isDisabled = computed(() => props.disabled || props.loading);

const VARIANTS: Record<Variant | "danger", string> = {
    primary:
        "bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600 shadow-sm",
    secondary:
        "border border-line bg-surface-card text-ink-700 hover:bg-surface-raised focus-visible:outline-brand-600",
    ghost:
        "text-ink-500 hover:bg-surface-raised hover:text-ink-700 focus-visible:outline-brand-600",
    danger:
        "bg-err-600 text-white hover:bg-err-700 focus-visible:outline-err-600 shadow-sm",
};

const SIZES: Record<Size, string> = {
    sm: "h-8 gap-1.5 px-3 text-[13px]",
    md: "h-10 gap-2 px-4 text-sm",
};

const classes = computed(() => [
    "inline-flex items-center justify-center rounded-control font-medium transition-colors",
    "focus-visible:outline-2 focus-visible:outline-offset-2",
    "disabled:cursor-not-allowed disabled:opacity-60",
    props.danger && props.variant === "primary" ? VARIANTS.danger : VARIANTS[props.variant],
    SIZES[props.size],
    props.block ? "w-full" : "",
]);

function onNativeClick(event: MouseEvent): void {
    if (isDisabled.value) return;
    emit("click", event);
}
</script>

<template>
    <button
        :type="type"
        :class="classes"
        :disabled="isDisabled"
        :aria-busy="loading || undefined"
        :aria-label="label"
        :title="label"
        @click="onNativeClick"
    >
        <svg
            v-if="loading"
            class="size-3.5 shrink-0 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
        >
            <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.25" />
            <path
                d="M21 12a9 9 0 0 0-9-9"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
            />
        </svg>
        <slot />
    </button>
</template>