// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import type { ProgressPayload } from "@/api/workspace";
const { fetchProgress } = vi.hoisted(() => ({ fetchProgress: vi.fn() }));
vi.mock("@/api/workspace", () => ({ fetchProgress }));
import { useLearnerStateStore } from "../learnerState";

beforeEach(() => { setActivePinia(createPinia()); fetchProgress.mockReset(); });

it("navigation follows current workspace progress and ignores an older response", async () => {
    let resolveOld!: (data: ProgressPayload) => void;
    fetchProgress.mockImplementationOnce(() => new Promise<ProgressPayload>((resolve) => { resolveOld = resolve; }));
    const newer = {lessons: [{lessonSlug: "polars-basics", status: "completed", lastActivityAt: "2026-10-31T12:00:00Z"}], tracks: [], summary: {}} as ProgressPayload;
    fetchProgress.mockResolvedValueOnce(newer);
    const store = useLearnerStateStore();
    const olderRequest = store.syncFromServer();
    await store.syncFromServer();
    resolveOld({lessons: [], tracks: [], summary: {}} as unknown as ProgressPayload);
    await olderRequest;
    expect(store.totalCompleted).toBe(1);
    expect(store.lastVisitedSlug).toBe("polars-basics");
    expect("completeLesson" in store).toBe(false);
});
