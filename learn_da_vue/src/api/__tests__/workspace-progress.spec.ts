import { beforeEach, expect, it, vi } from "vitest";
import type { ProgressPayload } from "@/api/workspace";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/api/index", () => ({ get, post: vi.fn(), put: vi.fn() }));
import { fetchProgress } from "@/api/workspace";

beforeEach(() => get.mockReset());

it("shares a concurrent progress read between navigation and the course map", async () => {
    let resolve!: (value: ProgressPayload) => void;
    const payload = { lessons: [], tracks: [], summary: {} } as ProgressPayload;
    get.mockImplementationOnce(() => new Promise<ProgressPayload>((done) => { resolve = done; }));
    const navigation = fetchProgress();
    const courseMap = fetchProgress();
    expect(get).toHaveBeenCalledTimes(1);
    resolve(payload);
    expect(await navigation).toBe(payload);
    expect(await courseMap).toBe(payload);
    get.mockResolvedValueOnce(payload);
    await fetchProgress();
    expect(get).toHaveBeenCalledTimes(2);
});

it("clears the shared read after failure so the next read can retry", async () => {
    let reject!: (reason: Error) => void;
    get.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    const navigation = fetchProgress();
    const courseMap = fetchProgress();
    const both = Promise.allSettled([navigation, courseMap]);
    const error = new Error("temporarily unavailable");
    reject(error);
    expect(await both).toEqual([{ status: "rejected", reason: error }, { status: "rejected", reason: error }]);
    expect(get).toHaveBeenCalledTimes(1);
    const payload = { lessons: [], tracks: [], summary: {} } as ProgressPayload;
    get.mockResolvedValueOnce(payload);
    expect(await fetchProgress()).toBe(payload);
    expect(get).toHaveBeenCalledTimes(2);
});
