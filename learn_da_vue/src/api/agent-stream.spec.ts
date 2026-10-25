import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { sendChatMessage } from "@/api/agent";
import type { AgentChatRequest } from "@/types/api";

// =====================================================
// SSE 解析测试：sendChatMessage 用 fetch + ReadableStream 逐块读，
// 所以这里要伪造一个分块到达的响应体（而不是一次性给完整字符串）。
// =====================================================

const PAYLOAD: AgentChatRequest = { message: "怎么分组", history: [] };

/** 按给定分块构造一个流式 Response */
function streamResponse(chunks: string[], init?: ResponseInit): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    ...init,
  });
}

function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

describe("sendChatMessage (SSE)", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("delivers deltas in order and resolves with the final content", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        sse({ type: "delta", text: "先 " }),
        sse({ type: "delta", text: "group_by" }),
        sse({
          type: "done",
          data: {
            content: "先 group_by",
            model: "qwen3.8-27b",
            usedFallback: false,
            interactionId: 7,
          },
        }),
      ]),
    );

    const deltas: string[] = [];
    const result = await sendChatMessage({
      payload: PAYLOAD,
      onDelta: (text) => deltas.push(text),
    });

    expect(deltas).toEqual(["先 ", "group_by"]);
    expect(result.reply).toBe("先 group_by");
    expect(result.model).toBe("qwen3.8-27b");
    expect(result.interactionId).toBe(7);
    expect(result.usedFallback).toBe(false);
  });

  it("reassembles events split across chunk boundaries", async () => {
    // 服务端的分块边界与事件边界无关：这里故意把一条事件切成三段
    const whole = sse({ type: "delta", text: "跨块文本" });
    fetchMock.mockResolvedValue(
      streamResponse([
        whole.slice(0, 10),
        whole.slice(10, 20),
        whole.slice(20) + sse({ type: "done", data: { content: "跨块文本" } }),
      ]),
    );

    const deltas: string[] = [];
    const result = await sendChatMessage({
      payload: PAYLOAD,
      onDelta: (text) => deltas.push(text),
    });

    expect(deltas).toEqual(["跨块文本"]);
    expect(result.reply).toBe("跨块文本");
  });

  it("reports tool calls so the UI can explain the wait", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        sse({ type: "tool", names: ["search_knowledge"] }),
        sse({ type: "delta", text: "查到了" }),
        sse({ type: "done", data: { content: "查到了" } }),
      ]),
    );

    const tools: string[][] = [];
    await sendChatMessage({
      payload: PAYLOAD,
      onTool: (names) => tools.push(names),
    });

    expect(tools).toEqual([["search_knowledge"]]);
  });

  it("marks a broken stream as partial and keeps the text already shown", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        sse({ type: "delta", text: "我先看" }),
        sse({ type: "error", reason: "stream_interrupted", partial: true }),
        sse({ type: "done", data: { content: "我先看", usedFallback: true } }),
      ]),
    );

    const errors: Array<{ message: string; partial?: boolean }> = [];
    const result = await sendChatMessage({
      payload: PAYLOAD,
      onError: (error, partial) =>
        errors.push({ message: error.message, partial }),
    });

    expect(errors).toHaveLength(1);
    expect(errors[0]?.partial).toBe(true);
    expect(errors[0]?.message).toContain("不完整");
    // 已经吐出的字不能丢
    expect(result.reply).toBe("我先看");
    expect(result.usedFallback).toBe(true);
  });

  it("surfaces a business error envelope as an ApiError", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ code: 422, msg: "message is required" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(sendChatMessage({ payload: PAYLOAD })).rejects.toThrow(
      "message is required",
    );
  });

  it("sends the request id header so the server can dedupe replays", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([sse({ type: "done", data: { content: "ok" } })]),
    );

    await sendChatMessage({ payload: PAYLOAD, requestId: "req-fixed-1" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/agent/chat/stream");
    expect((init.headers as Record<string, string>)["X-Request-ID"]).toBe(
      "req-fixed-1",
    );
    expect(init.credentials).toBe("include");
  });

  it("ignores malformed event lines instead of dropping the whole answer", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        "data: {不是 JSON}\n\n",
        sse({ type: "delta", text: "正常内容" }),
        sse({ type: "done", data: { content: "正常内容" } }),
      ]),
    );

    const result = await sendChatMessage({ payload: PAYLOAD });

    expect(result.reply).toBe("正常内容");
  });
});
