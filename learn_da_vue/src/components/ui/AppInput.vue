<script setup lang="ts">
import { computed, useId } from "vue";

// =====================================================
// AppInput：带标签/提示/错误态的单行输入
// 标签与输入通过 useId 关联（<label for>），错误用 aria-invalid + aria-describedby。
// =====================================================

const props = withDefaults(
    defineProps<{
        modelValue: string;
        label?: string;
        placeholder?: string;
        hint?: string;
        error?: string | null;
        type?: "text" | "search" | "email" | "password";
        disabled?: boolean;
        maxlength?: number;
    }>(),
    { type: "text", disabled: false },
);

const emit = defineEmits<{
    "update:modelValue": [value: string];
    enter: [];
}>();

const inputId = useId();
const describedBy = computed(() => {
    const ids: string[] = [];
    if (props.hint) ids.push(`${inputId}-hint`);
    if (props.error) ids.push(`${inputId}-error`);
    return ids.length ? ids.join(" ") : undefined;
});

function onInput(event: Event): void {
    emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>

<template>
    <div class="flex flex-col gap-1.5">
        <label v-if="label" :for="inputId" class="text-xs font-medium text-ink-700">
            {{ label }}
        </label>
        <input
            :id="inputId"
            :type="type"
            :value="modelValue"
            :placeholder="placeholder"
            :disabled="disabled"
            :maxlength="maxlength"
            :aria-invalid="error ? true : undefined"
            :aria-describedby="describedBy"
            class="h-10 rounded-control border bg-surface-card px-3 text-sm text-ink-900 transition-colors placeholder:text-ink-300 focus:outline-2 focus:outline-offset-1 focus:outline-brand-600 disabled:cursor-not-allowed disabled:bg-surface-raised"
            :class="error ? 'border-err-500' : 'border-line'"
            @input="onInput"
            @keyup.enter="emit('enter')"
        />
        <p v-if="error" :id="`${inputId}-error`" class="text-xs text-err-600">{{ error }}</p>
        <p v-else-if="hint" :id="`${inputId}-hint`" class="text-xs text-ink-500">{{ hint }}</p>
    </div>
</template>