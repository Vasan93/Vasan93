import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../store/auth'
import { Field, buttonClass, inputClass } from '../components/Field'

export default function ProfilePage() {
  const { user, updateProfile } = useAuth()
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [language, setLanguage] = useState(user?.preferred_language ?? 'English')
  const [goal, setGoal] = useState(user?.goal ?? '')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data: languages = ['English'] } = useQuery({
    queryKey: ['languages'],
    queryFn: () => api<string[]>('/auth/languages'),
  })

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      await updateProfile({ display_name: displayName, preferred_language: language, goal })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Your profile</h1>
      <p className="mt-1 text-ink/60">Your coach adapts to what you set here.</p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-xl border border-ink/10 bg-white/70 p-6">
        <Field label="Name">
          <input className={inputClass} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
        </Field>

        <Field label="Coaching language" hint="Lessons, explanations and encouragement all use this language.">
          <select className={inputClass} value={language} onChange={(e) => setLanguage(e.target.value)}>
            {languages.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Current goal">
          <input className={inputClass} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Reach 1500" />
        </Field>

        <div className="flex items-center gap-3">
          <button type="submit" className={buttonClass} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          {saved && <span className="text-sm text-moss">Saved.</span>}
        </div>
      </form>

      <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
          <dt className="text-ink/50">Email</dt>
          <dd className="mt-1 font-medium">{user?.email}</dd>
        </div>
        <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
          <dt className="text-ink/50">Rating estimate</dt>
          <dd className="mt-1 font-mono text-lg font-medium">{user?.current_rating_estimate}</dd>
        </div>
      </dl>
    </main>
  )
}
