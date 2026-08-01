import { describe, it, expect, vi, beforeEach } from "vitest";
import { nextTick, ref } from "vue";
import { setActivePinia, createPinia } from "pinia";
import type { LessonDetail, RecommendationResponse } from "@/types/api";

vi.mock("@/api/learning", () => ({
    fetchLessonBySlug: vi.fn(),
}));

vi.mock("@/api/recommendation", () => ({
    getRecommendations: vi.fn(),
}));

vi.mock("@/api/learnerState", () => ({
    fetchLearnerProgress: vi.fn(),
}));

vi.mock("@/api/analytics", () => ({
    trackEvent: vi.fn(),
}));

import { fetchLessonBySlug } from "@/api/learning";
import { getRecommendations } from "@/api/recommendation";
import { trackEvent } from "@/api/analytics";
import { useLearnerStateStore } from "@/stores/learnerState";
import { useLessonSession } from "@/composables/useLessonSession";

const mockedFetch = vi.mocked(fetchLessonBySlug);
const mockedRecs = vi.mocked(getRecommendations);
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
    codeExample: "print(1)",
    prevLesson: null,
    nextLesson: null,
};

const RECS: RecommendationResponse = {
    primary: null,
    alternatives: [],
};

describe("useLessonSession", () => {
    beforeEach(() => {
        localStorage.clear();
        setActivePinia(createPinia());
        mockedFetch.mockReset();
        mockedRecs.mockReset();
        mockedTrack.mockReset();
        mockedFetch.mockResolvedValue(LESSON);
        mockedRecs.mockResolvedValue(RECS);
        mockedTrack.mockResolvedValue({ recorded: true });
    });

    it("loads lesson and recommendation, records lesson_start once", async () => {
        const session = useLessonSession(() => "polars-basics");
        const result = await session.load();

        expect(result?.slug).toBe("polars-basics");
        expect(session.lesson.value?.title).toBe("Polars 基础");
        expect(session.recommendation.value).toEqual(RECS);
        expect(session.isLoading.value).toBe(false);
        expect(mockedTrack).toHaveBeenCalledTimes(1);
        expect(mockedTrack.mock.calls[0]?.[0]).toMatchObject({
            eventType: "lesson_start",
            lessonSlug: "polars-basics",
        });
    });

    it("degrades recommendation failure to null", async () => {
        mockedRecs.mockRejectedValue(new Error("down"));
        const session = useLessonSession(() => "polars-basics");
        await session.load();
        expect(session.lesson.value).not.toBeNull();
        expect(session.recommendation.value).toBeNull();
        expect(session.errorMsg.value).toBeNull();
    });

    it("sets errorMsg when lesson fetch fails", async () => {
        mockedFetch.mockRejectedValue(new Error("404"));
        const session = useLessonSession(() => "polars-basics");
        await session.load();
        expect(session.lesson.value).toBeNull();
        expect(session.errorMsg.value).toContain("404");
    });

    it("marks completed and refreshes recommendation", async () => {
        const session = useLessonSession(() => "polars-basics");
        await session.load();

        expect(session.isCompleted.value).toBe(false);
        await session.toggleCompleted(() => {});
        expect(session.isCompleted.value).toBe(true);
        // lesson_complete 事件上报
        expect(mockedTrack).toHaveBeenCalledWith(
            expect.objectContaining({ eventType: "lesson_complete" }),
        );
        // 完成状态变化后推荐刷新
        expect(mockedRecs).toHaveBeenCalledTimes(2);
    });

    it("uncompletes and triggers no completion callback", async () => {
        const session = useLessonSession(() => "polars-basics");
        await session.load();
        await session.toggleCompleted(() => {});

        let callbackCalled = false;
        const ok = await session.toggleCompleted(() => {
            callbackCalled = true;
        });

        expect(session.isCompleted.value).toBe(false);
        expect(callbackCalled).toBe(false);
        expect(mockedTrack).toHaveBeenCalledWith(
            expect.objectContaining({ eventType: "lesson_uncomplete" }),
        );
    });

    it("reloads when slug source changes", async () => {
        const slug = ref("polars-basics");
        const session = useLessonSession(slug);
        await session.load();
        expect(session.lesson.value?.slug).toBe("polars-basics");

        slug.value = "duckdb-analytics";
        mockedFetch.mockResolvedValue({ ...LESSON, slug: "duckdb-analytics" });
        await nextTick();
        await vi.waitFor(() => {
            expect(session.lesson.value?.slug).toBe("duckdb-analytics");
        });
        expect(session.lesson.value?.title).toBe("Polars 基础");
    });

    it("exposes completed state from learnerState store", async () => {
        const store = useLearnerStateStore();
        await store.completeLesson("polars-basics");

        const session = useLessonSession(() => "polars-basics");
        await session.load();
        expect(session.isCompleted.value).toBe(true);
    });
});
