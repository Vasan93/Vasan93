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

type Listener = () => void
const expiryListeners = new Set<Listener>()

/** Called when the server rejects a token we thought was good. */
export function onSessionExpired(listener: Listener): () => void {
  expiryListeners.add(listener)
  return () => expiryListeners.delete(listener)
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) headers.set('Content-Type', 'application/json')
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`)

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...options, headers })
  } catch {
    // fetch only rejects on a network-level failure, which is worth naming plainly.
    throw new ApiError('Could not reach the server. Check your connection and try again.', 0)
  }

  if (res.status === 401 && authToken) {
    // The token we were carrying is no longer valid. Sitting on error screens is worse
    // than sending the learner back to sign in.
    setToken(null)
    for (const listener of expiryListeners) listener()
    throw new ApiError('Your session has expired. Please sign in again.', 401)
  }

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
