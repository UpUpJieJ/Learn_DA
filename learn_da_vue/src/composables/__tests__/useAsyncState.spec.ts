import { describe, expect, it } from "vitest";
import { useAsyncState } from "../useAsyncState";

interface Deferred<T> {
    promise: Promise<T>;
    resolve: (value: T) => void;
    reject: (error: unknown) => void;
}

function deferred<T>(): Deferred<T> {
    let resolve!: (value: T) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

describe("useAsyncState", () => {
    it("初始为 idle，成功后进入 ready 并保留数据", async () => {
        const state = useAsyncState(async () => ({ value: 42 }));
        expect(state.status.value).toBe("idle");

        const result = await state.run();

        expect(result).toEqual({ value: 42 });
        expect(state.status.value).toBe("ready");
        expect(state.data.value).toEqual({ value: 42 });
        expect(state.error.value).toBeNull();
        expect(state.isReady.value).toBe(true);
    });

    it("isEmpty 命中时进入 empty 而不是 ready", async () => {
        const state = useAsyncState(async () => [] as string[], {
            isEmpty: (value) => value.length === 0,
        });

        await state.run();

        expect(state.status.value).toBe("empty");
        expect(state.isEmpty.value).toBe(true);
    });

    it("失败时进入 error 并给出可读信息，重试成功后恢复 ready", async () => {
        let attempt = 0;
        const state = useAsyncState(async () => {
            attempt += 1;
            if (attempt === 1) throw new Error("课程加载失败");
            return "ok";
        });

        await state.run();
        expect(state.status.value).toBe("error");
        expect(state.error.value).toBe("课程加载失败");

        await state.retry();
        expect(state.status.value).toBe("ready");
        expect(state.data.value).toBe("ok");
        expect(state.error.value).toBeNull();
    });

    it("非 Error 抛出物也给出兜底文案，不会渲染空错误", async () => {
        const state = useAsyncState(async () => {
            throw { code: 500 };
        });

        await state.run();

        expect(state.status.value).toBe("error");
        expect(state.error.value).toBe("加载失败，请重试");
    });

    it("竞态：后发请求胜出，先发的过期响应被丢弃", async () => {
        const first = deferred<string>();
        const second = deferred<string>();
        const queue = [first.promise, second.promise];
        const state = useAsyncState(async () => queue.shift() as Promise<string>);

        const firstRun = state.run();
        const secondRun = state.run();

        second.resolve("新数据");
        await secondRun;
        first.resolve("旧数据");
        await firstRun;

        expect(state.data.value).toBe("新数据");
        expect(state.status.value).toBe("ready");
    });

    it("请求期间保留上一份数据，避免刷新时闪白", async () => {
        const next = deferred<string>();
        let call = 0;
        const state = useAsyncState(async () => (++call === 1 ? "第一份" : next.promise));

        await state.run();
        const pending = state.run();

        expect(state.status.value).toBe("loading");
        expect(state.data.value).toBe("第一份");

        next.resolve("第二份");
        await pending;
        expect(state.data.value).toBe("第二份");
    });

    it("reset 清空数据并让在途请求失效", async () => {
        const pending = deferred<string>();
        const state = useAsyncState(async () => pending.promise);

        const run = state.run();
        state.reset();
        pending.resolve("迟到的数据");
        await run;

        expect(state.status.value).toBe("idle");
        expect(state.data.value).toBeNull();
    });
});