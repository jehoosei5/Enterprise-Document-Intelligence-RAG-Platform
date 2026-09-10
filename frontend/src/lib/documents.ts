const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type SourceFormat = 'pdf' | 'docx' | 'markdown' | 'text' | 'csv'
export type DocumentStatus = 'processing' | 'ready' | 'failed'

export interface DocumentOut {
  id: string
  filename: string
  title: string
  category: string | null
  is_public: boolean
  source_format: SourceFormat
  page_count: number | null
  ocr_used: boolean
  chunk_count: number | null
  status: DocumentStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

async function parseErrorOrThrow(res: Response): Promise<never> {
  const data = await res.json().catch(() => null)
  throw new Error(data?.detail ?? `Request failed with status ${res.status}`)
}

export async function listDocuments(token: string, category?: string): Promise<DocumentOut[]> {
  const url = new URL(`${API_BASE_URL}/documents`)
  if (category) url.searchParams.set('category', category)

  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export async function uploadDocument(
  token: string,
  params: { file: File; title: string; category: string | null; isPublic: boolean },
): Promise<DocumentOut> {
  const formData = new FormData()
  formData.append('file', params.file)
  formData.append('title', params.title)
  if (params.category) formData.append('category', params.category)
  formData.append('is_public', String(params.isPublic))

  const res = await fetch(`${API_BASE_URL}/documents`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}
