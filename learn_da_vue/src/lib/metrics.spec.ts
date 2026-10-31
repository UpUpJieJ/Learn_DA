import { describe, expect, it } from "vitest";
import { formatFirstTryRate } from "./metrics";

describe("first-try rate", () => {
    it("includes tasks which were tried but never passed", () => {
        expect(formatFirstTryRate({tasksFirstTry: 2, tasksAttempted: 10})).toBe("20%");
    });
    it("does not invent a percentage for visitors without attempts", () => {
        expect(formatFirstTryRate({tasksFirstTry: 0, tasksAttempted: 0})).toBe("—");
        expect(formatFirstTryRate(null)).toBe("—");
    });
});
