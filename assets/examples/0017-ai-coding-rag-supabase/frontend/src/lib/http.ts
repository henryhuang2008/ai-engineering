import { supabase } from '@/lib/supabase'
import { env } from '@/lib/env'

export class ApiError extends Error {
  readonly status: number | null
  readonly isNetworkError: boolean

  constructor(
    message: string,
    status: number | null,
    isNetworkError: boolean,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.isNetworkError = isNetworkError
  }
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()
  if (error) {
    throw new ApiError(error.message, null, false)
  }
  return session ? { Authorization: `Bearer ${session.access_token}` } : {}
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const authHeaders = await getAuthHeaders()
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value)
  }
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? AbortSignal.timeout(15_000),
    })
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('The API request timed out.', null, true)
    }
    if (error instanceof TypeError) {
      throw new ApiError(error.message, null, true)
    }
    throw error
  }

  if (!response.ok) {
    const detail = await response.text()
    throw new ApiError(
      detail || `The API request failed with status ${response.status}.`,
      response.status,
      false,
    )
  }
  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
