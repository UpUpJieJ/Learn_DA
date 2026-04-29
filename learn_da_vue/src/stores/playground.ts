import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { executeCode, formatCode } from "@/api/playground";
import type { ExecuteResponse } from "@/types/api";

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

    // ---- 执行历史 ----
    const history = ref<ExecutionRecord[]>([]);
    const maxHistorySize = 20;

    // ---- 格式化状态 ----
    const isFormatting = ref(false);

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

    // =====================================================
    // Actions
    // =====================================================

    async function runCode() {
        if (isExecuting.value || !code.value.trim()) return undefined;

        isExecuting.value = true;
        executionError.value = null;

        try {
            const response = await executeCode({
                code: code.value,
                language: language.value,
            });

            lastResponse.value = response;
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
                usedSandbox: "none",
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

    function setLanguage(lang: "python" | "sql") {
        language.value = lang;
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

        // computed
        isLastSuccess,
        stdout,
        stderr,
        executionTime,
        sortedHistory,
        hasOutput,

        // actions
        runCode,
        formatCurrentCode,
        clearEditor,
        clearOutput,
        loadFromHistory,
        clearHistory,
        setCode,
        setLanguage,
    };
});
