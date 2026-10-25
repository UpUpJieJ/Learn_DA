import { ApiError, CancelledError, post } from '@/api/index'
import { randomId } from '@/lib/uuid'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentFeedbackResponse,
  AgentFeedbackValue,
  ChatMessage,
  TeachingFeedback,
} from '@/types/api'

// =====================================================
// Agent API
//
// 后端 POST /agent/chat/stream 是真 SSE：文本增量边生成边下发，工具轮先发
// 一条 tool 事件再继续。这里用 fetch + ReadableStream 读取（不是
// EventSource —— 那条路只支持 GET，塞不进对话上下文）。
//
// 为什么不用 axios：axios 的 XHR 适配器拿不到增量流；fetch 的
// response.body 才能逐块读。业务错误信封（HTTP 200 + code>=400）在这里
// 单独处理一次，语义与 axios 拦截器保持一致。
// =====================================================

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/** 服务端下发的事件（与后端 AgentStreamEvent 对齐） */
type AgentStreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'tool'; names: string[] }
  | {
      type: 'error'
      reason: string
      partial: boolean
    }
  | { type: 'done'; data: AgentChatBackendData }

interface AgentChatBackendData {
  content?: string
  model?: string
  usedFallback?: boolean
  fallbackReason?: string | null
  teachingFeedback?: TeachingFeedback | null
  interactionId?: number | null
}

export interface SendChatOptions {
  payload: AgentChatRequest
  /** 每个文本增量到达时调用（已经是最终文本，不需要前端再拼接） */
  onDelta?: (text: string) => void
  /** 服务端正在调用工具（查知识库 / 查任务记录），用于显示「正在查…」 */
  onTool?: (names: string[]) => void
  onDone?: (
    fullReply: string,
    feedback?: TeachingFeedback | null,
    interactionId?: number | null,
  ) => void
  /** 中途失败。partial=true 表示已吐出的内容不完整，不能当完整回答 */
  onError?: (error: Error, partial?: boolean) => void
  signal?: AbortSignal
  requestId?: string
}

/**
 * 发送一条对话消息并流式接收回答
 * POST /agent/chat/stream
 */
export async function sendChatMessage(
  options: SendChatOptions,
): Promise<AgentChatResponse> {
  const {
    payload,
    onDelta,
    onTool,
    onDone,
    onError,
    signal,
    requestId = randomId(),
  } = options

  let reply = ''
  let finalData: AgentChatBackendData | null = null
  let interrupted = false

  try {
    const response = await fetch(`${API_BASE_URL}/agent/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-Request-ID': requestId,
      },
      credentials: 'include',
      body: JSON.stringify(payload),
      signal,
    })

    if (!response.ok) {
      throw await buildHttpError(response)
    }
    if (!response.body) {
      throw new ApiError('浏览器不支持流式响应', -1)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    // 逐块读，按 SSE 的空行切分事件；最后一块可能只有半个事件，留在 buffer
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseEventBlock(block)
        if (event) {
          if (event.type === 'delta') {
            reply += event.text
            onDelta?.(event.text)
          } else if (event.type === 'tool') {
            onTool?.(event.names)
          } else if (event.type === 'error') {
            interrupted = true
            // 已吐出的字不撤回，只标记不完整（后端同样这么判定）
            onError?.(new ApiError(errorReasonText(event.reason), -1), event.partial)
          } else if (event.type === 'done') {
            finalData = event.data
          }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }

    const content = finalData?.content ?? reply
    if (onDone) {
      onDone(
        content,
        finalData?.teachingFeedback ?? null,
        finalData?.interactionId ?? null,
      )
    }
    return {
      reply: content,
      model: finalData?.model,
      usedFallback: interrupted || (finalData?.usedFallback ?? false),
      teachingFeedback: finalData?.teachingFeedback ?? null,
      interactionId: finalData?.interactionId ?? null,
    }
  } catch (error) {
    if (isAbortError(error)) {
      const cancelled = new CancelledError('已停止生成')
      onError?.(cancelled)
      throw cancelled
    }
    const err = error instanceof Error ? error : new Error('请求失败')
    // 流中断时前面已经调过 onError(partial)，这里不重复报
    if (!interrupted) onError?.(err)
    throw err
  }
}

function parseEventBlock(block: string): AgentStreamEvent | null {
  const line = block
    .split('\n')
    .map((item) => item.trim())
    .find((item) => item.startsWith('data:'))
  if (!line) return null
  const raw = line.slice('data:'.length).trim()
  if (!raw) return null
  try {
    return JSON.parse(raw) as AgentStreamEvent
  } catch {
    // 服务端只发 JSON；坏行直接丢弃，不要让一条脏数据打断整段回答
    return null
  }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { name?: string }).name === 'AbortError'
  )
}

async function buildHttpError(response: Response): Promise<ApiError> {
  let message = `请求失败（${response.status}）`
  try {
    const body = (await response.json()) as { msg?: string; message?: string }
    message = body.msg ?? body.message ?? message
  } catch {
    // 非 JSON 响应（如网关 HTML 错误页）：保留状态码文案
  }
  return new ApiError(message, response.status)
}

function errorReasonText(reason: string): string {
  switch (reason) {
    case 'stream_interrupted':
      return '回答生成到一半中断了，上面的内容不完整'
    case 'no_api_key':
      return 'AI 助手暂时不可用：服务端没有配置模型密钥'
    case 'rate_limited':
      return 'AI 助手暂时不可用：模型限流'
    case 'timeout':
      return 'AI 助手暂时不可用：模型超时'
    case 'empty_response':
      return 'AI 助手这次没有生成任何内容'
    default:
      return 'AI 助手暂时不可用（模型调用失败）'
  }
}

export function recordAgentFeedback(
  interactionId: number,
  feedback: AgentFeedbackValue,
): Promise<AgentFeedbackResponse> {
  return post<AgentFeedbackResponse>('/agent/feedback', {
    interactionId,
    feedback,
  })
}

/**
 * 从消息列表中提取对话历史（排除 system 消息和当前用户消息）
 * 最多保留 20 条消息
 */
export function buildChatHistory(
  messages: ChatMessage[],
  currentMessageId?: string,
): Pick<ChatMessage, 'role' | 'content'>[] {
  const filtered = messages
    .filter((m) => m.role !== 'system')
    .filter((m) => m.id !== currentMessageId)
    .map(({ role, content }) => ({ role, content }))
  return filtered.slice(-20)
}
