import type { SourceOut } from './query'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface ConversationSummary {
  id: string
  title: string
  message_count: number
  created_at: string
}

export interface ConversationTurn {
  query_id: string
  question: string
  answer: string
  sources: SourceOut[]
  created_at: string
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: string
  turns: ConversationTurn[]
}

async function parseErrorOrThrow(res: Response): Promise<never> {
  const data = await res.json().catch(() => null)
  throw new Error(data?.detail ?? `Request failed with status ${res.status}`)
}

export async function listConversations(token: string): Promise<ConversationSummary[]> {
  const res = await fetch(`${API_BASE_URL}/conversations`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export async function getConversation(token: string, id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE_URL}/conversations/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}
