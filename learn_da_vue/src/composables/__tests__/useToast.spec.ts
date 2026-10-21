import { beforeEach, describe, expect, it, vi } from "vitest";
import { useToast } from "../useToast";

describe("useToast", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        useToast().clear();
    });

    it("show 入队并自动消失", async () => {
        const toast = useToast();

        toast.show("已保存");

        expect(toast.toasts.value).toHaveLength(1);
        expect(toast.toasts.value[0]?.kind).toBe("info");

        await vi.advanceTimersByTimeAsync(3000);
        expect(toast.toasts.value).toHaveLength(0);
    });

    it("durationMs = 0 时不自动消失", async () => {
        const toast = useToast();

        toast.show("等我手动关", { durationMs: 0 });
        await vi.advanceTimersByTimeAsync(10_000);

        expect(toast.toasts.value).toHaveLength(1);
    });

    it("dismiss 立即移除，且清理定时器", async () => {
        const toast = useToast();
        const id = toast.show("临时提示", { durationMs: 1000 });

        toast.dismiss(id);

        expect(toast.toasts.value).toHaveLength(0);
        await vi.advanceTimersByTimeAsync(2000);
        expect(toast.toasts.value).toHaveLength(0);
    });

    it("success / error 快捷方法写入对应 kind", () => {
        const toast = useToast();

        toast.success("已复制");
        toast.error("复制失败");

        expect(toast.toasts.value.map((item) => item.kind)).toEqual(["success", "error"]);
        expect(toast.toasts.value.map((item) => item.message)).toEqual(["已复制", "复制失败"]);
    });

    it("消息两侧空白会被裁掉（避免模板里换行产生空格）", () => {
        const toast = useToast();

        toast.show("  已复制  ");

        expect(toast.toasts.value[0]?.message).toBe("已复制");
    });

    it("多个 toast 各自独立计时", async () => {
        const toast = useToast();

        toast.show("短", { durationMs: 1000 });
        toast.show("长", { durationMs: 5000 });

        await vi.advanceTimersByTimeAsync(1200);
        expect(toast.toasts.value.map((item) => item.message)).toEqual(["长"]);

        await vi.advanceTimersByTimeAsync(4000);
        expect(toast.toasts.value).toHaveLength(0);
    });
});