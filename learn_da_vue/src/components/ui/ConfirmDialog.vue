<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import AppButton from "./AppButton.vue";

// =====================================================
// ConfirmDialog：危险操作确认层（替代 window.confirm）
//
// - ESC / 点遮罩 = 取消；打开时焦点落在取消按钮（默认不误触危险动作）
// - 危险动作用 danger 变体，确认按钮文案要写清后果（"删除这个格""撤销完成标记"）
// =====================================================

const props = withDefaults(
    defineProps<{
        open: boolean;
        title: string;
        description?: string;
        confirmText: string;
        cancelText?: string;
        danger?: boolean;
        loading?: boolean;
    }>(),
    { cancelText: "取消", danger: false, loading: false },
);

const emit = defineEmits<{ confirm: []; cancel: [] }>();

const cancelRef = ref<InstanceType<typeof AppButton> | null>(null);

function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
        event.stopPropagation();
        emit("cancel");
    }
}

watch(
    () => props.open,
    async (open) => {
        if (open) {
            window.addEventListener("keydown", onKeydown);
            await nextTick();
            (cancelRef.value?.$el as HTMLElement | undefined)?.focus();
        } else {
            window.removeEventListener("keydown", onKeydown);
        }
    },
    // immediate：组件挂载时就是打开状态（由 v-if 外的父级控制）也要能按 ESC
    { immediate: true },
);

onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
    <Teleport to="body">
        <div
            v-if="open"
            class="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4"
            @click.self="emit('cancel')"
        >
            <div
                role="dialog"
                aria-modal="true"
                :aria-label="title"
                class="w-full max-w-sm rounded-card bg-surface-card p-5 shadow-pop"
            >
                <h2 class="text-[15px] font-semibold text-ink-900">{{ title }}</h2>
                <p v-if="description" class="mt-2 text-sm text-ink-500">{{ description }}</p>
                <div class="mt-5 flex justify-end gap-2">
                    <AppButton ref="cancelRef" variant="secondary" size="sm" @click="emit('cancel')">
                        {{ cancelText }}
                    </AppButton>
                    <AppButton
                        :danger="danger"
                        size="sm"
                        :loading="loading"
                        @click="emit('confirm')"
                    >
                        {{ confirmText }}
                    </AppButton>
                </div>
            </div>
        </div>
    </Teleport>
</template>