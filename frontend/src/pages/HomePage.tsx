import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { AssessmentStatus, Curriculum, Weakness } from '../lib/types'
import { useAuth } from '../store/auth'
import { buttonClass } from '../components/Field'

export default function HomePage() {
  const { user } = useAuth()

  const { data: assessment } = useQuery({
    queryKey: ['assessment'],
    queryFn: () => api<AssessmentStatus>('/assessment'),
  })
  const { data: weaknesses = [] } = useQuery({
    queryKey: ['weaknesses'],
    queryFn: () => api<Weakness[]>('/weaknesses'),
  })
  const { data: curriculum } = useQuery({
    queryKey: ['curriculum'],
    queryFn: () => api<Curriculum>('/curriculum'),
  })

  const needsAssessment = user && !user.assessment_completed
  const top = weaknesses.slice(0, 3)

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Welcome, {user?.display_name}.</h1>
      <p className="mt-2 max-w-prose text-ink/70">
        Your coach speaks {user?.preferred_language} and works from your own games.
      </p>

      {needsAssessment ? (
        <section className="mt-8 rounded-xl border border-accent/30 bg-accent/5 p-6">
          <h2 className="font-medium">Start with a short assessment</h2>
          <p className="mt-1 max-w-prose text-sm text-ink/70">
            Ten positions across tactics, endgames, openings and strategy. It takes a few minutes and tells your
            coach where to begin.
          </p>
          <Link to="/assessment" className={`${buttonClass} mt-4 inline-block`}>
            {assessment && assessment.answered > 0
              ? `Continue (${assessment.answered} of ${assessment.total})`
              : 'Begin assessment'}
          </Link>
        </section>
      ) : (
        <section className="mt-8 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
            <p className="text-xs uppercase tracking-wide text-ink/50">Rating</p>
            <p className="mt-1 font-mono text-2xl font-semibold">{user?.current_rating_estimate}</p>
          </div>
          <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
            <p className="text-xs uppercase tracking-wide text-ink/50">Due today</p>
            <p className="mt-1 font-mono text-2xl font-semibold">{curriculum?.due.length ?? 0}</p>
          </div>
          <div className="rounded-xl border border-ink/10 bg-white/60 p-4">
            <p className="text-xs uppercase tracking-wide text-ink/50">Working on</p>
            <p className="mt-1 font-mono text-2xl font-semibold">{curriculum?.total_active ?? 0}</p>
          </div>
        </section>
      )}

      {top.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink/50">Your top three</h2>
          <ul className="mt-3 space-y-2">
            {top.map((weakness) => (
              <li
                key={weakness.taxonomy_key}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-ink/10 bg-white/60 px-4 py-3"
              >
                <span className="font-medium">{weakness.label}</span>
                <span className="text-xs text-ink/50">{weakness.teaching_topic}</span>
                <span className="ml-auto font-mono text-xs text-ink/40">
                  {Math.round(weakness.confidence * 100)}%
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to="/train" className={buttonClass}>
              Train now
            </Link>
            <Link
              to="/games"
              className="rounded-lg border border-ink/20 px-4 py-2 text-sm text-ink/70 transition hover:bg-ink/5"
            >
              Import a game
            </Link>
          </div>
        </section>
      )}

      {!needsAssessment && top.length === 0 && (
        <p className="mt-8 rounded-xl border border-dashed border-ink/20 px-4 py-8 text-center text-ink/50">
          Nothing to work on yet. <Link to="/games" className="text-accent underline">Import a game</Link> and your
          coach will find your patterns.
        </p>
      )}
    </main>
  )
}
