import { afterEach, describe, expect, it, vi } from "vitest";
import { sendChatMessage } from "@/api/agent";
import { cancelAllRequests } from "@/api/index";

function response(events: unknown[]) {
    const encoder = new TextEncoder();
    return new Response(new ReadableStream({
        start(controller) {
            for (const event of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
            controller.close();
        },
    }));
}

afterEach(() => vi.unstubAllGlobals());

describe("agent SSE completion", () => {
    it("parses CRLF events split across UTF-8 and CRLF boundaries", async () => {
        const bytes = new TextEncoder().encode('data: {"type":"delta","text":"中文"}\r\n\r\ndata: {"type":"done","data":{"content":"中文"}}\r\n\r\n');
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({
            start(controller) {
                for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
                controller.close();
            },
        }))));
        const delta = vi.fn();
        const result = await sendChatMessage({payload:{message:"hi"}, onDelta:delta});
        expect(result.reply).toBe("中文");
        expect(delta).toHaveBeenCalledWith("中文");
    });

    it("cancels fetch streams when all API requests are cancelled", async () => {
        vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => {
            options.signal.addEventListener('abort', () => reject(options.signal.reason));
        })));
        const pending = sendChatMessage({payload:{message:"hi"}});
        const rejected = expect(pending).rejects.toThrow('已停止生成');
        cancelAllRequests();
        await rejected;
    });
    it("preserves deltas when partial error is followed by a fallback done", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([
            {type: "delta", text: "partial answer"},
            {type: "error", reason: "stream_interrupted", partial: true},
            {type: "done", data: {content: "fallback"}},
        ])));
        const result = await sendChatMessage({payload: {message: "hi"}});
        expect(result.reply).toBe("partial answer");
        expect(result.usedFallback).toBe(true);
    });

    it("reports premature EOF as partial failure rather than successful completion", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([{type: "delta", text: "half"}])));
        const onError = vi.fn();
        const onDone = vi.fn();
        await expect(sendChatMessage({payload: {message: "hi"}, onError, onDone})).rejects.toThrow();
        expect(onError).toHaveBeenCalledWith(expect.any(Error), true);
        expect(onDone).not.toHaveBeenCalled();
    });
});
