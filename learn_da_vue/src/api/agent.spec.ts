import { describe, it, expect } from "vitest";
import { buildChatHistory } from "./agent";
import type { ChatMessage } from "@/types/api";

function msg(id: string, role: ChatMessage["role"], content: string): ChatMessage {
  return { id, role, content, timestamp: Date.now() };
}

describe("buildChatHistory", () => {
  it("excludes system messages", () => {
    const messages: ChatMessage[] = [
      msg("1", "system", "You are a helper"),
      msg("2", "user", "Hello"),
      msg("3", "assistant", "Hi"),
    ];
    const history = buildChatHistory(messages);
    expect(history).toHaveLength(2);
    expect(history.every((m) => m.role !== "system")).toBe(true);
  });

  it("excludes the current user message (last user entry)", () => {
    const messages: ChatMessage[] = [
      msg("1", "user", "first"),
      msg("2", "assistant", "reply"),
      msg("3", "user", "latest question"),
    ];
    const history = buildChatHistory(messages, "3");
    // Should only contain the first user message and the assistant reply
    expect(history).toHaveLength(2);
    expect(history[0]?.content).toBe("first");
    expect(history[1]?.content).toBe("reply");
  });

  it("caps history at 20 messages", () => {
    const messages: ChatMessage[] = Array.from({ length: 30 }, (_, i) =>
      msg(String(i), i % 2 === 0 ? "user" : "assistant", `msg-${i}`),
    );
    const history = buildChatHistory(messages);
    expect(history.length).toBeLessThanOrEqual(20);
  });

  it("returns role and content only (no id or extra fields)", () => {
    const messages: ChatMessage[] = [msg("1", "user", "hi")];
    const history = buildChatHistory(messages);
    expect(history[0]).toHaveProperty("role");
    expect(history[0]).toHaveProperty("content");
    expect(history[0]).not.toHaveProperty("id");
  });
});
