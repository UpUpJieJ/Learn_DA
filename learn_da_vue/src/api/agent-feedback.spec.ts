import { describe, it, expect } from "vitest";
import type {
  ChatMessage,
  TeachingFeedback,
  TeachingState,
  TeachingNextAction,
} from "@/types/api";

describe("TeachingFeedback type contract", () => {
  it("ChatMessage can carry teachingFeedback", () => {
    const msg: ChatMessage = {
      id: "1",
      role: "assistant",
      content: "你的代码有个语法错误",
      timestamp: Date.now(),
      teachingFeedback: {
        state: "execution_failed",
        attemptId: 42,
        evidenceSummary: "代码执行失败，需要先修复错误",
        diagnosis: "当前代码存在执行错误",
        hintLevel: 2,
        nextAction: "retry_exercise",
      },
    };
    expect(msg.teachingFeedback).toBeDefined();
    expect(msg.teachingFeedback?.state).toBe("execution_failed");
    expect(msg.teachingFeedback?.attemptId).toBe(42);
    expect(msg.teachingFeedback?.hintLevel).toBe(2);
    expect(msg.teachingFeedback?.nextAction).toBe("retry_exercise");
  });

  it("all 5 teaching states are valid", () => {
    const states: TeachingState[] = [
      "execution_failed",
      "verification_failed",
      "passed_unconfirmed",
      "unverifiable",
      "no_evidence",
    ];
    expect(states).toHaveLength(5);
  });

  it("all 4 next actions are valid", () => {
    const actions: TeachingNextAction[] = [
      "inspect_result",
      "retry_exercise",
      "confirm_lesson",
      "retry_later",
    ];
    expect(actions).toHaveLength(4);
  });

  it("teachingFeedback can be null (no evidence)", () => {
    const msg: ChatMessage = {
      id: "2",
      role: "assistant",
      content: "你好！有什么可以帮你的？",
      timestamp: Date.now(),
      teachingFeedback: null,
    };
    expect(msg.teachingFeedback).toBeNull();
  });

  it("teachingFeedback can be omitted", () => {
    const msg: ChatMessage = {
      id: "3",
      role: "assistant",
      content: "hi",
      timestamp: Date.now(),
    };
    expect(msg.teachingFeedback).toBeUndefined();
  });

  it("evidence does not leak code field", () => {
    const fb: TeachingFeedback = {
      state: "verification_failed",
      attemptId: 7,
      evidenceSummary: "代码执行成功，但练习断言未通过",
      diagnosis: "代码能运行，但输出与练习目标不一致",
      hintLevel: 1,
      nextAction: "retry_exercise",
    };
    const keys = Object.keys(fb);
    expect(keys).not.toContain("code");
    expect(keys).not.toContain("prompt");
    expect(keys).not.toContain("fullCode");
  });

  it("passed_unconfirmed maps to confirm_lesson when not completed", () => {
    const fb: TeachingFeedback = {
      state: "passed_unconfirmed",
      attemptId: 10,
      evidenceSummary: "练习已通过，可以确认课程完成",
      diagnosis: "练习目标已达成",
      hintLevel: 1,
      nextAction: "confirm_lesson",
    };
    expect(fb.nextAction).toBe("confirm_lesson");
  });

  it("unverifiable maps to retry_later", () => {
    const fb: TeachingFeedback = {
      state: "unverifiable",
      attemptId: null,
      evidenceSummary: "结果不可验证",
      diagnosis: "无法确认练习是否通过",
      hintLevel: 1,
      nextAction: "retry_later",
    };
    expect(fb.nextAction).toBe("retry_later");
  });
});
