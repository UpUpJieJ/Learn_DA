<script setup lang="ts">
import { ref, computed, nextTick, watch, onUnmounted } from "vue";
import { useLocalStateStore } from "@/stores/localState";
import { usePlaygroundStore } from "@/stores/playground";
import { streamChatMessage, buildChatHistory, explainCode, fixCode } from "@/api/agent";
import type { ChatMessage, AgentContext } from "@/types/api";

type QuickActionKey = "explain" | "fix" | "exercise" | "next";

interface QuickAction {
    key: QuickActionKey;
    label: string;
    disabled: boolean;
    prompt: string;
}

interface Props {
    embedded?: boolean
    context?: AgentContext
}

const props = withDefaults(defineProps<Props>(), {
    embedded: false,
    context: undefined,
})

const localStateStore = useLocalStateStore();
const playgroundStore = usePlaygroundStore();

// 状态
const messages = ref<ChatMessage[]>([]);
const inputText = ref("");
const isLoading = ref(false);
const copiedBlockId = ref<string | null>(null);

const messagesContainerRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);
const streamingMessageId = ref<string | null>(null);
let abortController: AbortController | null = null;

// Computed
const isOpen = computed(() => localStateStore.isAgentOpen);

const agentContext = computed<AgentContext>(() => ({
    currentCode: playgroundStore.code || undefined,
    lastError: playgroundStore.stderr || undefined,
    stdout: playgroundStore.stdout || undefined,
    stderr: playgroundStore.stderr || undefined,
    ...props.context,
}));

const messageCount = computed(() => messages.value.length);
const hasCurrentCode = computed(() => !!agentContext.value.currentCode?.trim());
const hasCurrentError = computed(
    () => !!(agentContext.value.stderr || agentContext.value.lastError)?.trim(),
);

const quickActions = computed<QuickAction[]>(() => [
    {
        key: "explain",
        label: "解释代码",
        disabled: !hasCurrentCode.value,
        prompt: "请结合当前课程，解释我现在 Playground 里的代码。",
    },
    {
        key: "fix",
        label: "修复错误",
        disabled: !hasCurrentCode.value || !hasCurrentError.value,
        prompt: "请结合当前课程和最近一次执行错误，帮我修复当前代码。",
    },
    {
        key: "exercise",
        label: "生成练习",
        disabled: false,
        prompt: "请根据当前课程生成一个小练习，并给出提示但先不要直接给最终答案。",
    },
    {
        key: "next",
        label: "下一步",
        disabled: false,
        prompt: "请根据当前课程、代码和运行结果，告诉我下一步应该学习或尝试什么。",
    },
]);

// 面板尺寸（支持自由拖拽调整）
const panelWidth = ref(400);
const panelHeight = ref(500);
const isResizingWidth = ref(false);
const isResizingHeight = ref(false);

function startResizeWidth(e: MouseEvent) {
    e.preventDefault();
    isResizingWidth.value = true;
    const startX = e.clientX;
    const startWidth = panelWidth.value;

    const onMove = (ev: MouseEvent) => {
        const delta = startX - ev.clientX;
        panelWidth.value = Math.min(800, Math.max(280, startWidth + delta));
    };
    const onUp = () => {
        isResizingWidth.value = false;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
}

function startResizeHeight(e: MouseEvent) {
    e.preventDefault();
    isResizingHeight.value = true;
    const startY = e.clientY;
    const startHeight = panelHeight.value;

    const onMove = (ev: MouseEvent) => {
        const delta = ev.clientY - startY;
        panelHeight.value = Math.min(700, Math.max(300, startHeight + delta));
    };
    const onUp = () => {
        isResizingHeight.value = false;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
}

async function scrollToBottom() {
    await nextTick();
    const el = messagesContainerRef.value;
    if (el) {
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
}

async function sendMessage(text?: string) {
    const content = (text ?? inputText.value).trim();
    if (!content || isLoading.value) return;

    inputText.value = "";

    const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
        timestamp: Date.now(),
    };
    messages.value.push(userMsg);

    const assistantId = `assistant-${Date.now()}`;
    const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
    };
    messages.value.push(assistantMsg);
    streamingMessageId.value = assistantId;

    isLoading.value = true;
    await scrollToBottom();

    const history = buildChatHistory(messages.value.filter(m => !m.isStreaming));
    abortController = new AbortController();

    try {
        await streamChatMessage({
            payload: {
                message: content,
                history,
                context: agentContext.value,
            },
            onToken: (token) => {
                const msg = messages.value.find((m) => m.id === assistantId);
                if (msg) {
                    msg.content += token;
                    scrollToBottom();
                }
            },
            onDone: (fullReply) => {
                const msg = messages.value.find((m) => m.id === assistantId);
                if (msg) {
                    msg.content = fullReply || msg.content;
                    msg.isStreaming = false;
                }
                streamingMessageId.value = null;
                isLoading.value = false;
                scrollToBottom();
            },
            onError: (error) => {
                const msg = messages.value.find((m) => m.id === assistantId);
                if (msg) {
                    msg.content = `请求失败：${error.message}`;
                    msg.isStreaming = false;
                }
                streamingMessageId.value = null;
                isLoading.value = false;
                scrollToBottom();
            },
            signal: abortController.signal,
        });
    } catch {
        const msg = messages.value.find((m) => m.id === assistantId);
        if (msg) {
            msg.content = "发生未知错误，请稍后重试。";
            msg.isStreaming = false;
        }
        streamingMessageId.value = null;
        isLoading.value = false;
    }
}

async function sendQuickAction(action: QuickAction) {
    if (action.disabled || isLoading.value) return;
    if (action.key === "exercise" || action.key === "next") {
        await sendMessage(action.prompt);
        return;
    }

    const code = agentContext.value.currentCode?.trim();
    if (!code) return;

    const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: action.prompt,
        timestamp: Date.now(),
    };
    const assistantId = `assistant-${Date.now()}`;
    const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        isStreaming: true,
    };

    messages.value.push(userMsg, assistantMsg);
    isLoading.value = true;
    await scrollToBottom();

    try {
        if (action.key === "explain") {
            const response = await explainCode({
                code,
                context: agentContext.value,
            });
            assistantMsg.content = response.explanation;
        } else {
            const errorMessage =
                agentContext.value.stderr ||
                agentContext.value.lastError ||
                "当前没有捕获到具体错误，请检查代码逻辑。";
            const response = await fixCode({
                code,
                errorMessage,
                context: agentContext.value,
            });
            const verification = response.verification
                ? `\n\n验证结果：${response.verification.verified ? "通过" : "未通过"}（${response.verification.status}，${response.verification.executionTime}ms）${
                      response.verification.stderr
                          ? `\n\n验证错误：\n\`\`\`text\n${response.verification.stderr}\n\`\`\``
                          : ""
                  }`
                : "";
            assistantMsg.content = `${response.explanation}\n\n修复代码：\n\`\`\`python\n${response.fixedCode}\n\`\`\`${verification}`;
        }
    } catch (error) {
        const message = error instanceof Error ? error.message : "请求失败";
        assistantMsg.content = `请求失败：${message}`;
    } finally {
        assistantMsg.isStreaming = false;
        isLoading.value = false;
        await scrollToBottom();
    }
}

function stopStreaming() {
    abortController?.abort();
    abortController = null;

    const msg = messages.value.find((m) => m.id === streamingMessageId.value);
    if (msg) {
        msg.content = msg.content || "已中断";
        msg.isStreaming = false;
    }
    streamingMessageId.value = null;
    isLoading.value = false;
}

function clearMessages() {
    messages.value = [];
}

function extractFirstCodeBlock(content: string): string | null {
    const match = content.match(/```(?:\w+)?\n([\s\S]*?)```/);
    return match && match[1] ? match[1].trim() : null;
}

async function copyCode(code: string, blockId: string) {
    try {
        await navigator.clipboard.writeText(code);
        copiedBlockId.value = blockId;
        setTimeout(() => {
            if (copiedBlockId.value === blockId) copiedBlockId.value = null;
        }, 2000);
    } catch {
        // silent
    }
}

function injectToPlayground(code: string) {
    playgroundStore.setCode(code);
}

function renderMessageContent(content: string): string {
    if (!content) return "";

    let html = content
        .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
            const escaped = code
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
            const id = `block-${Math.random().toString(36).slice(2, 7)}`;
            return `<div class="code-block" data-id="${id}" data-lang="${lang || "text"}" data-code="${encodeURIComponent(code.trim())}"><div class="code-header"><span class="code-lang">${lang || "text"}</span><div class="code-actions"><button class="code-btn copy-btn" data-id="${id}">复制</button><button class="code-btn run-btn" data-id="${id}">运行</button></div></div><pre><code>${escaped}</code></pre></div>`;
        })
        .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/^### (.+)$/gm, '<h4 class="h4">$1</h4>')
        .replace(/^## (.+)$/gm, '<h3 class="h3">$1</h3>')
        .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
        .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, '<ul class="ul">$&</ul>')
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
        .replace(/^> (.+)$/gm, '<blockquote class="quote">$1</blockquote>')
        .replace(/\n\n/g, "</p><p>")
        .replace(/\n/g, "<br />");

    return `<p>${html}</p>`;
}

function handleMessageClick(e: MouseEvent) {
    const target = e.target as HTMLElement;

    if (target.classList.contains("copy-btn")) {
        const blockId = target.dataset.id!;
        const block = document.querySelector(`.code-block[data-id="${blockId}"]`);
        if (block) {
            const code = decodeURIComponent((block as HTMLElement).dataset.code ?? "");
            copyCode(code, blockId);
            target.textContent = "已复制";
            setTimeout(() => { target.textContent = "复制"; }, 2000);
        }
    }

    if (target.classList.contains("run-btn")) {
        const blockId = target.dataset.id!;
        const block = document.querySelector(`.code-block[data-id="${blockId}"]`);
        if (block) {
            const code = decodeURIComponent((block as HTMLElement).dataset.code ?? "");
            injectToPlayground(code);
            target.textContent = "已运行";
            setTimeout(() => { target.textContent = "运行"; }, 2000);
        }
    }
}

function handleInputKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(e: Event) {
    const el = e.target as HTMLTextAreaElement;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

watch(isOpen, async (opened) => {
    if (opened) {
        await nextTick();
        setTimeout(() => inputRef.value?.focus(), 100);
    }
});

onUnmounted(() => {
    abortController?.abort();
});
</script>

<template>
    <!-- 浮动触发按钮（非内嵌模式） -->
    <Transition v-if="!embedded" name="fab">
        <button
            v-if="!isOpen"
            class="fixed top-20 right-5 z-40 w-10 h-10 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white shadow-lg border border-white/10 flex items-center justify-center transition-all duration-200 hover:shadow-xl"
            title="助手"
            @click="localStateStore.openAgent()"
        >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
        </button>
    </Transition>

    <!-- 主面板 -->
    <Transition v-if="!embedded" name="panel">
        <div
            v-if="isOpen"
            class="fixed top-16 right-5 z-50 flex flex-col bg-[#1a1a1a] rounded-2xl overflow-hidden shadow-2xl border border-white/10"
            :style="{ width: panelWidth + 'px', height: panelHeight + 'px' }"
        >
            <!-- 右侧拖拽手柄 -->
            <div
                class="absolute right-0 top-0 bottom-0 w-1 cursor-ew-resize hover:bg-blue-500/50 transition-colors"
                :class="isResizingWidth ? 'bg-blue-500/50' : ''"
                @mousedown="startResizeWidth"
            />
            <!-- 底部拖拽手柄 -->
            <div
                class="absolute bottom-0 left-0 right-0 h-1 cursor-ns-resize hover:bg-blue-500/50 transition-colors"
                :class="isResizingHeight ? 'bg-blue-500/50' : ''"
                @mousedown="startResizeHeight"
            />

            <!-- 头部 -->
            <header class="flex items-center justify-between px-4 py-3 border-b border-white/8 shrink-0">
                <div class="flex items-center gap-2">
                    <div class="w-7 h-7 rounded-lg bg-blue-500/10 flex items-center justify-center">
                        <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                    </div>
                    <span class="text-sm font-medium text-slate-200">助手</span>
                </div>

                <div class="flex items-center gap-1">
                    <button
                        v-if="messageCount > 0"
                        class="w-7 h-7 rounded flex items-center justify-center text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                        title="清空"
                        @click="clearMessages"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                    <button
                        class="w-7 h-7 rounded flex items-center justify-center text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                        title="关闭"
                        @click="localStateStore.closeAgent()"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
            </header>

            <!-- 消息列表 -->
            <div
                ref="messagesContainerRef"
                class="flex-1 overflow-y-auto bg-[#141414]"
                @click="handleMessageClick"
            >
                <!-- 空状态 -->
                <div
                    v-if="messageCount === 0"
                    class="flex flex-col items-center justify-center h-full px-6 text-center"
                >
                    <div class="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mb-4">
                        <svg class="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                    </div>
                    <p class="text-sm text-slate-500">输入问题获得帮助</p>
                </div>

                <!-- 消息 -->
                <div class="space-y-3 px-4 py-4">
                    <div
                        v-for="msg in messages"
                        :key="msg.id"
                        class="flex flex-col"
                        :class="msg.role === 'user' ? 'items-end' : 'items-start'"
                    >
                        <!-- 用户消息 -->
                        <div
                            v-if="msg.role === 'user'"
                            class="max-w-[85%] rounded-2xl px-4 py-2.5 bg-blue-600 text-white text-sm"
                        >
                            {{ msg.content }}
                        </div>

                        <!-- 助手消息 -->
                        <div
                            v-else
                            class="max-w-[90%]"
                        >
                            <div class="rounded-2xl px-4 py-2.5 bg-white/5 border border-white/8 text-slate-300 text-sm leading-relaxed">
                                <div v-html="renderMessageContent(msg.content)" />
                                <span
                                    v-if="msg.isStreaming"
                                    class="inline-block w-0.5 h-3.5 bg-blue-400 ml-0.5 animate-pulse align-text-bottom"
                                />
                            </div>

                            <!-- 操作 -->
                            <div class="flex items-center gap-2 mt-1 px-1">
                                <button
                                    v-if="!msg.isStreaming"
                                    class="text-xs text-slate-600 hover:text-slate-400 transition-colors"
                                    @click="copyCode(msg.content, msg.id)"
                                >
                                    {{ copiedBlockId === msg.id ? '已复制' : '复制' }}
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- 加载指示 -->
                    <div
                        v-if="isLoading && messages.at(-1)?.isStreaming"
                        class="flex items-center gap-1.5"
                    >
                        <div class="flex items-center gap-1 px-3 py-2 rounded-xl bg-white/5">
                            <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0s" />
                            <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0.15s" />
                            <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0.3s" />
                        </div>
                    </div>
                </div>
            </div>

            <!-- 输入区域 -->
            <div class="shrink-0 bg-[#1a1a1a] border-t border-white/8 px-4 py-3">
                <div class="mb-3 grid grid-cols-2 gap-2">
                    <button
                        v-for="action in quickActions"
                        :key="action.key"
                        class="rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors"
                        :class="
                            action.disabled || isLoading
                                ? 'border-white/5 bg-white/[0.02] text-slate-600 cursor-not-allowed'
                                : 'border-white/10 bg-white/5 text-slate-300 hover:border-blue-400/40 hover:bg-blue-500/10 hover:text-blue-200'
                        "
                        :disabled="action.disabled || isLoading"
                        @click="sendQuickAction(action)"
                    >
                        {{ action.label }}
                    </button>
                </div>

                <!-- 停止按钮 -->
                <div v-if="isLoading" class="flex justify-center mb-2">
                    <button
                        class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-slate-400 text-xs hover:bg-white/10 transition-colors"
                        @click="stopStreaming"
                    >
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                            <rect x="6" y="6" width="12" height="12" rx="1" />
                        </svg>
                        停止
                    </button>
                </div>

                <!-- 输入框 -->
                <div class="flex items-end gap-2 bg-[#242424] border border-white/10 rounded-xl px-3 py-2 focus-within:border-blue-500/40 transition-colors">
                    <textarea
                        ref="inputRef"
                        v-model="inputText"
                        class="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-600 resize-none outline-none leading-relaxed max-h-[100px]"
                        placeholder="输入问题..."
                        rows="1"
                        :disabled="isLoading"
                        @keydown="handleInputKeydown"
                        @input="autoResize"
                    />
                    <button
                        class="w-8 h-8 rounded-lg flex items-center justify-center transition-all shrink-0"
                        :class="inputText.trim() && !isLoading ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-white/5 text-slate-600 cursor-not-allowed'"
                        :disabled="!inputText.trim() || isLoading"
                        @click="sendMessage()"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    </Transition>

    <!-- 内嵌模式 -->
    <div v-if="embedded" class="flex flex-col h-full min-h-0 bg-[#0d1117]">
        <!-- 消息列表 -->
        <div
            ref="messagesContainerRef"
            class="flex-1 min-h-0 overflow-y-auto"
            @click="handleMessageClick"
        >
            <!-- 空状态 -->
            <div
                v-if="messageCount === 0"
                class="flex flex-col items-center justify-center h-full px-6 text-center"
            >
                <div class="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mb-4">
                    <svg class="w-6 h-6 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                </div>
                <p class="text-sm text-slate-500">输入问题获得帮助</p>
            </div>

            <!-- 消息 -->
            <div class="space-y-3 px-4 py-4">
                <div
                    v-for="msg in messages"
                    :key="msg.id"
                    class="flex flex-col"
                    :class="msg.role === 'user' ? 'items-end' : 'items-start'"
                >
                    <!-- 用户消息 -->
                    <div
                        v-if="msg.role === 'user'"
                        class="max-w-[85%] rounded-2xl px-4 py-2.5 bg-blue-600 text-white text-sm"
                    >
                        {{ msg.content }}
                    </div>

                    <!-- 助手消息 -->
                    <div
                        v-else
                        class="max-w-[90%]"
                    >
                        <div class="rounded-2xl px-4 py-2.5 bg-white/5 border border-white/8 text-slate-300 text-sm leading-relaxed">
                            <div v-html="renderMessageContent(msg.content)" />
                            <span
                                v-if="msg.isStreaming"
                                class="inline-block w-0.5 h-3.5 bg-blue-400 ml-0.5 animate-pulse align-text-bottom"
                            />
                        </div>

                        <!-- 操作 -->
                        <div class="flex items-center gap-2 mt-1 px-1">
                            <button
                                v-if="!msg.isStreaming"
                                class="text-xs text-slate-600 hover:text-slate-400 transition-colors"
                                @click="copyCode(msg.content, msg.id)"
                            >
                                {{ copiedBlockId === msg.id ? '已复制' : '复制' }}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- 加载指示 -->
                <div
                    v-if="isLoading && messages.at(-1)?.isStreaming"
                    class="flex items-center gap-1.5"
                >
                    <div class="flex items-center gap-1 px-3 py-2 rounded-xl bg-white/5">
                        <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0s" />
                        <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0.15s" />
                        <span class="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style="animation-delay: 0.3s" />
                    </div>
                </div>
            </div>
        </div>

        <!-- 输入区域 -->
        <div class="shrink-0 bg-[#0d1117] border-t border-white/8 px-4 py-3">
            <div class="mb-3 grid grid-cols-2 gap-2">
                <button
                    v-for="action in quickActions"
                    :key="action.key"
                    class="rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors"
                    :class="
                        action.disabled || isLoading
                            ? 'border-white/5 bg-white/[0.02] text-slate-600 cursor-not-allowed'
                            : 'border-white/10 bg-white/5 text-slate-300 hover:border-blue-400/40 hover:bg-blue-500/10 hover:text-blue-200'
                    "
                    :disabled="action.disabled || isLoading"
                    @click="sendQuickAction(action)"
                >
                    {{ action.label }}
                </button>
            </div>

            <!-- 停止按钮 -->
            <div v-if="isLoading" class="flex justify-center mb-2">
                <button
                    class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-slate-400 text-xs hover:bg-white/10 transition-colors"
                    @click="stopStreaming"
                >
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" rx="1" />
                    </svg>
                    停止
                </button>
            </div>

            <!-- 输入框 -->
            <div class="flex items-end gap-2 bg-[#242424] border border-white/10 rounded-xl px-3 py-2 focus-within:border-blue-500/40 transition-colors">
                <textarea
                    ref="inputRef"
                    v-model="inputText"
                    class="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-600 resize-none outline-none leading-relaxed max-h-[100px]"
                    placeholder="输入问题..."
                    rows="1"
                    :disabled="isLoading"
                    @keydown="handleInputKeydown"
                    @input="autoResize"
                />
                <button
                    class="w-8 h-8 rounded-lg flex items-center justify-center transition-all shrink-0"
                    :class="inputText.trim() && !isLoading ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-white/5 text-slate-600 cursor-not-allowed'"
                    :disabled="!inputText.trim() || isLoading"
                    @click="sendMessage()"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                </button>
            </div>
        </div>
    </div>
</template>

<style scoped>
/* 动画 */
.panel-enter-active { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.panel-leave-active { transition: all 0.15s ease-in; }
.panel-enter-from { opacity: 0; transform: translateY(12px) scale(0.96); }
.panel-leave-to { opacity: 0; transform: translateY(8px) scale(0.97); }

.fab-enter-active { transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
.fab-leave-active { transition: all 0.15s ease-in; }
.fab-enter-from, .fab-leave-to { opacity: 0; transform: scale(0.8); }

/* 滚动条 */
.overflow-y-auto { scrollbar-width: thin; scrollbar-color: #333 transparent; }
.overflow-y-auto::-webkit-scrollbar { width: 4px; }
.overflow-y-auto::-webkit-scrollbar-track { background: transparent; }
.overflow-y-auto::-webkit-scrollbar-thumb { background: #333; border-radius: 999px; }
</style>

<style>
/* Markdown 内容 */
.msg-content p { margin: 0 0 0.4rem 0; line-height: 1.6; }
.msg-content p:last-child { margin-bottom: 0; }
.msg-content .h3 { font-size: 0.9rem; font-weight: 600; color: #e2e8f0; margin: 0.6rem 0 0.3rem 0; }
.msg-content .h4 { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; margin: 0.5rem 0 0.25rem 0; }
.msg-content strong { font-weight: 600; color: #f1f5f9; }
.msg-content em { font-style: italic; color: #94a3b8; }
.msg-content .inline-code {
    font-family: monospace;
    font-size: 0.8rem;
    background: rgba(255,255,255,0.06);
    color: #a5b4fc;
    padding: 0.1em 0.4em;
    border-radius: 4px;
}
.msg-content .ul { padding-left: 1.2rem; margin: 0.3rem 0; list-style: disc; }
.msg-content .ul li { margin-bottom: 0.2rem; color: #cbd5e1; }
.msg-content .quote { border-left: 2px solid #4b5563; padding: 0.3rem 0.6rem; margin: 0.4rem 0; background: rgba(255,255,255,0.03); border-radius: 0 4px 4px 0; color: #9ca3af; }

/* 代码块 */
.code-block { margin: 0.5rem 0; border-radius: 8px; overflow: hidden; border: 1px solid rgba(255,255,255,0.08); background: #1e1e1e; }
.code-header { display: flex; align-items: center; justify-content: space-between; padding: 0.35rem 0.75rem; background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.05); }
.code-lang { font-family: monospace; font-size: 0.7rem; color: #6b7280; text-transform: uppercase; }
.code-actions { display: flex; gap: 0.3rem; }
.code-btn { padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.7rem; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.05); color: #9ca3af; cursor: pointer; transition: all 0.15s; }
.code-btn:hover { background: rgba(255,255,255,0.1); color: #e2e8f0; }
.code-block pre { margin: 0; padding: 0.75rem; overflow-x: auto; }
.code-block code { font-family: monospace; font-size: 0.8rem; line-height: 1.6; color: #e2e8f0; white-space: pre; }
</style>
