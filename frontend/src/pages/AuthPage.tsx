import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import { Field, buttonClass, inputClass } from '../components/Field'

export default function AuthPage() {
  const [mode, setMode] = useState<'login' | 'signup'>('signup')
  const { login, signup, error, status } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [language, setLanguage] = useState('English')
  const [goal, setGoal] = useState('')

  const { data: languages = ['English'] } = useQuery({
    queryKey: ['languages'],
    queryFn: () => api<string[]>('/auth/languages'),
  })

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    try {
      if (mode === 'login') await login(email, password)
      else await signup({ email, password, display_name: displayName, preferred_language: language, goal })
    } catch {
      /* the store holds the error message */
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <h1 className="font-serif text-4xl font-semibold tracking-tight">GrandmasterAI</h1>
      <p className="mt-2 text-ink/70">
        A patient coach who learns exactly where you go wrong, and teaches in your language.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4 rounded-xl border border-ink/10 bg-white/70 p-6">
        <div className="flex gap-1 rounded-lg bg-ink/5 p-1 text-sm">
          {(['signup', 'login'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
                mode === m ? 'bg-white shadow-sm' : 'text-ink/60 hover:text-ink'
              }`}
            >
              {m === 'signup' ? 'Create account' : 'Sign in'}
            </button>
          ))}
        </div>

        {mode === 'signup' && (
          <Field label="Your name">
            <input className={inputClass} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </Field>
        )}

        <Field label="Email">
          <input type="email" className={inputClass} value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>

        <Field label="Password" hint={mode === 'signup' ? 'At least 8 characters.' : undefined}>
          <input
            type="password"
            className={inputClass}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={mode === 'signup' ? 8 : undefined}
            required
          />
        </Field>

        {mode === 'signup' && (
          <>
            <Field label="Language you are most comfortable in" hint="Your coach speaks only this language.">
              <select className={inputClass} value={language} onChange={(e) => setLanguage(e.target.value)}>
                {languages.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="What do you want to achieve?" hint="Optional. It shapes what your coach works on first.">
              <input
                className={inputClass}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Stop blundering pieces"
              />
            </Field>
          </>
        )}

        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

        <button type="submit" className={`${buttonClass} w-full`} disabled={status === 'loading'}>
          {status === 'loading' ? 'Just a moment…' : mode === 'signup' ? 'Start coaching' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
