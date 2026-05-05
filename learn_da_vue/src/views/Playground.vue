<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { usePlaygroundStore } from "@/stores/playground";
import { useLocalStateStore } from "@/stores/localState";
import { fetchExamples, fetchExample, fetchLessonBySlug } from "@/api/learning";
import type { DataFrameCell, ExampleSummary, LessonDetail } from "@/types/api";
import AgentPanel from "@/components/agent/AgentPanel.vue";

const route = useRoute();
const router = useRouter();
const playgroundStore = usePlaygroundStore();
const localStateStore = useLocalStateStore();

// =====================================================
// 课程文档（左侧面板）
// =====================================================

const props = defineProps<{ slug?: string }>();

const currentLesson = ref<LessonDetail | null>(null);
const isLoadingLesson = ref(false);
const isDocPanelCollapsed = ref(false);

async function loadLesson(slug: string) {
  if (!slug) {
    currentLesson.value = null;
    return;
  }
  isLoadingLesson.value = true;
  try {
    currentLesson.value = await fetchLessonBySlug(slug);
  } catch (err) {
    console.error("加载课程失败:", err);
    currentLesson.value = null;
  } finally {
    isLoadingLesson.value = false;
  }
}

watch(
  () => props.slug,
  (slug) => {
    if (slug) loadLesson(slug);
  },
  { immediate: true }
);

function loadLessonCode(code: string) {
  playgroundStore.setCode(code);
}

function goToPrevLesson() {
  if (currentLesson.value?.prevLesson) {
    router.push(`/playground/${currentLesson.value.prevLesson.slug}`);
  }
}

function goToNextLesson() {
  if (currentLesson.value?.nextLesson) {
    router.push(`/playground/${currentLesson.value.nextLesson.slug}`);
  }
}

function toggleDocPanel() {
  isDocPanelCollapsed.value = !isDocPanelCollapsed.value;
}

// 简易 Markdown 渲染
function renderMarkdown(md: string): string {
  if (!md) return "";
  let html = md
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
      const escaped = code
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      return `<div class="doc-code-block" data-lang="${
        lang || "text"
      }"><div class="doc-code-header"><span>${
        lang || "text"
      }</span><button class="doc-code-load" data-code="${encodeURIComponent(
        code.trim()
      )}">加载代码</button></div><pre><code>${escaped}</code></pre></div>`;
    })
    .replace(/`([^`]+)`/g, '<code class="doc-inline-code">$1</code>')
    .replace(/^#### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, "<ul>$&</ul>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/\n{2,}/g, "</p><p>");
  return `<p>${html}</p>`;
}

function handleDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (target.classList.contains("doc-code-load")) {
    const code = decodeURIComponent(target.dataset.code ?? "");
    if (code) {
      playgroundStore.setCode(code);
      target.textContent = "已加载";
      setTimeout(() => {
        target.textContent = "加载代码";
      }, 2000);
    }
  }
}

// =====================================================
// 示例代码选择器
// =====================================================

const examples = ref<ExampleSummary[]>([]);
const isLoadingExamples = ref(false);
const showExampleSelector = ref(false);

const groupedExamples = computed(() => {
  const groups: Record<string, ExampleSummary[]> = {};
  for (const ex of examples.value) {
    const topic = ex.topic || "other";
    if (!groups[topic]) groups[topic] = [];
    groups[topic].push(ex);
  }
  return groups;
});

const topicLabels: Record<string, string> = {
  polars: "Polars",
  duckdb: "DuckDB",
  integration: "组合",
};

async function loadExamples() {
  isLoadingExamples.value = true;
  try {
    examples.value = await fetchExamples();
  } catch (err) {
    console.error("加载示例失败:", err);
  } finally {
    isLoadingExamples.value = false;
  }
}

async function loadExampleCode(slug: string) {
  if (!slug) return;
  try {
    const example = await fetchExample(slug);
    if (example?.code) {
      playgroundStore.setCode(example.code);
      showExampleSelector.value = false;
    }
  } catch (err) {
    console.error("加载示例代码失败:", err);
  }
}

function toggleExampleSelector() {
  showExampleSelector.value = !showExampleSelector.value;
  if (showExampleSelector.value && examples.value.length === 0) {
    loadExamples();
  }
}

// =====================================================
// 布局
// =====================================================

const docPanelWidth = ref(320);
const splitRatio = ref(55);
const isDraggingDoc = ref(false);
const isDragging = ref(false);
const containerRef = ref<HTMLElement | null>(null);
const lineNumbersRef = ref<HTMLElement | null>(null);

const activeResultTab = ref<"output" | "dataframe" | "history" | "assistant">(
  "assistant"
);

const resultTabs = ["output", "dataframe", "history", "assistant"] as const;

const docWidthStyle = computed(() => `${docPanelWidth.value}px`);
const editorWidthStyle = computed(() => `${splitRatio.value}%`);
const resultWidthStyle = computed(() => `${100 - splitRatio.value}%`);

const hasDocPanel = computed(() => !!props.slug);

const statusText = computed(() => {
  if (playgroundStore.isExecuting) return "执行中";
  if (!playgroundStore.lastResponse) return "就绪";
  const s = playgroundStore.lastResponse.status;
  if (s === "success") return `${playgroundStore.executionTime}ms`;
  if (s === "timeout") return "超时";
  return "出错";
});

const statusClass = computed(() => {
  if (playgroundStore.isExecuting) return "bg-blue-500";
  if (!playgroundStore.lastResponse) return "bg-slate-500";
  const s = playgroundStore.lastResponse.status;
  if (s === "success") return "bg-emerald-500";
  if (s === "timeout") return "bg-yellow-500";
  return "bg-red-500";
});

const currentDataFrame = computed(() => playgroundStore.lastResponse?.dataframe ?? null);
const agentContext = computed(() => ({
  currentCode: playgroundStore.code || undefined,
  currentLesson: currentLesson.value?.slug,
  lessonTitle: currentLesson.value?.title,
  lessonCategory: currentLesson.value?.category,
  lessonContent: currentLesson.value?.content?.slice(0, 3000),
  stdout: playgroundStore.stdout || undefined,
  stderr: playgroundStore.stderr || undefined,
  lastError: playgroundStore.stderr || undefined,
}));

// 拖拽文档面板宽度
function onDocDragStart(e: MouseEvent) {
  e.preventDefault();
  isDraggingDoc.value = true;
  const startX = e.clientX;
  const startWidth = docPanelWidth.value;

  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX;
    docPanelWidth.value = Math.min(600, Math.max(200, startWidth + delta));
  };
  const onUp = () => {
    isDraggingDoc.value = false;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

// 拖拽分栏
function onDragStart(e: MouseEvent) {
  e.preventDefault();
  isDragging.value = true;
  const onMove = (ev: MouseEvent) => {
    if (!containerRef.value) return;
    const rect = containerRef.value.getBoundingClientRect();
    const ratio = ((ev.clientX - rect.left) / rect.width) * 100;
    splitRatio.value = Math.min(80, Math.max(20, ratio));
  };
  const onUp = () => {
    isDragging.value = false;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

// 键盘快捷键
function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    playgroundStore.runCode();
    activeResultTab.value = "output";
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "l") {
    e.preventDefault();
    playgroundStore.clearOutput();
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
  document.addEventListener("click", handleClickOutside);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("click", handleClickOutside);
});

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest(".example-selector")) {
    showExampleSelector.value = false;
  }
}

async function runCode() {
  const response = await playgroundStore.runCode();
  activeResultTab.value = response?.resultType === "dataframe" ? "dataframe" : "output";
}

function syncLineNumberScroll(e: Event) {
  const textarea = e.target as HTMLTextAreaElement;
  if (lineNumbersRef.value) {
    lineNumbersRef.value.scrollTop = textarea.scrollTop;
  }
}

function copyOutput() {
  const text = [playgroundStore.stdout, playgroundStore.stderr]
    .filter(Boolean)
    .join("\n");
  navigator.clipboard.writeText(text).catch(() => {});
}

function loadHistoryItem(record: (typeof playgroundStore.sortedHistory)[0]) {
  playgroundStore.loadFromHistory(record);
  activeResultTab.value =
    record.response.resultType === "dataframe" ? "dataframe" : "output";
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

function truncateCode(code: string, maxLen = 50): string {
  const oneline = code.replace(/\s+/g, " ").trim();
  return oneline.length > maxLen ? oneline.slice(0, maxLen) + "…" : oneline;
}

function formatDataFrameCell(value: DataFrameCell | undefined): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}
</script>

<template>
  <div class="flex flex-col h-full min-h-0 bg-[#0d1117] overflow-hidden select-none">
    <!-- 顶部工具栏 -->
    <header
      class="flex items-center justify-between px-4 py-2.5 bg-[#161b22] border-b border-white/5 shrink-0"
    >
      <div class="flex items-center gap-4">
        <!-- 当前执行环境 -->
        <div
          class="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200"
          title="当前仅支持 Python 执行，可在 Python 中使用 duckdb 查询 SQL"
        >
          <span>Python</span>
        </div>

        <!-- 课程名（有slug时显示） -->
        <div v-if="currentLesson" class="flex items-center gap-2">
          <span class="text-xs text-slate-400">{{ currentLesson.title }}</span>
        </div>

        <!-- 状态 -->
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="statusClass" />
          <span
            class="text-xs"
            :class="
              playgroundStore.isExecuting
                ? 'text-blue-400'
                : playgroundStore.lastResponse?.status === 'success'
                ? 'text-emerald-400'
                : playgroundStore.lastResponse?.status === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
            "
          >
            {{ statusText }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- 示例 -->
        <div class="relative example-selector">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/10 text-slate-400 hover:text-white hover:border-white/20 transition-all"
            @click="toggleExampleSelector"
          >
            <svg
              class="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            示例
          </button>

          <div
            v-if="showExampleSelector"
            class="absolute top-full right-0 mt-2 w-72 bg-[#1c2128] border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden"
          >
            <div class="px-3 py-2 border-b border-white/10">
              <span class="text-xs text-slate-400">选择示例</span>
            </div>
            <div
              v-if="isLoadingExamples"
              class="p-4 text-center text-slate-500 text-sm"
            >
              加载中...
            </div>
            <div
              v-else-if="examples.length === 0"
              class="p-4 text-center text-slate-500 text-sm"
            >
              暂无示例
            </div>
            <div v-else class="max-h-80 overflow-y-auto py-1">
              <div
                v-for="(group, topic) in groupedExamples"
                :key="topic"
                class="mb-1"
              >
                <div class="px-3 py-1.5 text-xs text-slate-500 bg-white/5">
                  {{ topicLabels[topic] || topic }}
                </div>
                <button
                  v-for="ex in group"
                  :key="ex.slug"
                  class="w-full px-3 py-2 text-left text-sm text-slate-300 hover:bg-white/5 hover:text-white transition-colors"
                  @click="loadExampleCode(ex.slug)"
                >
                  <div class="font-medium">{{ ex.title }}</div>
                  <div class="text-xs text-slate-500 mt-0.5">
                    {{ ex.summary }}
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 字体大小 -->
        <div class="flex items-center gap-1">
          <button
            class="w-6 h-6 rounded flex items-center justify-center text-slate-500 hover:text-white hover:bg-white/10 transition-colors text-xs font-mono"
            @click="localStateStore.decreaseFontSize()"
          >
            −
          </button>
          <span class="text-xs text-slate-600 w-5 text-center">{{
            localStateStore.editorFontSize
          }}</span>
          <button
            class="w-6 h-6 rounded flex items-center justify-center text-slate-500 hover:text-white hover:bg-white/10 transition-colors text-xs font-mono"
            @click="localStateStore.increaseFontSize()"
          >
            +
          </button>
        </div>

        <!-- 运行 -->
        <button
          class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all"
          :class="
            playgroundStore.isExecuting
              ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white'
          "
          :disabled="playgroundStore.isExecuting"
          @click="runCode"
        >
          <svg
            v-if="!playgroundStore.isExecuting"
            class="w-4 h-4"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M8 5v14l11-7z" />
          </svg>
          <svg
            v-else
            class="w-4 h-4 animate-spin"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          {{ playgroundStore.isExecuting ? "运行中" : "运行" }}
        </button>
      </div>
    </header>

    <!-- 主体 -->
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <!-- 左侧：课程文档 -->
      <div
        v-if="hasDocPanel"
        class="flex flex-col h-full bg-[#0d1117] border-r border-white/5 shrink-0 transition-all duration-300"
        :class="isDocPanelCollapsed ? 'w-10' : ''"
        :style="!isDocPanelCollapsed ? { width: docWidthStyle } : {}"
      >
        <!-- 折叠态 -->
        <div v-if="isDocPanelCollapsed" class="flex flex-col items-center py-3">
          <button
            class="p-2 rounded text-slate-500 hover:text-white hover:bg-white/5"
            @click="toggleDocPanel"
          >
            <svg
              class="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        </div>

        <!-- 展开态 -->
        <template v-else>
          <!-- 文档头部 -->
          <div
            class="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-white/5 shrink-0"
          >
            <div class="flex items-center gap-2 min-w-0 flex-1">
              <svg
                class="w-4 h-4 text-slate-500 shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="1.5"
                  d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                />
              </svg>
              <span class="text-xs font-medium text-slate-300 truncate">{{
                currentLesson?.title ?? "课程"
              }}</span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <!-- 上一节 / 下一节 -->
              <div
                v-if="currentLesson?.prevLesson || currentLesson?.nextLesson"
                class="flex items-center overflow-hidden rounded-md border border-white/10 bg-white/[0.03]"
              >
                <button
                  v-if="currentLesson?.prevLesson"
                  class="flex h-7 items-center gap-1.5 px-2.5 text-xs font-medium text-slate-300 hover:bg-white/8 hover:text-white transition-colors"
                  title="上一节"
                  @click="goToPrevLesson"
                >
                  <svg
                    class="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M15 19l-7-7 7-7"
                    />
                  </svg>
                  <span class="hidden 2xl:inline">上一节</span>
                </button>
                <div
                  v-if="currentLesson?.prevLesson && currentLesson?.nextLesson"
                  class="h-4 w-px bg-white/10"
                />
                <button
                  v-if="currentLesson?.nextLesson"
                  class="flex h-7 items-center gap-1.5 px-2.5 text-xs font-medium text-slate-300 hover:bg-white/8 hover:text-white transition-colors"
                  title="下一节"
                  @click="goToNextLesson"
                >
                  <span class="hidden 2xl:inline">下一节</span>
                  <svg
                    class="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </button>
              </div>
              <!-- 加载示例代码 -->
              <button
                v-if="currentLesson?.codeExample"
                class="flex h-7 items-center gap-1.5 rounded-md border border-blue-400/30 bg-blue-500/12 px-2.5 text-xs font-semibold text-blue-200 shadow-sm shadow-blue-950/20 hover:border-blue-300/50 hover:bg-blue-500/20 hover:text-white transition-colors"
                title="加载示例代码"
                @click="loadLessonCode(currentLesson.codeExample)"
              >
                <svg
                  class="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                </svg>
                <span class="hidden xl:inline">加载示例</span>
              </button>
              <!-- 收起 -->
              <button
                class="w-6 h-6 rounded flex items-center justify-center text-slate-500 hover:text-white hover:bg-white/5 transition-colors"
                @click="toggleDocPanel"
              >
                <svg
                  class="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
              </button>
            </div>
          </div>

          <!-- 文档内容 -->
          <div class="flex-1 overflow-y-auto" @click="handleDocClick">
            <!-- 加载中 -->
            <div
              v-if="isLoadingLesson"
              class="flex items-center justify-center h-full"
            >
              <div
                class="w-6 h-6 rounded-full border-2 border-slate-700 border-t-slate-400 animate-spin"
              />
            </div>

            <!-- 课程文档 -->
            <div
              v-else-if="currentLesson"
              class="doc-content px-5 py-4"
              v-html="renderMarkdown(currentLesson.content)"
            />

            <!-- 无内容 -->
            <div
              v-else
              class="flex items-center justify-center h-full text-center px-6"
            >
              <p class="text-sm text-slate-600">课程内容未找到</p>
            </div>
          </div>
        </template>
      </div>

      <!-- 拖拽分隔条：文档 <-> 编辑器 -->
      <div
        v-if="hasDocPanel && !isDocPanelCollapsed"
        class="w-1 shrink-0 bg-white/5 hover:bg-slate-600 cursor-col-resize transition-colors"
        :class="isDraggingDoc ? 'bg-slate-600' : ''"
        @mousedown="onDocDragStart"
      />

      <!-- 编辑器 + 结果 -->
      <div
        ref="containerRef"
        class="flex flex-1 overflow-hidden"
        :class="isDragging ? 'cursor-col-resize' : ''"
      >
        <!-- 编辑器 -->
        <div
          class="flex flex-col min-w-0 h-full overflow-hidden"
          :style="{ width: editorWidthStyle }"
        >
          <div
            class="flex items-center px-4 py-2 bg-[#0d1117] border-b border-white/5 shrink-0"
          >
            <div class="flex items-center gap-2">
              <svg
                class="w-4 h-4 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="1.5"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <span class="text-xs text-slate-400 font-mono">
                script.py
              </span>
            </div>
            <span class="ml-auto text-xs text-slate-600"
              >{{ playgroundStore.code.split("\n").length }} 行</span
            >
          </div>

          <div class="flex-1 flex overflow-hidden bg-[#0d1117] min-h-0">
            <div
              ref="lineNumbersRef"
              class="shrink-0 w-12 py-4 bg-[#0d1117] border-r border-white/5 text-right select-none overflow-y-auto"
            >
              <div
                v-for="n in playgroundStore.code.split('\n').length"
                :key="n"
                class="px-3 font-mono text-slate-600 leading-6"
                :style="{ fontSize: `${localStateStore.editorFontSize}px` }"
              >
                {{ n }}
              </div>
            </div>
            <textarea
              v-model="playgroundStore.code"
              class="flex-1 p-4 bg-[#0d1117] text-slate-300 font-mono resize-none outline-none leading-6 caret-blue-400 placeholder-slate-700 overflow-y-auto"
              :style="{ fontSize: `${localStateStore.editorFontSize}px` }"
              placeholder="# 输入代码，Ctrl+Enter 运行"
              spellcheck="false"
              autocomplete="off"
              autocorrect="off"
              autocapitalize="off"
              @keydown.ctrl.enter.prevent="runCode"
              @keydown.meta.enter.prevent="runCode"
              @scroll="syncLineNumberScroll"
            />
          </div>

          <div
            class="flex items-center justify-between px-4 py-1.5 bg-[#161b22] border-t border-white/5 shrink-0 text-xs text-slate-600"
          >
            <div class="flex items-center gap-4">
              <span>Ctrl+Enter 运行</span>
              <span>Ctrl+L 清空</span>
            </div>
            <span>Python 3.11</span>
          </div>
        </div>

        <!-- 拖拽分隔条 -->
        <div
          class="w-1 shrink-0 bg-white/5 hover:bg-slate-600 cursor-col-resize transition-colors"
          :class="isDragging ? 'bg-slate-600' : ''"
          @mousedown="onDragStart"
        />

        <!-- 结果面板 -->
        <div
          class="flex flex-col min-w-0 h-full overflow-hidden bg-[#0d1117]"
          :style="{ width: resultWidthStyle }"
        >
          <div
            class="flex items-center bg-[#161b22] border-b border-white/5 shrink-0"
          >
            <button
              v-for="tab in resultTabs"
              :key="tab"
              class="flex items-center gap-1.5 px-4 py-2.5 text-xs border-b-2 transition-all"
              :class="
                activeResultTab === tab
                  ? 'border-emerald-500 text-slate-200'
                  : 'border-transparent text-slate-500 hover:text-slate-300'
              "
              @click="activeResultTab = tab"
            >
              <span>{{
                tab === "output"
                  ? "输出"
                  : tab === "dataframe"
                  ? "数据"
                  : tab === "history"
                  ? "历史"
                  : "助手"
              }}</span>
            </button>
            <div
              v-if="activeResultTab !== 'assistant'"
              class="ml-auto flex items-center gap-1 pr-3"
            >
              <button
                class="p-1.5 rounded text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors"
                title="复制"
                @click="copyOutput"
              >
                <svg
                  class="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </button>
              <button
                class="p-1.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/5 transition-colors"
                title="清空"
                @click="playgroundStore.clearOutput()"
              >
                <svg
                  class="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          </div>

          <div class="flex-1 min-h-0 overflow-hidden relative">
            <div
              v-show="activeResultTab === 'output'"
              class="absolute inset-0 overflow-y-auto p-4"
            >
              <div
                v-if="
                  !playgroundStore.hasOutput && !playgroundStore.isExecuting
                "
                class="flex flex-col items-center justify-center h-full text-center"
              >
                <p class="text-sm text-slate-600">按 Ctrl+Enter 运行代码</p>
              </div>
              <div
                v-else-if="playgroundStore.isExecuting"
                class="flex flex-col items-center justify-center h-full gap-3"
              >
                <div
                  class="w-8 h-8 rounded-full border-2 border-slate-700 border-t-slate-400 animate-spin"
                />
                <p class="text-sm text-slate-500">执行中...</p>
              </div>
              <div v-else>
                <div
                  v-if="playgroundStore.lastResponse"
                  class="flex items-center gap-2 mb-3 pb-2 border-b border-white/5 text-xs"
                >
                  <span
                    class="w-2 h-2 rounded-full"
                    :class="
                      playgroundStore.lastResponse.status === 'success'
                        ? 'bg-emerald-500'
                        : playgroundStore.lastResponse.status === 'timeout'
                        ? 'bg-yellow-500'
                        : 'bg-red-500'
                    "
                  />
                  <span
                    :class="
                      playgroundStore.lastResponse.status === 'success'
                        ? 'text-emerald-400'
                        : playgroundStore.lastResponse.status === 'timeout'
                        ? 'text-yellow-400'
                        : 'text-red-400'
                    "
                  >
                    {{
                      playgroundStore.lastResponse.status === "success"
                        ? "成功"
                        : playgroundStore.lastResponse.status === "timeout"
                        ? "超时"
                        : "出错"
                    }}
                  </span>
                  <span class="text-slate-600"
                    >{{ playgroundStore.executionTime }}ms</span
                  >
                </div>
                <pre
                  v-if="playgroundStore.stdout"
                  class="font-mono text-sm text-emerald-400 whitespace-pre-wrap"
                  >{{ playgroundStore.stdout }}</pre
                >
                <div
                  v-if="playgroundStore.stderr"
                  class="mt-3 rounded-lg bg-red-950/20 border border-red-900/30 p-3"
                >
                  <pre
                    class="font-mono text-xs text-red-400 whitespace-pre-wrap"
                    >{{ playgroundStore.stderr }}</pre
                  >
                </div>
              </div>
            </div>
            <div
              v-show="activeResultTab === 'dataframe'"
              class="absolute inset-0 overflow-auto"
            >
              <div
                v-if="!currentDataFrame"
                class="flex h-full flex-col items-center justify-center px-6 text-center"
              >
                <p class="text-sm text-slate-600">运行后可在这里查看表格结果</p>
              </div>

              <div v-else class="min-w-full p-4">
                <div class="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p class="text-sm font-semibold text-slate-200">
                      DataFrame 预览
                    </p>
                    <p class="text-xs text-slate-500">
                      {{ currentDataFrame.rowCount }} 行 /
                      {{ currentDataFrame.columns.length }} 列
                      <span v-if="currentDataFrame.truncated">
                        ，仅显示前 {{ currentDataFrame.rows.length }} 行
                      </span>
                    </p>
                  </div>
                </div>

                <div
                  class="overflow-auto rounded-lg border border-white/8 bg-[#0b0f14]"
                >
                  <table class="min-w-full border-collapse text-left text-xs">
                    <thead class="sticky top-0 z-10 bg-[#161b22]">
                      <tr>
                        <th
                          v-for="column in currentDataFrame.columns"
                          :key="column"
                          class="border-b border-white/8 px-3 py-2 font-semibold text-slate-300"
                        >
                          {{ column }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, rowIndex) in currentDataFrame.rows"
                        :key="rowIndex"
                        class="odd:bg-white/[0.02] hover:bg-white/[0.04]"
                      >
                        <td
                          v-for="column in currentDataFrame.columns"
                          :key="column"
                          class="max-w-64 border-b border-white/[0.04] px-3 py-2 font-mono text-slate-300"
                          :class="
                            row[column] === null || row[column] === undefined
                              ? 'text-slate-600'
                              : ''
                          "
                        >
                          <span class="block truncate">
                            {{ formatDataFrameCell(row[column]) }}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div
              v-show="activeResultTab === 'history'"
              class="absolute inset-0 overflow-y-auto p-4"
            >
              <div
                v-if="playgroundStore.sortedHistory.length === 0"
                class="flex flex-col items-center justify-center h-full text-center"
              >
                <p class="text-sm text-slate-600">暂无执行历史</p>
              </div>
              <div v-else>
                <div class="flex items-center justify-between mb-3">
                  <span class="text-xs text-slate-500"
                    >最近 {{ playgroundStore.sortedHistory.length }} 次</span
                  >
                  <button
                    class="text-xs text-red-500/60 hover:text-red-400"
                    @click="playgroundStore.clearHistory()"
                  >
                    清空
                  </button>
                </div>
                <div class="space-y-2">
                  <div
                    v-for="record in playgroundStore.sortedHistory"
                    :key="record.id"
                    class="p-3 rounded-lg bg-white/3 border border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                    @click="loadHistoryItem(record)"
                  >
                    <div class="flex items-center gap-2 mb-1">
                      <span
                        class="w-2 h-2 rounded-full"
                        :class="
                          record.response.status === 'success'
                            ? 'bg-emerald-500'
                            : record.response.status === 'timeout'
                            ? 'bg-yellow-500'
                            : 'bg-red-500'
                        "
                      />
                      <span
                        class="text-xs"
                        :class="
                          record.response.status === 'success'
                            ? 'text-emerald-400'
                            : record.response.status === 'timeout'
                            ? 'text-yellow-400'
                            : 'text-red-400'
                        "
                      >
                        {{
                          record.response.status === "success"
                            ? "成功"
                            : record.response.status === "timeout"
                            ? "超时"
                            : "出错"
                        }}
                      </span>
                      <span class="text-xs text-slate-600"
                        >{{ record.response.executionTime }}ms</span
                      >
                      <span class="ml-auto text-xs text-slate-600">{{
                        formatTime(record.timestamp)
                      }}</span>
                    </div>
                    <code
                      class="text-xs text-slate-500 font-mono block truncate"
                      >{{ truncateCode(record.code) }}</code
                    >
                  </div>
                </div>
              </div>
            </div>
            <!-- 助手面板 -->
            <div
              v-show="activeResultTab === 'assistant'"
              class="absolute inset-0 flex flex-col bg-[#0d1117] overflow-hidden"
            >
              <AgentPanel :embedded="true" :context="agentContext" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
textarea {
  scrollbar-width: thin;
  scrollbar-color: #30363d transparent;
}
textarea::-webkit-scrollbar {
  width: 6px;
}
textarea::-webkit-scrollbar-track {
  background: transparent;
}
textarea::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 999px;
}

.overflow-y-auto {
  scrollbar-width: thin;
  scrollbar-color: #30363d transparent;
}
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}
.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}
.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 999px;
}
</style>

<style>
/* 课程文档内容样式 */
.doc-content h1 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #e2e8f0;
  margin: 1.2rem 0 0.6rem;
}
.doc-content h2 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #e2e8f0;
  margin: 1.2rem 0 0.5rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.doc-content h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #cbd5e1;
  margin: 1rem 0 0.4rem;
}
.doc-content h4 {
  font-size: 0.9rem;
  font-weight: 600;
  color: #cbd5e1;
  margin: 0.8rem 0 0.3rem;
}
.doc-content p {
  color: #94a3b8;
  line-height: 1.7;
  margin: 0 0 0.6rem;
}
.doc-content strong {
  font-weight: 600;
  color: #e2e8f0;
}
.doc-content em {
  font-style: italic;
  color: #94a3b8;
}
.doc-content ul {
  padding-left: 1.2rem;
  margin: 0.4rem 0;
  list-style: disc;
  color: #94a3b8;
}
.doc-content li {
  margin-bottom: 0.2rem;
  line-height: 1.6;
}
.doc-content blockquote {
  border-left: 2px solid #4b5563;
  padding: 0.3rem 0.6rem;
  margin: 0.5rem 0;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 0 4px 4px 0;
  color: #9ca3af;
}
.doc-content .doc-inline-code {
  font-family: monospace;
  font-size: 0.8rem;
  background: rgba(255, 255, 255, 0.06);
  color: #a5b4fc;
  padding: 0.1em 0.4em;
  border-radius: 4px;
}
.doc-content .doc-code-block {
  margin: 0.6rem 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: #1e1e1e;
}
.doc-content .doc-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.3rem 0.6rem;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.7rem;
}
.doc-content .doc-code-header span {
  color: #6b7280;
  text-transform: uppercase;
  font-family: monospace;
}
.doc-content .doc-code-load {
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  border: 1px solid rgba(59, 130, 246, 0.3);
  background: rgba(59, 130, 246, 0.1);
  color: #60a5fa;
  cursor: pointer;
  transition: all 0.15s;
}
.doc-content .doc-code-load:hover {
  background: rgba(59, 130, 246, 0.2);
}
.doc-content .doc-code-block pre {
  margin: 0;
  padding: 0.6rem;
  overflow-x: auto;
}
.doc-content .doc-code-block code {
  font-family: monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  color: #e2e8f0;
  white-space: pre;
}
</style>
