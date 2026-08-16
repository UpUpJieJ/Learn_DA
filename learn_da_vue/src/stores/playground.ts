import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { executeCode, formatCode } from "@/api/playground";
import { randomId } from "@/lib/uuid";
import type {
    ExecuteResponse,
    ExecutionSource,
    ExerciseDefinition,
    ExerciseVerification,
} from "@/types/api";

// =====================================================
// 执行历史记录条目
// =====================================================

export interface ExecutionRecord {
    id: string;
    code: string;
    response: ExecuteResponse;
    timestamp: number;
}

// =====================================================
// Playground Store
// =====================================================

export const usePlaygroundStore = defineStore("playground", () => {
    // ---- 编辑器状态 ----
    const code = ref<string>(
        `import polars as pl\n\n# 创建一个简单的 DataFrame\ndf = pl.DataFrame({\n    "name": ["Alice", "Bob", "Charlie"],\n    "age": [25, 30, 35],\n    "score": [88.5, 92.0, 78.3],\n})\n\nprint(df)\n`,
    );
    const language = ref<"python" | "sql">("python");

    // ---- 执行状态 ----
    const isExecuting = ref(false);
    const lastResponse = ref<ExecuteResponse | null>(null);
    const executionError = ref<string | null>(null);
    const nextExecutionSource = ref<ExecutionSource>("playground");

    // ---- 执行历史 ----
    const history = ref<ExecutionRecord[]>([]);
    const maxHistorySize = 20;

    // ---- 格式化状态 ----
    const isFormatting = ref(false);

    // ---- Phase 2: 练习状态 ----
    const activeExercise = ref<ExerciseDefinition | null>(null);
    const activeLessonSlug = ref<string | null>(null);
    const exercisePassed = ref(false);

    // =====================================================
    // Computed
    // =====================================================

    const isLastSuccess = computed(
        () => lastResponse.value?.status === "success",
    );

    const stdout = computed(() => lastResponse.value?.stdout ?? "");
    const stderr = computed(() => lastResponse.value?.stderr ?? "");

    const executionTime = computed(
        () => lastResponse.value?.executionTime ?? 0,
    );

    const sortedHistory = computed(() =>
        [...history.value].sort((a, b) => b.timestamp - a.timestamp),
    );

    const hasOutput = computed(
        () =>
            !!lastResponse.value &&
            (stdout.value.length > 0 || stderr.value.length > 0),
    );

    /** Phase 2: 当前是否有活跃练习 */
    const isInExercise = computed(() => activeExercise.value !== null);

    /** Phase 2: 最近一次验证结果 */
    const lastVerification = computed<ExerciseVerification | null>(
        () => lastResponse.value?.verification ?? null,
    );

    /** Phase 2: 验证是否通过 */
    const isVerificationPassed = computed(
        () =>
            lastVerification.value?.status === "passed" || exercisePassed.value,
    );

    // =====================================================
    // Actions
    // =====================================================

    async function runCode() {
        if (isExecuting.value || !code.value.trim()) return undefined;

        isExecuting.value = true;
        executionError.value = null;

        const source = nextExecutionSource.value;
        nextExecutionSource.value = "playground"; // reset after use

        try {
            const response = await executeCode({
                code: code.value,
                language: language.value,
                requestId: randomId(),
                source,
                // Phase 2: 练习执行参数
                lessonSlug: activeLessonSlug.value ?? undefined,
                exerciseId: activeExercise.value?.id ?? undefined,
            });

            // Don't store rejected/unavailable responses as successes
            if (response.status === "rejected" || response.status === "unavailable") {
                lastResponse.value = response;
                executionError.value =
                    response.status === "rejected"
                        ? "该代码未获准运行"
                        : "执行服务暂时不可用";
                return response;
            }

            lastResponse.value = response;

            // Phase 2: 检查验证结果
            if (response.verification?.status === "passed") {
                exercisePassed.value = true;
            }

            addToHistory(code.value, response);
            return response;
        } catch (err) {
            const message =
                err instanceof Error ? err.message : "代码执行失败，请稍后重试";
            executionError.value = message;

            lastResponse.value = {
                status: "error",
                stdout: "",
                stderr: message,
                executionTime: 0,
                resultType: "error",
                dataframe: null,
            };
            return lastResponse.value;
        } finally {
            isExecuting.value = false;
        }
    }

    async function formatCurrentCode() {
        if (isFormatting.value || !code.value.trim()) return;

        isFormatting.value = true;

        try {
            const result = await formatCode({
                code: code.value,
                language: "python",
            });

            if (result.changed) {
                code.value = result.formatted;
            }

            return result.changed;
        } catch (err) {
            console.error("[Playground] 格式化失败:", err);
            return false;
        } finally {
            isFormatting.value = false;
        }
    }

    function clearEditor() {
        code.value = "";
        clearOutput();
    }

    function clearOutput() {
        lastResponse.value = null;
        executionError.value = null;
    }

    function loadFromHistory(record: ExecutionRecord) {
        code.value = record.code;
        lastResponse.value = record.response;
        executionError.value = null;
    }

    function clearHistory() {
        history.value = [];
    }

    function setCode(newCode: string) {
        code.value = newCode;
    }

    function loadAgentSuggestion(agentCode: string) {
        code.value = agentCode;
        nextExecutionSource.value = "agent_suggested";
    }

    function setLanguage(lang: "python" | "sql") {
        language.value = lang;
    }

    // ---- Phase 2: 练习管理 ----

    /** 开始练习 */
    function startExercise(
        exercise: ExerciseDefinition,
        lessonSlug: string,
        starterCode?: string,
    ) {
        activeExercise.value = exercise;
        activeLessonSlug.value = lessonSlug;
        exercisePassed.value = false;
        if (starterCode !== undefined) {
            code.value = starterCode;
        } else if (exercise.starterCode) {
            code.value = exercise.starterCode;
        }
        language.value = (exercise.language as "python" | "sql") ?? "python";
        clearOutput();
    }

    /** 结束练习 */
    function endExercise() {
        activeExercise.value = null;
        activeLessonSlug.value = null;
        exercisePassed.value = false;
    }

    /** 重置练习通过状态 */
    function resetExercisePassed() {
        exercisePassed.value = false;
    }

    // =====================================================
    // 私有工具函数
    // =====================================================

    function addToHistory(executedCode: string, response: ExecuteResponse) {
        const record: ExecutionRecord = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            code: executedCode,
            response,
            timestamp: Date.now(),
        };

        history.value.unshift(record);

        if (history.value.length > maxHistorySize) {
            history.value = history.value.slice(0, maxHistorySize);
        }
    }

    // =====================================================
    // 返回
    // =====================================================

    return {
        // state
        code,
        language,
        isExecuting,
        isFormatting,
        lastResponse,
        executionError,
        history,
        // Phase 2
        activeExercise,
        activeLessonSlug,
        exercisePassed,

        // computed
        isLastSuccess,
        stdout,
        stderr,
        executionTime,
        sortedHistory,
        hasOutput,
        isInExercise,
        lastVerification,
        isVerificationPassed,

        // actions
        runCode,
        formatCurrentCode,
        clearEditor,
        clearOutput,
        loadFromHistory,
        clearHistory,
        setCode,
        setLanguage,
        loadAgentSuggestion,
        nextExecutionSource,
        startExercise,
        endExercise,
        resetExercisePassed,
    };
});
