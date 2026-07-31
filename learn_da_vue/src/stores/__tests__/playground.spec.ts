/**
 * Task 6: Playground Store 测试
 *
 * 验收标准：
 * - 练习状态管理（startExercise/endExercise）
 * - 验证状态跟踪
 * - 执行请求携带练习参数
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { usePlaygroundStore } from "@/stores/playground";
import type { ExerciseDefinition } from "@/types/api";

// Mock the API module
vi.mock("@/api/playground", () => ({
    executeCode: vi.fn(),
    formatCode: vi.fn(),
    resumeExercise: vi.fn(),
    listExerciseAttempts: vi.fn(),
    getExerciseStats: vi.fn(),
}));

const mockExercise: ExerciseDefinition = {
    id: "python-functions-add-bonus-v1",
    title: "为成绩添加 bonus",
    language: "python",
    starterCode: "def add_bonus(score):\n    return score + 5\nprint(add_bonus(95))",
    objective: "定义接收 score 的函数，返回加 5 后的值。",
    hints: ["先把 score 放在函数参数中", "用 return 返回 score + 5"],
    validator: {
        type: "stdout_exact",
        expected: "100",
    },
};

describe("Playground Store - Phase 2", () => {
    beforeEach(() => {
        setActivePinia(createPinia());
        vi.clearAllMocks();
    });

    describe("startExercise", () => {
        it("should set active exercise and lesson slug", () => {
            const store = usePlaygroundStore();

            store.startExercise(mockExercise, "python-functions");

            expect(store.activeExercise).toEqual(mockExercise);
            expect(store.activeLessonSlug).toBe("python-functions");
            expect(store.isInExercise).toBe(true);
        });

        it("should load starter code when no custom code provided", () => {
            const store = usePlaygroundStore();

            store.startExercise(mockExercise, "python-functions");

            expect(store.code).toBe(mockExercise.starterCode);
        });

        it("should use custom code when provided", () => {
            const store = usePlaygroundStore();
            const customCode = "print('custom')";

            store.startExercise(mockExercise, "python-functions", customCode);

            expect(store.code).toBe(customCode);
        });

        it("should reset exercisePassed state", () => {
            const store = usePlaygroundStore();
            store.exercisePassed = true;

            store.startExercise(mockExercise, "python-functions");

            expect(store.exercisePassed).toBe(false);
        });

        it("should set language from exercise", () => {
            const store = usePlaygroundStore();

            store.startExercise(mockExercise, "python-functions");

            expect(store.language).toBe("python");
        });
    });

    describe("endExercise", () => {
        it("should clear exercise state", () => {
            const store = usePlaygroundStore();
            store.startExercise(mockExercise, "python-functions");

            store.endExercise();

            expect(store.activeExercise).toBeNull();
            expect(store.activeLessonSlug).toBeNull();
            expect(store.isInExercise).toBe(false);
            expect(store.exercisePassed).toBe(false);
        });
    });

    describe("verification state", () => {
        it("should track verification passed", () => {
            const store = usePlaygroundStore();
            store.startExercise(mockExercise, "python-functions");

            // Simulate a successful verification response
            store.lastResponse = {
                status: "success",
                stdout: "100",
                stderr: "",
                executionTime: 50,
                resultType: "text",
                dataframe: null,
                verification: {
                    status: "passed",
                    failureReason: null,
                    validatorType: "stdout_exact",
                },
            };

            expect(store.lastVerification?.status).toBe("passed");
            expect(store.isVerificationPassed).toBe(true);
        });

        it("should track verification failed", () => {
            const store = usePlaygroundStore();
            store.startExercise(mockExercise, "python-functions");

            store.lastResponse = {
                status: "success",
                stdout: "99",
                stderr: "",
                executionTime: 50,
                resultType: "text",
                dataframe: null,
                verification: {
                    status: "failed",
                    failureReason: "stdout_exact_mismatch",
                    validatorType: "stdout_exact",
                },
            };

            expect(store.lastVerification?.status).toBe("failed");
            expect(store.isVerificationPassed).toBe(false);
        });

        it("should return null verification for normal execution", () => {
            const store = usePlaygroundStore();

            store.lastResponse = {
                status: "success",
                stdout: "hello",
                stderr: "",
                executionTime: 50,
                resultType: "text",
                dataframe: null,
            };

            expect(store.lastVerification).toBeNull();
        });
    });

    describe("exercisePassed persistence", () => {
        it("should persist exercisePassed after verification passed", () => {
            const store = usePlaygroundStore();
            store.startExercise(mockExercise, "python-functions");

            // First verification passes
            store.lastResponse = {
                status: "success",
                stdout: "100",
                stderr: "",
                executionTime: 50,
                resultType: "text",
                dataframe: null,
                verification: { status: "passed" },
            };
            store.exercisePassed = true;

            // Later execution without verification
            store.lastResponse = {
                status: "success",
                stdout: "other",
                stderr: "",
                executionTime: 50,
                resultType: "text",
                dataframe: null,
            };

            // Should still be considered passed
            expect(store.isVerificationPassed).toBe(true);
        });

        it("should reset exercisePassed on resetExercisePassed", () => {
            const store = usePlaygroundStore();
            store.exercisePassed = true;

            store.resetExercisePassed();

            expect(store.exercisePassed).toBe(false);
        });
    });
});
