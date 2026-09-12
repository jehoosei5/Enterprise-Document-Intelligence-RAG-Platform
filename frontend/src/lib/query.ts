const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface SourceOut {
  index: number
  filename: string
  locator: string
  text: string
}

export interface QueryResponse {
  query_id: string
  conversation_id: string
  answer: string
  sources: SourceOut[]
  rewritten_query: string
  input_tokens: number
  output_tokens: number
}

export interface QueryLogSummary {
  id: string
  question: string
  answer: string
  faithfulness_score: number | null
  context_precision_score: number | null
  answer_relevance_score: number | null
  eval_passed: boolean | null
  feedback: string | null
  latency_total_ms: number
  created_at: string
}

async function parseErrorOrThrow(res: Response): Promise<never> {
  const data = await res.json().catch(() => null)
  throw new Error(data?.detail ?? `Request failed with status ${res.status}`)
}

export async function askAboutDocument(
  token: string,
  documentId: string,
  question: string,
): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, document_id: documentId, evaluate: false }),
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export async function getDocumentQuestions(token: string, documentId: string): Promise<QueryLogSummary[]> {
  const res = await fetch(`${API_BASE_URL}/documents/${documentId}/questions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}
