const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type SourceFormat = 'pdf' | 'docx' | 'markdown' | 'text' | 'csv'
export type DocumentStatus = 'processing' | 'ready' | 'failed'

// Formats content-editing supports — must match the backend's
// _TEXT_BACKED_FORMATS in app/api/documents.py.
export const EDITABLE_FORMATS: SourceFormat[] = ['text', 'markdown', 'csv']

export interface DocumentOut {
  id: string
  filename: string
  title: string
  category: string | null
  is_public: boolean
  source_format: SourceFormat
  size_bytes: number
  page_count: number | null
  ocr_used: boolean
  chunk_count: number | null
  status: DocumentStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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

export async function getDocument(token: string, id: string): Promise<DocumentOut> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export async function getDocumentFile(
  token: string,
  id: string,
): Promise<{ blob: Blob; contentType: string }> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}/file`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
  const blob = await res.blob()
  return { blob, contentType: res.headers.get('content-type') ?? 'application/octet-stream' }
}

export async function updateDocument(
  token: string,
  id: string,
  params: { title?: string; category?: string | null; is_public?: boolean },
): Promise<DocumentOut> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) return parseErrorOrThrow(res)
  return res.json()
}

export async function deleteDocument(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return parseErrorOrThrow(res)
}

export async function updateDocumentContent(
  token: string,
  id: string,
  content: string,
): Promise<DocumentOut> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}/content`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
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
