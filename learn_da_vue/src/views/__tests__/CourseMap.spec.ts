// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
const { fetchProgress, push } = vi.hoisted(() => ({ fetchProgress: vi.fn(), push: vi.fn() }));
vi.mock("@/api/workspace", () => ({ fetchProgress }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));
import CourseMap from "../CourseMap.vue";

it("keeps a review action after all courses are complete", async () => {
    fetchProgress.mockResolvedValue({lessons: [{lessonSlug: "polars-basics", title: "Polars 基础", status: "completed", totalTasks: 3, passedTasks: 3, currentTaskId: null, track: "polars"}],
        tracks: [], summary: {tasksPassed: 3, tasksTotal: 3, lessonsCompleted: 1, lessonsTotal: 1, lessonsStarted: 1, attemptsTotal: 3}});
    const wrapper = mount(CourseMap);
    await flushPromises();
    const review = wrapper.findAll("button").find((button) => button.text() === "复习");
    expect(review).toBeTruthy();
    await review!.trigger("click");
    expect(push).toHaveBeenCalledWith({path: "/lesson/polars-basics", query: undefined});
    wrapper.unmount();
});
