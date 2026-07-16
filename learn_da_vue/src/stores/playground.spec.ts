import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import type { ExecuteResponse } from "@/types/api";

// Mock the API module
vi.mock("@/api/playground", () => ({
    executeCode: vi.fn(),
    formatCode: vi.fn(),
}));

import { executeCode } from "@/api/playground";
import { usePlaygroundStore } from "@/stores/playground";

const mockedExecuteCode = vi.mocked(executeCode);

const SUCCESS_RESPONSE: ExecuteResponse = {
    status: "success",
    stdout: "hello\n",
    stderr: "",
    executionTime: 10,
    resultType: "text",
    dataframe: null,
};

const REJECTED_RESPONSE: ExecuteResponse = {
    status: "rejected",
    stdout: "",
    stderr: "",
    executionTime: 0,
    resultType: "error",
    dataframe: null,
};

const UNAVAILABLE_RESPONSE: ExecuteResponse = {
    status: "unavailable",
    stdout: "",
    stderr: "",
    executionTime: 0,
    resultType: "error",
    dataframe: null,
};

describe("playground store – source propagation", () => {
    beforeEach(() => {
        setActivePinia(createPinia());
        mockedExecuteCode.mockReset();
    });

    it("sends source=agent_suggested after loadAgentSuggestion", async () => {
        mockedExecuteCode.mockResolvedValue(SUCCESS_RESPONSE);

        const store = usePlaygroundStore();
        store.loadAgentSuggestion("print(1)");

        expect(store.code).toBe("print(1)");
        expect(store.nextExecutionSource).toBe("agent_suggested");

        await store.runCode();

        expect(mockedExecuteCode).toHaveBeenCalledOnce();
        const payload = mockedExecuteCode.mock.calls[0][0];
        expect(payload.source).toBe("agent_suggested");
        expect(payload.requestId).toBeDefined();
        expect(typeof payload.requestId).toBe("string");
    });

    it("resets source to playground after agent_suggested execution", async () => {
        mockedExecuteCode.mockResolvedValue(SUCCESS_RESPONSE);

        const store = usePlaygroundStore();
        store.loadAgentSuggestion("print(1)");
        await store.runCode();

        // Next run should be source=playground
        await store.runCode();

        const secondPayload = mockedExecuteCode.mock.calls[1][0];
        expect(secondPayload.source).toBe("playground");
    });

    it("sends source=playground for normal runs", async () => {
        mockedExecuteCode.mockResolvedValue(SUCCESS_RESPONSE);

        const store = usePlaygroundStore();
        store.setCode("print('hello')");
        await store.runCode();

        const payload = mockedExecuteCode.mock.calls[0][0];
        expect(payload.source).toBe("playground");
    });

    it("does not store rejected responses in history", async () => {
        mockedExecuteCode.mockResolvedValue(REJECTED_RESPONSE);

        const store = usePlaygroundStore();
        store.loadAgentSuggestion("bad code");
        await store.runCode();

        expect(store.history).toHaveLength(0);
        expect(store.executionError).toBe("该代码未获准运行");
    });

    it("does not store unavailable responses in history", async () => {
        mockedExecuteCode.mockResolvedValue(UNAVAILABLE_RESPONSE);

        const store = usePlaygroundStore();
        await store.runCode();

        expect(store.history).toHaveLength(0);
        expect(store.executionError).toBe("执行服务暂时不可用");
    });

    it("stores successful responses in history", async () => {
        mockedExecuteCode.mockResolvedValue(SUCCESS_RESPONSE);

        const store = usePlaygroundStore();
        store.setCode("print('ok')");
        await store.runCode();

        expect(store.history).toHaveLength(1);
        expect(store.history[0].code).toBe("print('ok')");
    });
});
