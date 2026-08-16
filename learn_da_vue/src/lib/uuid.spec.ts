import { describe, expect, it } from "vitest";
import { randomId } from "./uuid";

describe("randomId", () => {
    it("返回 UUID v4 格式", () => {
        expect(randomId()).toMatch(
            /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
        );
    });

    it("连续调用不重复", () => {
        const ids = new Set(Array.from({ length: 1000 }, () => randomId()));
        expect(ids.size).toBe(1000);
    });
});
