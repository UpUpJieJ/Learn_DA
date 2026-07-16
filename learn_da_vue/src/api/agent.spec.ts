import { describe, it, expect } from "vitest";
import { buildChatHistory } from "./agent";
import type { ChatMessage } from "@/types/api";

describe("buildChatHistory", () => {
  it("excludes system messages", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "system", content: "You are a helper" },
      { id: "2", role: "user", content: "Hello" },
      { id: "3", role: "assistant", content: "Hi" },
    ];
    const history = buildChatHistory(messages);
    expect(history).toHaveLength(2);
    expect(history.every((m) => m.role !== "system")).toBe(true);
  });

  it("excludes the current user message (last user entry)", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "first" },
      { id: "2", role: "assistant", content: "reply" },
      { id: "3", role: "user", content: "latest question" },
    ];
    const history = buildChatHistory(messages, "3");
    // Should only contain the first user message and the assistant reply
    expect(history).toHaveLength(2);
    expect(history[0].content).toBe("first");
    expect(history[1].content).toBe("reply");
  });

  it("caps history at 20 messages", () => {
    const messages: ChatMessage[] = Array.from({ length: 30 }, (_, i) => ({
      id: String(i),
      role: (i % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
      content: `msg-${i}`,
    }));
    const history = buildChatHistory(messages);
    expect(history.length).toBeLessThanOrEqual(20);
  });

  it("returns role and content only (no id or extra fields)", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "hi" },
    ];
    const history = buildChatHistory(messages);
    expect(history[0]).toHaveProperty("role");
    expect(history[0]).toHaveProperty("content");
    expect(history[0]).not.toHaveProperty("id");
  });
});
