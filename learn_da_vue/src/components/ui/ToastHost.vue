<script setup lang="ts">
import { useToast, type ToastKind } from "@/composables/useToast";

// =====================================================
// ToastHost：唯一的 toast 容器，挂在 App.vue 根部
// 页面里调 useToast().success(...) 即可，不要各自渲染。
// =====================================================

const { toasts, dismiss } = useToast();

const KIND_CLASS: Record<ToastKind, string> = {
    success: "border-ok-600/40 bg-ok-50 text-ok-700",
    error: "border-err-500/40 bg-err-50 text-err-700",
    info: "border-line bg-surface-card text-ink-700",
};
</script>

<template>
    <Teleport to="body">
        <div
            class="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4"
            role="status"
            aria-live="polite"
        >
            <TransitionGroup name="slide-up">
                <div
                    v-for="item in toasts"
                    :key="item.id"
                    class="pointer-events-auto flex max-w-md items-center gap-3 rounded-control border px-3 py-2 text-sm shadow-pop"
                    :class="KIND_CLASS[item.kind]"
                >
                    <span class="flex-1">{{ item.message }}</span>
                    <button
                        type="button"
                        class="rounded-control px-1 opacity-60 transition-opacity hover:opacity-100"
                        aria-label="关闭提示"
                        @click="dismiss(item.id)"
                    >
                        ×
                    </button>
                </div>
            </TransitionGroup>
        </div>
    </Teleport>
</template>