<script setup lang="ts">
import { computed } from "vue";
import { useToast } from "@/composables/useToast";

// =====================================================
// CodeOutput：执行输出面板（实验室与工作区共用）
//
// 展示 stdout / stderr / 耗时，并提供复制。
// 只读展示，不负责执行；执行状态由父组件传入。
// =====================================================

type OutputStatus = "idle" | "running" | "success" | "error";

const props = withDefaults(
    defineProps<{
        stdout?: string | null;
        stderr?: string | null;
        durationMs?: number | null;
        status?: OutputStatus;
        /** 面板高度（Tailwind 类，由父组件决定在布局里的高度） */
        minHeightClass?: string;
    }>(),
    { stdout: "", stderr: "", status: "idle", minHeightClass: "min-h-[120px]" },
);

const toast = useToast();

const hasOutput = computed(() => Boolean(props.stdout || props.stderr));
const isError = computed(() => props.status === "error" || Boolean(props.stderr));
const statusLabel = computed(() => {
    if (props.status === "running") return "运行中…";
    if (props.status === "error" || props.stderr) return "失败";
    if (props.status === "success") return "成功";
    return "待运行";
});

const body = computed(() => [props.stdout, props.stderr].filter(Boolean).join("\n"));

async function copyOutput(): Promise<void> {
    if (!body.value) return;
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(body.value);
        } else {
            const previous = document.activeElement as HTMLElement | null;
            const area = document.createElement("textarea");
            area.value = body.value;
            area.setAttribute("readonly", "");
            area.style.cssText = "position:fixed;left:-9999px;top:0";
            document.body.append(area);
            try {
                area.select();
                if (!document.execCommand("copy")) throw new Error("copy failed");
            } finally {
                area.remove();
                previous?.focus();
            }
        }
        toast.success("输出已复制");
    } catch {
        toast.error("复制失败，请手动选择文本");
    }
}
</script>

<template>
    <div class="overflow-hidden rounded-card border border-editor-line bg-editor-bg">
        <div class="flex items-center justify-between gap-3 border-b border-editor-line px-3 py-2">
            <div class="flex items-center gap-2 text-xs text-editor-ink/60">
                <span
                    class="size-1.5 rounded-pill"
                    :class="isError ? 'bg-err-500' : status === 'success' ? 'bg-ok-500' : 'bg-editor-ink/30'"
                    aria-hidden="true"
                />
                <span>输出</span>
                <span class="text-editor-ink/65">·</span>
                <span :class="isError ? 'text-err-500' : ''">{{ statusLabel }}</span>
                <span v-if="durationMs != null" class="text-editor-ink/65">{{ durationMs }}ms</span>
            </div>
            <button
                v-if="hasOutput"
                type="button"
                class="rounded-control px-2 py-1 text-xs text-editor-ink/60 transition-colors hover:bg-editor-ink/10 hover:text-editor-ink"
                @click="copyOutput"
            >
                复制
            </button>
        </div>
        <pre
            role="log"
            aria-live="polite"
            aria-label="执行输出"
            class="overflow-auto px-3 py-2.5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-words"
            :class="[minHeightClass, 'text-editor-ink/85']"
        ><span v-if="stdout" class="block">{{ stdout }}</span><span v-if="stderr" class="block text-err-500">{{ stderr }}</span><span v-if="!hasOutput">运行后在这里看到输出</span></pre>
    </div>
</template>
