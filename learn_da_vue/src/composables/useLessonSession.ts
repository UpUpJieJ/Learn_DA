import { computed, ref, watch, type Ref } from "vue";
import { fetchLessonBySlug } from "@/api/learning";
import { getRecommendations } from "@/api/recommendation";
import { useLearnerStateStore } from "@/stores/learnerState";
import type { LessonDetail, RecommendationResponse } from "@/types/api";

// =====================================================
// useLessonSession：课程页工作流
//
// 职责（阶段 4 Task 2）：
// - 课程加载 + 推荐并行获取，lesson_start 事件上报（唯一上报点）；
// - 完成/撤销状态（learnerState store 乐观更新 + 幂等事件）；
// - 推荐刷新（完成状态变化后自动重新拉取）。
// 页面只负责 DOM 副作用（目录、滚动监听、动画）。
// =====================================================

export type SlugSource = Ref<string> | (() => string);

function toSlug(source: SlugSource): string {
    return typeof source === "function" ? source() : source.value;
}

export function useLessonSession(slugSource: SlugSource) {
    const lesson = ref<LessonDetail | null>(null);
    const isLoading = ref(false);
    const errorMsg = ref<string | null>(null);
    const recommendation = ref<RecommendationResponse | null>(null);

    const learnerStateStore = useLearnerStateStore();

    const isCompleted = computed(() =>
        lesson.value ? learnerStateStore.isLessonCompleted(lesson.value.slug) : false,
    );

    /** 加载课程与推荐；成功返回课程数据，失败返回 null 并写 errorMsg。 */
    async function load(): Promise<LessonDetail | null> {
        const slug = toSlug(slugSource);
        if (!slug) return null;

        isLoading.value = true;
        errorMsg.value = null;
        lesson.value = null;
        recommendation.value = null;

        try {
            const [lessonData, recommendationData] = await Promise.all([
                fetchLessonBySlug(slug),
                getRecommendations({ currentLesson: slug }).catch(() => null),
            ]);
            lesson.value = lessonData;
            recommendation.value = recommendationData;
            // 阶段 1：唯一的 lesson_start 上报点，后端同事务联动 LearnerState 投影
            await learnerStateStore.recordLessonStart(slug);
            return lessonData;
        } catch (err) {
            errorMsg.value =
                err instanceof Error ? err.message : "课程内容加载失败，请稍后重试";
            return null;
        } finally {
            isLoading.value = false;
        }
    }

    /** 重新拉取推荐（完成状态变化后调用）。失败时保持旧值。 */
    async function refreshRecommendation(): Promise<void> {
        const slug = toSlug(slugSource);
        if (!slug) return;
        recommendation.value = await getRecommendations({ currentLesson: slug }).catch(
            () => recommendation.value,
        );
    }

    /** 标记完成（幂等，后端按 eventId 去重）。 */
    async function markCompleted(): Promise<boolean> {
        if (!lesson.value) return false;
        return learnerStateStore.completeLesson(lesson.value.slug);
    }

    /** 撤销完成。 */
    async function markUncompleted(): Promise<boolean> {
        if (!lesson.value) return false;
        return learnerStateStore.uncompleteLesson(lesson.value.slug);
    }

    /**
     * 完成/撤销切换，随后刷新推荐。
     * 从未完成 → 完成且成功时触发 onCompleted（供页面做动画等副作用）。
     */
    async function toggleCompleted(onCompleted?: () => void): Promise<boolean> {
        if (!lesson.value) return false;
        const wasCompleted = learnerStateStore.isLessonCompleted(lesson.value.slug);
        const ok = wasCompleted
            ? await markUncompleted()
            : await markCompleted();
        if (ok && !wasCompleted && onCompleted) {
            onCompleted();
        }
        await refreshRecommendation();
        return ok;
    }

    watch(
        () => toSlug(slugSource),
        (newSlug, oldSlug) => {
            if (newSlug && newSlug !== oldSlug) {
                void load();
            }
        },
    );

    return {
        lesson,
        isLoading,
        errorMsg,
        recommendation,
        isCompleted,
        load,
        refreshRecommendation,
        markCompleted,
        markUncompleted,
        toggleCompleted,
    };
}
