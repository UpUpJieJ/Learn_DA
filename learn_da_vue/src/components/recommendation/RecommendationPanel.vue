<script setup lang="ts">
import { getRecommendationStyle } from "@/lib/recommendation";
import type { RecommendationResponse } from "@/types/api";

// =====================================================
// RecommendationPanel（阶段 4 Task 2.3）
//
// 统一 Learning / LessonDetail / Dashboard 三处的
// 下一步建议渲染与交互。页面只传数据并处理导航。
// =====================================================

defineProps<{
    recommendation: RecommendationResponse | null;
}>();

const emit = defineEmits<{
    navigate: [slug: string];
}>();
</script>

<template>
    <div
        v-if="recommendation?.primary"
        class="rounded-xl border transition-all"
        :class="getRecommendationStyle(recommendation.primary).containerClass"
    >
        <div class="flex items-start gap-4 p-5">
            <div
                class="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                :class="getRecommendationStyle(recommendation.primary).badgeClass"
            >
                <span class="text-2xl">{{ getRecommendationStyle(recommendation.primary).icon }}</span>
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1.5">
                    <p
                        class="text-xs font-semibold"
                        :class="getRecommendationStyle(recommendation.primary).labelClass"
                    >
                        {{ getRecommendationStyle(recommendation.primary).label }}
                    </p>
                    <span
                        v-if="getRecommendationStyle(recommendation.primary).priorityBadge"
                        class="px-2 py-0.5 rounded-full text-xs font-medium"
                        :class="getRecommendationStyle(recommendation.primary).badgeClass"
                    >
                        {{ getRecommendationStyle(recommendation.primary).priorityBadge }}
                    </span>
                </div>
                <h3 class="text-base font-bold text-slate-800 mb-2">
                    {{ recommendation.primary.targetTitle }}
                </h3>
                <p class="text-sm text-slate-600 leading-relaxed mb-4">
                    {{ recommendation.primary.reason }}
                </p>
                <div class="flex items-center gap-3">
                    <button
                        class="px-5 py-2 text-white text-sm font-medium rounded-lg transition-all"
                        :class="getRecommendationStyle(recommendation.primary).buttonClass"
                        @click="emit('navigate', recommendation.primary.targetSlug)"
                    >
                        {{ recommendation.primary.actionLabel }}
                    </button>
                </div>
            </div>
        </div>

        <!-- 备选建议（如果有） -->
        <div
            v-if="recommendation.alternatives && recommendation.alternatives.length > 0"
            class="border-t border-slate-200/50 px-5 py-3 bg-white/30"
        >
            <p class="text-xs text-slate-500 font-medium mb-2">其他选择：</p>
            <div class="flex flex-wrap gap-2">
                <button
                    v-for="alt in recommendation.alternatives"
                    :key="alt.targetSlug"
                    class="px-3 py-1.5 text-xs font-medium rounded-lg bg-white border border-slate-200 text-slate-700 hover:border-slate-300 hover:shadow-sm transition-all"
                    @click="emit('navigate', alt.targetSlug)"
                >
                    {{ alt.targetTitle }}
                </button>
            </div>
        </div>
    </div>
</template>
