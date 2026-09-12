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

export async function askQuery(
  token: string,
  params: { question: string; document_id?: string; conversation_id?: string; evaluate?: boolean }
): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: params.question,
      document_id: params.document_id ?? null,
      conversation_id: params.conversation_id ?? null,
      evaluate: params.evaluate ?? false,
    }),
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export interface StreamDoneEvent {
  query_id: string
  conversation_id: string
  rewritten_query: string
  sources: SourceOut[]
  input_tokens: number
  output_tokens: number
}

/** Consumes /query/stream's SSE body manually — browsers' EventSource
 * can't POST or send custom headers, so this is the standard way to read
 * an SSE response from a POST fetch(). Calls onDelta per answer-token
 * chunk as it arrives, resolves with the final "done" event's metadata
 * once the stream ends.
 */
export async function askQueryStream(
  token: string,
  params: { question: string; document_id?: string; conversation_id?: string; evaluate?: boolean },
  onDelta: (delta: string) => void,
): Promise<StreamDoneEvent> {
  const res = await fetch(`${API_BASE_URL}/query/stream`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: params.question,
      document_id: params.document_id ?? null,
      conversation_id: params.conversation_id ?? null,
      evaluate: params.evaluate ?? false,
    }),
  })
  if (!res.ok || !res.body) return parseErrorOrThrow(res)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done: StreamDoneEvent | null = null

  while (true) {
    const { value, done: readerDone } = await reader.read()
    if (readerDone) break
    buffer += decoder.decode(value, { stream: true })

    let sepIndex: number
    while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex)
      buffer = buffer.slice(sepIndex + 2)
      const line = rawEvent.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue

      const payload = JSON.parse(line.slice('data: '.length))
      if (payload.event === 'done') {
        done = payload as StreamDoneEvent
      } else if (typeof payload.delta === 'string') {
        onDelta(payload.delta)
      }
    }
  }

  if (!done) throw new Error('Stream ended without a completion event.')
  return done
}

export async function submitFeedback(token: string, queryId: string, rating: 'up' | 'down'): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/queries/${queryId}/feedback`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  })
  if (!res.ok) return parseErrorOrThrow(res)
}

export async function getQueryDetails(token: string, queryId: string): Promise<any> {
  const res = await fetch(`${API_BASE_URL}/queries/${queryId}`, {
    headers: { Authorization: `Bearer ${token}` },
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
