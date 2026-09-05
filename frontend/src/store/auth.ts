import { create } from 'zustand'
import { api, setToken, getToken, onSessionExpired } from '../lib/api'
import type { TokenResponse, User } from '../lib/types'

interface AuthState {
  user: User | null
  status: 'idle' | 'loading' | 'authenticated' | 'anonymous'
  error: string | null
  signup: (input: SignupInput) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  restore: () => Promise<void>
  updateProfile: (patch: Partial<Pick<User, 'display_name' | 'preferred_language' | 'goal'>>) => Promise<void>
  setUser: (user: User) => void
}

export interface SignupInput {
  email: string
  password: string
  display_name: string
  preferred_language: string
  goal: string
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  status: 'idle',
  error: null,

  signup: async (input) => {
    set({ status: 'loading', error: null })
    try {
      const res = await api<TokenResponse>('/auth/signup', { method: 'POST', body: JSON.stringify(input) })
      setToken(res.access_token)
      set({ user: res.user, status: 'authenticated' })
    } catch (err) {
      set({ status: 'anonymous', error: err instanceof Error ? err.message : 'Signup failed' })
      throw err
    }
  },

  login: async (email, password) => {
    set({ status: 'loading', error: null })
    try {
      const res = await api<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      setToken(res.access_token)
      set({ user: res.user, status: 'authenticated' })
    } catch (err) {
      set({ status: 'anonymous', error: err instanceof Error ? err.message : 'Login failed' })
      throw err
    }
  },

  logout: () => {
    setToken(null)
    set({ user: null, status: 'anonymous', error: null })
  },

  restore: async () => {
    if (!getToken()) {
      set({ status: 'anonymous' })
      return
    }
    set({ status: 'loading' })
    try {
      const user = await api<User>('/auth/me')
      set({ user, status: 'authenticated' })
    } catch {
      setToken(null)
      set({ user: null, status: 'anonymous' })
    }
  },

  updateProfile: async (patch) => {
    const user = await api<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(patch) })
    set({ user })
  },

  setUser: (user) => set({ user }),
}))

// A rejected token anywhere in the app returns the learner to the sign-in screen.
onSessionExpired(() => {
  useAuth.setState({ user: null, status: 'anonymous', error: 'Your session has expired. Please sign in again.' })
})
