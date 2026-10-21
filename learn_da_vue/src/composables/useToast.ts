// =====================================================
// useToast：瞬时反馈（"已复制""已保存"等）的唯一入口
//
// 分层约定（见 docs/learning-workspace-redesign-2026-10-21.md §15.3）：
//   状态变化 → inline（按钮 loading、状态药丸）
//   瞬时事件 → toast
//   危险操作 → ConfirmDialog（不用 window.confirm）
//
// 状态放在模块级，任何组件调 useToast() 都操作同一个队列；
// ToastHost 负责渲染，别在页面里自己写 toast 容器。
// =====================================================

import { readonly, ref } from "vue";

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
    id: number;
    kind: ToastKind;
    message: string;
    durationMs: number;
}

const DEFAULT_DURATION_MS = 2600;

const items = ref<ToastItem[]>([]);
const timers = new Map<number, ReturnType<typeof setTimeout>>();
let seq = 0;

function dismiss(id: number): void {
    const timer = timers.get(id);
    if (timer !== undefined) {
        clearTimeout(timer);
        timers.delete(id);
    }
    items.value = items.value.filter((item) => item.id !== id);
}

export interface ShowToastOptions {
    kind?: ToastKind;
    /** 0 表示不自动消失 */
    durationMs?: number;
}

function show(message: string, options: ShowToastOptions = {}): number {
    const kind = options.kind ?? "info";
    const durationMs = options.durationMs ?? DEFAULT_DURATION_MS;
    const id = ++seq;
    items.value = [...items.value, { id, kind, message: message.trim(), durationMs }];
    if (durationMs > 0) {
        timers.set(
            id,
            setTimeout(() => dismiss(id), durationMs),
        );
    }
    return id;
}

function clear(): void {
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    items.value = [];
}

export function useToast() {
    return {
        toasts: readonly(items),
        show,
        success: (message: string, durationMs?: number) => show(message, { kind: "success", durationMs }),
        error: (message: string, durationMs?: number) => show(message, { kind: "error", durationMs }),
        info: (message: string, durationMs?: number) => show(message, { kind: "info", durationMs }),
        dismiss,
        clear,
    };
}