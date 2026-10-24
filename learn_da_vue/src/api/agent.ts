import { post } from '@/api/index'
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
// 后端 POST /agent/chat 是**一次性返回**（FC 多轮工具调用 + 最终答案），
// 没有 SSE 增量。所以这里如实提供 sendChatMessage：等整段答案回来再交付，
// 不再用「先拿到整段、再当成 token 吐出去」的方式伪装打字机效果。
// 真流式要等后端支持 FC 多轮增量输出（E2），届时再引入 onToken。
// =====================================================

interface SendChatOptions {
  payload: AgentChatRequest
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
 * 发送一条对话消息并等待完整回答
 * POST /agent/chat
 */
export async function sendChatMessage(
  options: SendChatOptions,
): Promise<AgentChatResponse> {
  const { payload, onDone, onError, signal, requestId = randomId() } = options

  try {
    const data = await post<AgentChatBackendData>('/agent/chat', payload, {
      signal,
      headers: { 'X-Request-ID': requestId },
    })
    const reply = data.content ?? ''
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
