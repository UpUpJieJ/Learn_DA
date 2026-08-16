import { computed, ref, type Ref } from "vue";
import { fetchLessonBySlug } from "@/api/learning";
import { resumeExercise } from "@/api/playground";
import { useLearnerStateStore } from "@/stores/learnerState";
import { useLocalStateStore } from "@/stores/localState";
import { usePlaygroundStore } from "@/stores/playground";
import type { LessonDetail } from "@/types/api";

// =====================================================
// usePlaygroundSession：Playground 课程会话工作流
//
// 职责（阶段 4 Task 2）：
// - 课程加载 + 草稿恢复 / 练习恢复（结构化练习优先）；
// - lesson_start 上报（唯一上报点）；
// - 完成课程（收口到 learnerState store 幂等写路径）；
// - 结果 Tab 选择（输出/数据/历史/尝试/助手）。
// 页面只保留布局、示例选择器、快照 UI 与编辑器 DOM。
// =====================================================

export type ResultTab =
    | "output"
    | "dataframe"
    | "history"
    | "attempts"
    | "assistant";

export const RESULT_TABS: readonly ResultTab[] = [
    "output",
    "dataframe",
    "history",
    "attempts",
    "assistant",
];

export type PlaygroundSlugSource = Ref<string | undefined> | (() => string | undefined);

function toSlug(source: PlaygroundSlugSource): string | undefined {
    return typeof source === "function" ? source() : source.value;
}

export function usePlaygroundSession(slugSource: PlaygroundSlugSource) {
    const playgroundStore = usePlaygroundStore();
    const localStateStore = useLocalStateStore();
    const learnerStateStore = useLearnerStateStore();

    const currentLesson = ref<LessonDetail | null>(null);
    const isLoadingLesson = ref(false);
    const hasLoadedDraft = ref(false);
    const isCompletingLesson = ref(false);

    const activeResultTab = ref<ResultTab>("assistant");
    // 「尝试」tab 只在结构化练习激活时展示（展示真实 attempt 记录）
    const resultTabs = computed<readonly ResultTab[]>(() =>
        playgroundStore.activeExercise
            ? RESULT_TABS
            : RESULT_TABS.filter((t) => t !== "attempts"),
    );

    const draftKey = computed(() => {
        const slug = toSlug(slugSource);
        return slug ? `lesson:${slug}` : "default";
    });

    /** 从本地草稿恢复；无草稿时使用课程示例代码。 */
    function loadDraftForContext(seedCode?: string) {
        const draft = localStateStore.getPlaygroundDraft(draftKey.value);
        hasLoadedDraft.value = false;

        if (draft) {
            playgroundStore.setLanguage(draft.language);
            playgroundStore.setCode(draft.code);
        } else if (seedCode !== undefined) {
            playgroundStore.setLanguage("python");
            playgroundStore.setCode(seedCode);
        }

        hasLoadedDraft.value = true;
    }

    /** 加载课程：结构化练习优先（恢复上次尝试），否则恢复草稿。 */
    async function load(): Promise<void> {
        const slug = toSlug(slugSource);
        if (!slug) {
            currentLesson.value = null;
            return;
        }
        isLoadingLesson.value = true;
        try {
            currentLesson.value = await fetchLessonBySlug(slug);
            // 阶段 1：唯一的 lesson_start 上报点
            await learnerStateStore.recordLessonStart(slug);

            const exercise = currentLesson.value.exercise;
            if (exercise) {
                // 尝试恢复上次未完成的练习
                try {
                    const resumeData = await resumeExercise(exercise.id, slug);
                    if (resumeData.isResumed) {
                        playgroundStore.startExercise(exercise, slug, resumeData.code);
                    } else {
                        playgroundStore.startExercise(exercise, slug, exercise.starterCode);
                    }
                } catch {
                    playgroundStore.startExercise(exercise, slug, exercise.starterCode);
                }
            } else {
                loadDraftForContext(currentLesson.value.codeExample);
            }
        } catch (err) {
            console.error("加载课程失败:", err);
            currentLesson.value = null;
            loadDraftForContext();
        } finally {
            isLoadingLesson.value = false;
        }
    }

    /** 完成课程：收口到 learnerState store（内部走 /analytics/track 幂等写路径）。 */
    async function completeLesson(): Promise<boolean> {
        if (!currentLesson.value || isCompletingLesson.value) return false;
        isCompletingLesson.value = true;
        try {
            return await learnerStateStore.completeLesson(currentLesson.value.slug);
        } catch (err) {
            console.error("完成课程失败:", err);
            return false;
        } finally {
            isCompletingLesson.value = false;
        }
    }

    /** 设置代码并同步保存草稿（示例加载 / 快照恢复共用）。 */
    function setCodeAndSaveDraft(code: string): void {
        playgroundStore.setCode(code);
        localStateStore.savePlaygroundDraft(
            draftKey.value,
            code,
            playgroundStore.language,
        );
    }

    return {
        currentLesson,
        isLoadingLesson,
        hasLoadedDraft,
        isCompletingLesson,
        activeResultTab,
        resultTabs,
        draftKey,
        load,
        loadDraftForContext,
        completeLesson,
        setCodeAndSaveDraft,
    };
}
