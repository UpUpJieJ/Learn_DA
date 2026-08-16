import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";
import { setActivePinia, createPinia } from "pinia";
import type { LessonDetail } from "@/types/api";

vi.mock("@/api/learning", () => ({
    fetchLessonBySlug: vi.fn(),
    fetchExamples: vi.fn(),
    fetchExample: vi.fn(),
}));

vi.mock("@/api/playground", () => ({
    resumeExercise: vi.fn(),
    executeCode: vi.fn(),
    formatCode: vi.fn(),
}));

vi.mock("@/api/learnerState", () => ({
    fetchLearnerProgress: vi.fn(),
}));

vi.mock("@/api/analytics", () => ({
    trackEvent: vi.fn(),
    saveCodeSnapshot: vi.fn(),
    fetchCodeSnapshots: vi.fn(),
}));

import { fetchLessonBySlug } from "@/api/learning";
import { resumeExercise } from "@/api/playground";
import { trackEvent } from "@/api/analytics";
import { useLearnerStateStore } from "@/stores/learnerState";
import { usePlaygroundStore } from "@/stores/playground";
import { usePlaygroundSession, RESULT_TABS } from "@/composables/usePlaygroundSession";

const mockedFetch = vi.mocked(fetchLessonBySlug);
const mockedResume = vi.mocked(resumeExercise);
const mockedTrack = vi.mocked(trackEvent);

const LESSON: LessonDetail = {
    id: 1,
    slug: "polars-basics",
    title: "Polars 基础",
    description: "",
    topic: "data-analysis",
    category: "polars",
    difficulty: "beginner",
    estimatedMinutes: 15,
    order: 1,
    tags: [],
    track: "polars_basics",
    content: "# body",
    codeExample: "print('hello')",
    prevLesson: null,
    nextLesson: null,
};

describe("usePlaygroundSession", () => {
    beforeEach(() => {
        localStorage.clear();
        setActivePinia(createPinia());
        mockedFetch.mockReset();
        mockedResume.mockReset();
        mockedTrack.mockReset();
        mockedFetch.mockResolvedValue(LESSON);
        mockedResume.mockRejectedValue(new Error("no resume"));
    });

    it("loads lesson, records lesson_start, seeds draft from codeExample", async () => {
        const session = usePlaygroundSession(() => "polars-basics");
        await session.load();

        expect(session.currentLesson.value?.slug).toBe("polars-basics");
        expect(session.draftKey.value).toBe("lesson:polars-basics");
        expect(session.hasLoadedDraft.value).toBe(true);
        const store = usePlaygroundStore();
        expect(store.code).toBe("print('hello')");
        expect(mockedTrack).toHaveBeenCalledWith(
            expect.objectContaining({ eventType: "lesson_start" }),
        );
    });

    it("resumes unfinished exercise when resume data exists", async () => {
        mockedResume.mockResolvedValue({
            exerciseId: "ex-1",
            lessonSlug: "polars-basics",
            code: "# resumed code",
            language: "python",
            isResumed: true,
            exerciseTitle: "Ex",
            objective: "",
            hints: [],
            starterCode: "starter",
        });
        const lessonWithExercise = {
            ...LESSON,
            exercise: {
                id: "ex-1",
                title: "Ex",
                language: "python",
                starterCode: "starter",
                objective: "",
                hints: [],
                validator: { type: "stdout_exact", expected: "ok" },
            },
        };
        mockedFetch.mockResolvedValue(lessonWithExercise);

        const session = usePlaygroundSession(() => "polars-basics");
        await session.load();

        const store = usePlaygroundStore();
        expect(store.isInExercise).toBe(true);
        expect(store.code).toBe("# resumed code");
    });

    it("starts exercise with starter code when resume unavailable", async () => {
        const lessonWithExercise = {
            ...LESSON,
            exercise: {
                id: "ex-1",
                title: "Ex",
                language: "python",
                starterCode: "starter",
                objective: "",
                hints: [],
                validator: { type: "stdout_exact", expected: "ok" },
            },
        };
        mockedFetch.mockResolvedValue(lessonWithExercise);

        const session = usePlaygroundSession(() => "polars-basics");
        await session.load();

        const store = usePlaygroundStore();
        expect(store.isInExercise).toBe(true);
        expect(store.code).toBe("starter");
    });

    it("recovers draft from localState when present", async () => {
        const localState = (await import("@/stores/localState")).useLocalStateStore();
        const store = usePlaygroundStore();
        store.setCode("stale");
        store.setLanguage("python");
        localState.savePlaygroundDraft("lesson:polars-basics", "# draft code", "python");

        const session = usePlaygroundSession(() => "polars-basics");
        await session.load();

        expect(store.code).toBe("# draft code");
    });

    it("completes lesson through learnerState store once", async () => {
        const session = usePlaygroundSession(() => "polars-basics");
        await session.load();

        const ok = await session.completeLesson();

        expect(ok).toBe(true);
        const learnerStore = useLearnerStateStore();
        expect(learnerStore.isLessonCompleted("polars-basics")).toBe(true);
        // 只走 store 幂等写路径，不重复上报原始事件
        expect(mockedTrack).toHaveBeenCalledTimes(2); // lesson_start + lesson_complete(store 内部)
    });

    it("exposes result tabs and keeps active tab state", () => {
        expect(RESULT_TABS).toContain("assistant");
        expect(RESULT_TABS).toContain("attempts");

        const session = usePlaygroundSession(() => "polars-basics");
        expect(session.activeResultTab.value).toBe("assistant");
        session.activeResultTab.value = "output";
        expect(session.activeResultTab.value).toBe("output");
    });

    it("setCodeAndSaveDraft updates editor and draft storage", async () => {
        const session = usePlaygroundSession(() => "polars-basics");
        session.setCodeAndSaveDraft("print(2)");

        const store = usePlaygroundStore();
        const localState = (await import("@/stores/localState")).useLocalStateStore();
        expect(store.code).toBe("print(2)");
        expect(localState.getPlaygroundDraft("lesson:polars-basics")?.code).toBe(
            "print(2)",
        );
    });

    it("shows attempts tab only when an exercise is active", () => {
        const session = usePlaygroundSession(() => undefined);
        expect(session.resultTabs.value).not.toContain("attempts");
        expect(session.resultTabs.value).toContain("snapshots");

        const store = usePlaygroundStore();
        store.startExercise(
            {
                id: "ex-1",
                title: "Ex",
                language: "python",
                starterCode: "",
                objective: "",
                hints: [],
                validator: { type: "stdout_exact", expected: "ok" },
            },
            "polars-basics",
            "code",
        );
        expect([...session.resultTabs.value]).toEqual([...RESULT_TABS]);
    });
});
