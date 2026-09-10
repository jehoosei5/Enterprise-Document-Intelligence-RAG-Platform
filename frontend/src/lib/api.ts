const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** POSTs JSON, parses the JSON response, and throws ApiError (using the
 * backend's {"detail": "..."} message) on any non-2xx status.
 */
export async function apiPost<TResponse>(path: string, body: unknown, token?: string): Promise<TResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })

  const data = await res.json().catch(() => null)

  if (!res.ok) {
    const message = data?.detail ?? `Request failed with status ${res.status}`
    throw new ApiError(res.status, message)
  }

  return data as TResponse
}

export async function apiGet<TResponse>(path: string, token?: string): Promise<TResponse> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE_URL}${path}`, { headers })
  const data = await res.json().catch(() => null)

  if (!res.ok) {
    const message = data?.detail ?? `Request failed with status ${res.status}`
    throw new ApiError(res.status, message)
  }

  return data as TResponse
}
