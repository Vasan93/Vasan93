import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { DashboardData } from '../lib/types'
import RatingChart from '../components/charts/RatingChart'
import ActivityChart from '../components/charts/ActivityChart'
import WeaknessProgressChart from '../components/charts/WeaknessProgressChart'
import { formatDay } from '../components/charts/chartTheme'

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
      <p className="text-xs uppercase tracking-wide text-ink/50">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold text-ink">{value}</p>
      {note && <p className="mt-0.5 text-xs text-ink/50">{note}</p>}
    </div>
  )
}

function Panel({
  title,
  subtitle,
  children,
  aside,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  aside?: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-ink/10 bg-white/60 p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-medium">{title}</h2>
        {subtitle && <p className="text-xs text-ink/50">{subtitle}</p>}
        {aside && <div className="ml-auto">{aside}</div>}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export default function DashboardPage() {
  const [showTable, setShowTable] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api<DashboardData>('/dashboard'),
  })

  if (isLoading) return <p className="p-10 text-ink/50">Loading your progress…</p>
  if (!data) return <p className="p-10 text-red-700">Could not load your progress.</p>

  const change = data.rating_change_30d
  const solvedRate =
    data.puzzles_attempted > 0 ? Math.round((data.puzzles_solved / data.puzzles_attempted) * 100) : null

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Your progress</h1>
      <p className="mt-1 max-w-prose text-ink/60">
        Rating moves slowly, especially early on. The weaknesses you have retired are the better measure of a good
        month.
      </p>

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Rating"
          value={String(data.rating)}
          note={change === 0 ? 'no change in 30 days' : `${change > 0 ? '+' : ''}${change} in 30 days`}
        />
        <StatTile
          label="Streak"
          value={`${data.streak_days} ${data.streak_days === 1 ? 'day' : 'days'}`}
          note={data.best_streak > data.streak_days ? `best ${data.best_streak}` : 'your best yet'}
        />
        <StatTile
          label="Puzzles solved"
          value={String(data.puzzles_solved)}
          note={solvedRate !== null ? `${solvedRate}% of ${data.puzzles_attempted}` : 'none yet'}
        />
        <StatTile
          label="Game accuracy"
          value={data.average_accuracy !== null ? `${data.average_accuracy}%` : '—'}
          note={`${data.games_reviewed} ${data.games_reviewed === 1 ? 'game' : 'games'} reviewed`}
        />
      </section>

      <div className="mt-6 space-y-6">
        <Panel
          title="Rating over time"
          subtitle="every reading since you started"
          aside={
            data.rating_history.length > 1 ? (
              <button
                onClick={() => setShowTable((shown) => !shown)}
                className="rounded-md border border-ink/15 px-2.5 py-1 text-xs text-ink/60 transition hover:bg-ink/5"
              >
                {showTable ? 'Hide numbers' : 'Show numbers'}
              </button>
            ) : undefined
          }
        >
          <RatingChart history={data.rating_history} />
          {showTable && (
            <table className="mt-4 w-full text-left text-sm">
              <caption className="sr-only">Every rating reading, with its date and where it came from</caption>
              <thead>
                <tr className="border-b border-ink/10 text-xs uppercase tracking-wide text-ink/50">
                  <th scope="col" className="py-1 font-medium">Date</th>
                  <th scope="col" className="py-1 font-medium">Rating</th>
                  <th scope="col" className="py-1 font-medium">From</th>
                </tr>
              </thead>
              <tbody>
                {data.rating_history.map((point) => (
                  <tr key={point.recorded_at} className="border-b border-ink/5">
                    <td className="py-1">{formatDay(point.recorded_at)}</td>
                    <td className="py-1 font-mono">{point.rating}</td>
                    <td className="py-1 text-ink/60">{point.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel
          title="Weakness progress"
          subtitle={`${data.status_counts.active ?? 0} active · ${data.status_counts.improving ?? 0} improving · ${
            data.status_counts.retired ?? 0
          } retired`}
        >
          <WeaknessProgressChart weaknesses={data.weaknesses} />
        </Panel>

        <Panel title="Practice" subtitle="puzzles attempted each day">
          <ActivityChart activity={data.activity} />
          <p className="mt-3 text-xs text-ink/50">
            {data.lessons_completed} {data.lessons_completed === 1 ? 'lesson' : 'lessons'} passed ·{' '}
            <Link to="/train" className="text-accent underline">
              keep training
            </Link>
          </p>
        </Panel>
      </div>
    </main>
  )
}
