// =====================================================
// useAsyncState：网络页面的三态（loading / empty / error）唯一承载
//
// 动机：改造前全站 56 处 isLoading 各写一套，加载骨架、空态、
// 错误重试的覆盖参差不齐（Playground / LessonDetail 一个 skeleton 都没有）。
// 页面统一改成：
//   const lesson = useAsyncState(() => fetchLessonBySlug(slug), { isEmpty: (v) => !v.lesson });
//   onMounted(lesson.run);
// 模板里按 lesson.status 渲染骨架 / 空态 / 错误重试，不要自己写 loading 布尔。
//
// 语义细节：
//   - 竞态：后发请求胜出，先发的过期响应被丢弃（不覆盖新数据）
//   - 失败不清空已有数据（重试期间旧内容仍可见，避免闪白）
//   - empty 由调用方用 isEmpty 判定；默认只有 null/undefined 算空
// =====================================================

import { computed, ref, type Ref } from "vue";

export type AsyncStatus = "idle" | "loading" | "ready" | "empty" | "error";

export interface UseAsyncStateOptions<T> {
    /** 判定"有数据但为空"（如课程列表长度为 0），命中则 status = "empty" */
    isEmpty?: (value: T) => boolean;
    /** 错误回调，用于埋点或额外提示；不影响 status 流转 */
    onError?: (error: unknown) => void;
}

export interface UseAsyncStateReturn<T> {
    status: Ref<AsyncStatus>;
    data: Ref<T | null>;
    error: Ref<string | null>;
    isLoading: Ref<boolean>;
    isReady: Ref<boolean>;
    isEmpty: Ref<boolean>;
    isError: Ref<boolean>;
    run: () => Promise<T | null>;
    retry: () => Promise<T | null>;
    reset: () => void;
}

function toMessage(error: unknown): string {
    if (error instanceof Error && error.message.trim()) return error.message.trim();
    if (typeof error === "string" && error.trim()) return error.trim();
    return "加载失败，请重试";
}

export function useAsyncState<T>(
    loader: () => Promise<T>,
    options: UseAsyncStateOptions<T> = {},
): UseAsyncStateReturn<T> {
    const status = ref<AsyncStatus>("idle") as Ref<AsyncStatus>;
    const data = ref<T | null>(null) as Ref<T | null>;
    const error = ref<string | null>(null);
    let requestId = 0;

    async function run(): Promise<T | null> {
        const current = ++requestId;
        status.value = "loading";
        error.value = null;
        try {
            const value = await loader();
            if (current !== requestId) return null; // 过期响应：已有更新的请求在跑
            data.value = value;
            const empty = options.isEmpty ? options.isEmpty(value) : value == null;
            status.value = empty ? "empty" : "ready";
            return value;
        } catch (err) {
            if (current !== requestId) return null;
            error.value = toMessage(err);
            status.value = "error";
            options.onError?.(err);
            return null;
        }
    }

    function reset(): void {
        requestId++; // 让在途请求失效
        status.value = "idle";
        data.value = null;
        error.value = null;
    }

    return {
        status,
        data,
        error,
        isLoading: computed(() => status.value === "loading"),
        isReady: computed(() => status.value === "ready"),
        isEmpty: computed(() => status.value === "empty"),
        isError: computed(() => status.value === "error"),
        run,
        retry: run,
        reset,
    };
}