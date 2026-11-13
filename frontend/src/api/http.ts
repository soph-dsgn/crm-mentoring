import type { ApiErrorEnvelope } from './contracts'

type RequestBody = BodyInit | Record<string, unknown> | undefined
type ApiRequestInit = Omit<RequestInit, 'body'> & { body?: RequestBody }
type RequestDependencies = {
  fetchImpl?: typeof fetch
  cookie?: string
  notifyUnauthorized?: boolean
}

let sessionExpiredHandler: (() => void) | null = null

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function setSessionExpiredHandler(handler: (() => void) | null) {
  sessionExpiredHandler = handler
}

export function readCookie(cookie: string, name: string): string | null {
  const prefix = `${name}=`
  for (const part of cookie.split(';')) {
    const normalized = part.trim()
    if (normalized.startsWith(prefix)) {
      try {
        return decodeURIComponent(normalized.slice(prefix.length))
      } catch {
        return null
      }
    }
  }
  return null
}

function isJsonBody(body: RequestBody): body is Record<string, unknown> {
  return Boolean(body) && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof URLSearchParams) && !(body instanceof Blob) && !(body instanceof ArrayBuffer)
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== 'object' || !('error' in value)) return false
  const error = (value as { error?: unknown }).error
  return Boolean(error) && typeof error === 'object' && typeof (error as { code?: unknown }).code === 'string' && typeof (error as { message?: unknown }).message === 'string'
}

export async function apiRequest<T = void>(path: string, init: ApiRequestInit = {}, dependencies: RequestDependencies = {}): Promise<T> {
  const fetchImpl = dependencies.fetchImpl ?? fetch
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()
  const body = isJsonBody(init.body) ? JSON.stringify(init.body) : init.body
  if (isJsonBody(init.body)) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const cookie = dependencies.cookie ?? (typeof document === 'undefined' ? '' : document.cookie)
    const csrf = readCookie(cookie, 'kuratorskaya_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }

  let response: Response
  try {
    response = await fetchImpl(path, { ...init, body, headers, credentials: 'include' })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'connection_error', 'Connection failed')
  }

  if (response.ok) {
    if (response.status === 204) return undefined as T
    const contentType = response.headers.get('content-type') ?? ''
    return (contentType.includes('application/json') ? await response.json() : await response.text()) as T
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    // Non-JSON error bodies are never exposed to the interface.
  }
  const envelope = isErrorEnvelope(payload) ? payload.error : null
  const apiError = new ApiError(response.status, envelope?.code ?? 'request_failed', envelope?.message ?? 'Request failed', envelope?.details ?? {})
  if (response.status === 401 && dependencies.notifyUnauthorized !== false) sessionExpiredHandler?.()
  throw apiError
}
