import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({
    getMock: vi.fn(),
}));

vi.mock("@/api/index", () => ({
    get: getMock,
    post: vi.fn(),
}));

import { fetchPracticeStats } from "@/api/analytics";
import { resumeExercise } from "@/api/playground";

describe("Phase 2 practice API contract", () => {
    beforeEach(() => {
        getMock.mockReset();
    });

    it("uses the camelCase lessonSlug query expected by the resume endpoint", () => {
        resumeExercise("python-functions-add-bonus-v1", "python-functions");

        expect(getMock).toHaveBeenCalledWith(
            "/playground/exercises/python-functions-add-bonus-v1/resume",
            { lessonSlug: "python-functions" },
        );
    });

    it("loads server-authoritative practice metrics for Dashboard", () => {
        fetchPracticeStats();

        expect(getMock).toHaveBeenCalledWith("/analytics/practice-stats");
    });
});
