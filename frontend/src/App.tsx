import { useQuery } from '@tanstack/react-query'
import { api, type Health } from './lib/api'

export default function App() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/health'),
  })

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="font-serif text-4xl font-semibold tracking-tight">GrandmasterAI</h1>
      <p className="mt-2 text-ink/70">Your personal chess coach. Engine truth, human teaching.</p>

      <section className="mt-10 rounded-xl border border-ink/10 bg-white/60 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink/50">Backend status</h2>
        {isLoading && <p className="mt-3 text-ink/60">Checking…</p>}
        {error && <p className="mt-3 text-red-700">Backend unreachable.</p>}
        {data && (
          <>
            <p className="mt-3 text-lg font-medium">
              {data.service}: <span className={data.status === 'ok' ? 'text-moss' : 'text-accent'}>{data.status}</span>
            </p>
            <dl className="mt-4 grid gap-2 text-sm">
              {Object.entries(data.components).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4 border-b border-ink/5 pb-1">
                  <dt className="text-ink/60">{key}</dt>
                  <dd className="font-mono text-xs">{value}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
      </section>
    </main>
  )
}
