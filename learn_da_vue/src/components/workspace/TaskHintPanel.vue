<template>
    <div class="border-t border-line pt-3">
        <div class="flex items-center justify-between gap-2">
            <p class="text-[11px] text-ink-300">
                提示
                {{
                    task.hintsUsed > 0
                        ? `已用 ${task.hintsUsed}/${task.hintMaxLevel} 层`
                        : `可要 ${task.hintMaxLevel} 层`
                }}
            </p>
            <AppButton
                variant="ghost"
                size="sm"
                :loading="loading"
                :label="task.hintsUsed > 0 ? '再要一层提示' : '给点提示'"
                @click="emit('request', task.taskId)"
            >
                {{ task.hintsUsed > 0 ? "再要一层提示" : "给点提示" }}
            </AppButton>
        </div>

        <p v-if="task.hintsUsed === 0" class="mt-1 text-[11px] leading-5 text-ink-300">
            提示按你在这道任务上的失败次数逐层加深，最多 {{ task.hintMaxLevel }} 层；不会直接给整格答案。
        </p>

        <ol v-if="hints.length" class="mt-3 space-y-3">
            <li
                v-for="hint in hints"
                :key="hint.level"
                class="rounded-control bg-surface-raised p-3"
                :data-level="hint.level"
            >
                <div class="mb-1 flex items-center gap-2 text-[11px] text-ink-300">
                    <StatusPill status="passed" size="sm" :label="`L${hint.level}`" />
                    <span>{{ hint.hasNext ? "已给" : "最后一层" }}</span>
                </div>
                <!-- 内容是服务端按层确定性生成的 Markdown，不含用户输入 -->
                <div
                    class="prose-hint text-xs leading-6 text-ink-700"
                    v-html="renderMarkdown(hint.content)"
                />
            </li>
        </ol>

        <p
            v-else-if="task.hintsUsed > 0"
            class="mt-2 text-[11px] leading-5 text-ink-300"
        >
            之前用过的提示在刷新后不再重复显示；点「再要一层提示」会拿到更深的一层。
        </p>
    </div>
</template>

<script setup lang="ts">
import { AppButton, StatusPill } from "@/components/ui";
import type { HintResponse, WorkspaceTask } from "@/api/workspace";
import { renderMarkdown } from "@/lib/markdown";

defineProps<{
    task: WorkspaceTask;
    hints: HintResponse[];
    loading: boolean;
}>();

const emit = defineEmits<{ request: [taskId: string] }>();
</script>
