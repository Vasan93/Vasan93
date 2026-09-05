import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, getToken, onSessionExpired, setToken } from '../lib/api'

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fake = vi.fn().mockResolvedValue({
    ok: response.ok ?? true,
    status: response.status ?? 200,
    statusText: response.statusText ?? 'OK',
    json: response.json ?? (async () => ({})),
  } as Response)
  vi.stubGlobal('fetch', fake)
  return fake
}

afterEach(() => {
  vi.unstubAllGlobals()
  setToken(null)
})

describe('api', () => {
  it('sends the bearer token when one is stored', async () => {
    setToken('a-token')
    const fetchMock = mockFetch({ json: async () => ({ ok: true }) })
    await api('/health')
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer a-token')
  })

  it('surfaces the server detail message on failure', async () => {
    mockFetch({ ok: false, status: 409, json: async () => ({ detail: 'Already exists.' }) })
    await expect(api('/auth/signup', { method: 'POST', body: '{}' })).rejects.toThrow('Already exists.')
  })

  it('names a network failure in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/health')).rejects.toThrow(/Could not reach the server/)
  })

  it('clears the session and notifies listeners when a token is rejected', async () => {
    setToken('stale-token')
    const expired = vi.fn()
    const unsubscribe = onSessionExpired(expired)
    mockFetch({ ok: false, status: 401 })

    await expect(api('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(getToken()).toBeNull()
    expect(expired).toHaveBeenCalledOnce()
    unsubscribe()
  })

  it('does not treat a failed login as an expired session', async () => {
    const expired = vi.fn()
    const unsubscribe = onSessionExpired(expired)
    mockFetch({ ok: false, status: 401, json: async () => ({ detail: 'Incorrect email or password.' }) })

    await expect(api('/auth/login', { method: 'POST', body: '{}' })).rejects.toThrow('Incorrect email or password.')
    expect(expired).not.toHaveBeenCalled()
    unsubscribe()
  })
})
