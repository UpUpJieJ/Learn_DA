import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock, axiosMock } = vi.hoisted(() => {
  const requestMock = vi.fn();
  const axiosMock = Object.assign(vi.fn(), {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
      request: requestMock,
    })),
    isCancel: vi.fn(() => false),
  });
  return { requestMock, axiosMock };
});

vi.mock("axios", () => ({ default: axiosMock }));

import { request } from "./index";

describe("request", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue({ data: { code: 200, msg: "ok", data: "done" } });
  });

  it("passes a caller-provided AbortSignal through to Axios", async () => {
    const controller = new AbortController();

    await request<string>({ method: "POST", url: "/agent/chat", signal: controller.signal });

    expect(requestMock).toHaveBeenCalledWith(
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("creates an AbortSignal when the caller did not provide one", async () => {
    await request<string>({ method: "GET", url: "/lessons" });

    expect(requestMock).toHaveBeenCalledWith(
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });
});
