/** Thin typed fetch wrapper around the backend API. */

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

let authToken: string | null = localStorage.getItem('gm_token')

export function setToken(token: string | null): void {
  authToken = token
  if (token) localStorage.setItem('gm_token', token)
  else localStorage.removeItem('gm_token')
}

export function getToken(): string | null {
  return authToken
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) headers.set('Content-Type', 'application/json')
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`)

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export interface Health {
  status: string
  service: string
  components: Record<string, string>
}
