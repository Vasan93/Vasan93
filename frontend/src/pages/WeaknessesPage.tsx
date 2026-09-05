import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Weakness } from '../lib/types'
import WeaknessCard from '../components/WeaknessCard'

const categoryOrder = ['tactical', 'positional', 'opening', 'endgame', 'meta']

export default function WeaknessesPage() {
  const { data: weaknesses = [], isLoading } = useQuery({
    queryKey: ['weaknesses'],
    queryFn: () => api<Weakness[]>('/weaknesses'),
  })

  const grouped = categoryOrder
    .map((category) => ({ category, items: weaknesses.filter((w) => w.category === category) }))
    .filter((group) => group.items.length > 0)

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">What to work on</h1>
      <p className="mt-1 max-w-prose text-ink/60">
        These are patterns, not single blunders. Your coach only calls something a weakness once it has seen it
        happen more than once.
      </p>

      {isLoading && <p className="mt-6 text-ink/50">Loading…</p>}

      {!isLoading && weaknesses.length === 0 && (
        <p className="mt-6 rounded-xl border border-dashed border-ink/20 px-4 py-8 text-center text-ink/50">
          Nothing yet. <Link to="/games" className="text-accent underline">Import a game</Link> and have it reviewed,
          and your patterns will show up here.
        </p>
      )}

      {grouped.map((group) => (
        <section key={group.category} className="mt-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink/50">{group.category}</h2>
          <ul className="space-y-3">
            {group.items.map((weakness) => (
              <WeaknessCard key={weakness.taxonomy_key} weakness={weakness} />
            ))}
          </ul>
        </section>
      ))}
    </main>
  )
}
