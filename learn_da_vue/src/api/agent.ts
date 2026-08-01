import { post } from '@/api/index'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentContext,
  ChatMessage,
  AgentFeedbackResponse,
  AgentFeedbackValue,
  TeachingFeedback,
} from '@/types/api'

// =====================================================
// Agent API（后端已提供非流式响应；前端按伪流式回调兼容面板交互）
// =====================================================

interface StreamChatOptions {
  payload: AgentChatRequest
  onToken?: (token: string) => void
  onDone?: (
    fullReply: string,
    feedback?: TeachingFeedback | null,
    interactionId?: number | null,
  ) => void
  onError?: (error: Error) => void
  signal?: AbortSignal
  requestId?: string
}

interface AgentChatBackendData {
  content?: string
  model?: string
  usedFallback?: boolean
  teachingFeedback?: TeachingFeedback | null
  interactionId?: number | null
}

/**
 * 发送对话消息，兼容当前"伪流式"前端调用约定
 * POST /agent/chat
 */
export async function streamChatMessage(
  options: StreamChatOptions,
): Promise<AgentChatResponse> {
  const {
    payload,
    onToken,
    onDone,
    onError,
    signal,
    requestId = crypto.randomUUID(),
  } = options

  try {
    const data = await post<AgentChatBackendData>('/agent/chat', payload, {
      signal,
      headers: { 'X-Request-ID': requestId },
    })
    const reply = data.content ?? ''
    if (reply && onToken) {
      onToken(reply)
    }
    if (onDone) {
      onDone(reply, data.teachingFeedback ?? null, data.interactionId ?? null)
    }
    return {
      reply,
      model: data.model,
      usedFallback: data.usedFallback,
      teachingFeedback: data.teachingFeedback ?? null,
      interactionId: data.interactionId ?? null,
    }
  } catch (error) {
    const err = error instanceof Error ? error : new Error('请求失败')
    if (onError) {
      onError(err)
    }
    throw err
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
