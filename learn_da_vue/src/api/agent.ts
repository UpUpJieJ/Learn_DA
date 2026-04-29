import { post } from '@/api/index'
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentContext,
  AgentRouteInfo,
  AgentStructuredResult,
  AgentToolName,
  ChatMessage,
} from '@/types/api'

// =====================================================
// Agent API（预留接口，后端尚未实装）
// =====================================================

interface StreamChatOptions {
  payload: AgentChatRequest
  onToken?: (token: string) => void
  onDone?: (fullReply: string) => void
  onError?: (error: Error) => void
  signal?: AbortSignal
}

interface AgentChatBackendData {
  content?: string
  toolName?: AgentToolName
  model?: string
  usedFallback?: boolean
  route?: AgentRouteInfo | null
  structuredResult?: AgentStructuredResult | null
}

/**
 * 发送对话消息，兼容当前“伪流式”前端调用约定
 * POST /agent/chat
 */
export async function streamChatMessage(
  options: StreamChatOptions,
): Promise<AgentChatResponse> {
  const { payload, onToken, onDone, onError, signal } = options

  try {
    const data = await post<AgentChatBackendData>('/agent/chat', payload, { signal })
    const reply = data.content ?? ''
    if (reply && onToken) {
      onToken(reply)
    }
    if (onDone) {
      onDone(reply)
    }
    return {
      reply,
      toolName: data.toolName,
      model: data.model,
      usedFallback: data.usedFallback,
      route: data.route,
      structuredResult: data.structuredResult,
    }
  } catch (error) {
    const err = error instanceof Error ? error : new Error('请求失败')
    if (onError) {
      onError(err)
    }
    throw err
  }
}

/**
 * 从消息列表中提取对话历史（排除 system 消息）
 */
export function buildChatHistory(
  messages: ChatMessage[],
): Pick<ChatMessage, 'role' | 'content'>[] {
  return messages
    .filter((m) => m.role !== 'system')
    .map(({ role, content }) => ({ role, content }))
}

// =====================================================
// 快捷操作
// =====================================================

export interface FixCodeRequest {
  code: string
  errorMessage: string
  context?: AgentContext
}

export interface FixCodeVerification {
  verified: boolean
  status: string
  stdout: string
  stderr: string
  executionTime: number
  usedSandbox: string
}

export interface FixCodeResponse {
  fixedCode: string
  explanation: string
  model?: string
  usedFallback?: boolean
  verification?: FixCodeVerification | null
  structuredResult?: AgentStructuredResult | null
}

/**
 * 修复代码错误
 * POST /agent/fix
 */
export async function fixCode(payload: FixCodeRequest): Promise<FixCodeResponse> {
  return post<FixCodeResponse>('/agent/fix', payload)
}

export interface ExplainCodeRequest {
  code: string
  context?: AgentContext
}

export interface ExplainCodeResponse {
  explanation: string
  model?: string
  usedFallback?: boolean
  structuredResult?: AgentStructuredResult | null
}

/**
 * 解释代码含义
 * POST /agent/explain
 */
export async function explainCode(payload: ExplainCodeRequest): Promise<ExplainCodeResponse> {
  return post<ExplainCodeResponse>('/agent/explain', payload)
}
