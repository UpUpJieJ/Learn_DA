<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch, useId } from "vue";
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
const dialogRef = ref<HTMLElement | null>(null);
const titleId = useId();
const descriptionId = useId();
const settled = ref(false);
let opener: HTMLElement | null = null;
let previousOverflow = "";
let locked = false;

function cancel() {
    if (props.loading || settled.value) return;
    settled.value = true;
    emit("cancel");
}
function confirm() {
    if (props.loading || settled.value) return;
    settled.value = true;
    emit("confirm");
}
function release() {
    window.removeEventListener("keydown", onKeydown);
    if (!locked) return;
    document.body.style.overflow = previousOverflow;
    locked = false;
    if (opener?.isConnected) opener.focus();
}
function onKeydown(event: KeyboardEvent): void {
    if (!props.open) return;
    if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        cancel();
    } else if (event.key === "Tab") {
        const controls = Array.from(dialogRef.value?.querySelectorAll<HTMLElement>(
            'button:not([disabled]), input:not([disabled]), a[href], [tabindex="0"]',
        ) ?? []);
        const first = controls[0];
        const last = controls.at(-1);
        if (!first) { event.preventDefault(); dialogRef.value?.focus(); return; }
        if (event.shiftKey && (document.activeElement === first || !dialogRef.value?.contains(document.activeElement))) {
            event.preventDefault(); last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.value?.contains(document.activeElement))) {
            event.preventDefault(); first.focus();
        }
    }
}
watch(() => props.loading, (loading, previous) => {
    if (previous && !loading) settled.value = false;
});
watch(
    () => props.open,
    async (open) => {
        if (!open) { release(); return; }
        settled.value = false;
        opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        locked = true;
        window.addEventListener("keydown", onKeydown);
        await nextTick();
        if (props.open) (cancelRef.value?.$el as HTMLElement | undefined)?.focus();
    },
    { immediate: true },
);
onBeforeUnmount(release);
</script>

<template>
    <Teleport to="body">
        <div
            v-if="open"
            class="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4"
            @click.self="cancel"
        >
            <div
                ref="dialogRef"
                tabindex="-1"
                role="dialog"
                aria-modal="true"
                :aria-labelledby="titleId"
                :aria-describedby="description ? descriptionId : undefined"
                class="w-full max-w-sm rounded-card bg-surface-card p-5 shadow-pop"
            >
                <h2 :id="titleId" class="text-[15px] font-semibold text-ink-900">{{ title }}</h2>
                <p v-if="description" :id="descriptionId" class="mt-2 text-sm text-ink-500">{{ description }}</p>
                <div class="mt-5 flex justify-end gap-2">
                    <AppButton ref="cancelRef" variant="secondary" size="sm" @click="cancel">
                        {{ cancelText }}
                    </AppButton>
                    <AppButton
                        :danger="danger"
                        size="sm"
                        :loading="loading"
                        @click="confirm"
                    >
                        {{ confirmText }}
                    </AppButton>
                </div>
            </div>
        </div>
    </Teleport>
</template>