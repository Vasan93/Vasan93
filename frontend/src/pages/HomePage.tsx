import { useQuery } from '@tanstack/react-query'
import { api, type Health } from '../lib/api'
import { useAuth } from '../store/auth'

export default function HomePage() {
  const { user } = useAuth()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health') })

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Welcome, {user?.display_name}.</h1>
      <p className="mt-2 max-w-prose text-ink/70">
        Your coach speaks {user?.preferred_language}. Next we will find out exactly where your chess stands, then
        start working on the things holding you back.
      </p>

      {user?.goal && (
        <p className="mt-4 rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm">
          <span className="font-medium">Your goal:</span> {user.goal}
        </p>
      )}

      <section className="mt-8 rounded-xl border border-ink/10 bg-white/60 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/50">System</h2>
        <dl className="mt-3 grid gap-2 text-sm">
          {health &&
            Object.entries(health.components).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-4 border-b border-ink/5 pb-1">
                <dt className="text-ink/60">{key}</dt>
                <dd className="font-mono text-xs">{value}</dd>
              </div>
            ))}
        </dl>
      </section>
    </main>
  )
}
