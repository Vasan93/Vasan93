import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { AssessmentAnswerResult, AssessmentResult, AssessmentStatus } from '../lib/types'
import PlayableBoard from '../components/PlayableBoard'
import CoachNote from '../components/CoachNote'
import WeaknessCard from '../components/WeaknessCard'
import { buttonClass } from '../components/Field'
import PageSkeleton from '../components/Skeleton'
import { useAuth } from '../store/auth'

export default function AssessmentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { setUser } = useAuth()
  const [lastAnswer, setLastAnswer] = useState<AssessmentAnswerResult | null>(null)
  const [result, setResult] = useState<AssessmentResult | null>(null)
  const startedAt = useRef(Date.now())

  const { data: status, refetch } = useQuery({
    queryKey: ['assessment'],
    queryFn: () => api<AssessmentStatus>('/assessment'),
  })

  useEffect(() => {
    startedAt.current = Date.now()
  }, [status?.next_puzzle?.id])

  const answer = useMutation({
    mutationFn: (san: string) =>
      api<AssessmentAnswerResult>('/assessment/answer', {
        method: 'POST',
        body: JSON.stringify({
          puzzle_id: status!.next_puzzle!.id,
          answer: san,
          seconds: (Date.now() - startedAt.current) / 1000,
        }),
      }),
    onSuccess: (data) => setLastAnswer(data),
  })

  const finish = useMutation({
    mutationFn: () => api<AssessmentResult>('/assessment/finish', { method: 'POST' }),
    onSuccess: async (data) => {
      setResult(data)
      const me = await api<Parameters<typeof setUser>[0]>('/auth/me')
      setUser(me)
      void queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    },
  })

  const restart = useMutation({
    mutationFn: () => api<AssessmentStatus>('/assessment/restart', { method: 'POST' }),
    onSuccess: () => {
      setResult(null)
      setLastAnswer(null)
      void refetch()
    },
  })

  async function next() {
    setLastAnswer(null)
    const fresh = await refetch()
    if (fresh.data?.finished) finish.mutate()
  }

  // ------------------------------------------------------------------ result
  if (result) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="font-serif text-3xl font-semibold">Where you stand</h1>

        <div className="mt-6 rounded-xl border border-ink/10 bg-white/70 p-6 text-center">
          <p className="text-sm uppercase tracking-wide text-ink/50">Starting rating</p>
          <p className="mt-1 font-mono text-5xl font-semibold">{result.rating}</p>
          <p className="mt-1 text-sm text-ink/50">
            give or take {result.confidence_interval} · {result.correct} of {result.answered} solved
          </p>
        </div>

        <div className="mt-6">
          <CoachNote note={result.summary} />
        </div>

        {result.top_weaknesses.length > 0 && (
          <section className="mt-8">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink/50">What we will work on first</h2>
            <ul className="mt-3 space-y-3">
              {result.top_weaknesses.map((weakness) => (
                <WeaknessCard key={weakness.taxonomy_key} weakness={weakness} />
              ))}
            </ul>
          </section>
        )}

        <div className="mt-8 flex flex-wrap gap-3">
          <button onClick={() => navigate('/train')} className={buttonClass}>
            Start training
          </button>
          <button
            onClick={() => restart.mutate()}
            className="rounded-lg border border-ink/20 px-4 py-2 text-sm text-ink/70 transition hover:bg-ink/5"
          >
            Take it again
          </button>
        </div>
      </main>
    )
  }

  if (!status) return <PageSkeleton cards={1} />

  // ------------------------------------------------------------- finished run
  if (status.finished || !status.next_puzzle) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10 text-center">
        <h1 className="font-serif text-3xl font-semibold">All done</h1>
        <p className="mt-2 text-ink/60">Let your coach work out where you stand.</p>
        <button onClick={() => finish.mutate()} className={`${buttonClass} mt-6`} disabled={finish.isPending}>
          {finish.isPending ? 'Working it out…' : 'See my results'}
        </button>
        {finish.isError && <p className="mt-3 text-sm text-red-700">{(finish.error as Error).message}</p>}
      </main>
    )
  }

  // ------------------------------------------------------------- in progress
  const puzzle = status.next_puzzle
  const progress = (status.answered / status.total) * 100

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Skill assessment</h1>
      <p className="mt-1 text-ink/60">
        A few positions across tactics, endgames, openings and strategy. Not sure? Play your best guess.
      </p>

      <div className="mt-5">
        <div className="flex justify-between text-xs text-ink/50">
          <span>
            Position {status.answered + 1} of {status.total}
          </span>
          <span className="capitalize">{puzzle.side_to_move} to move</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink/10">
          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="mt-6">
        <PlayableBoard
          fen={puzzle.fen}
          orientation={puzzle.side_to_move}
          disabled={answer.isPending || lastAnswer !== null}
          onMove={(san) => answer.mutate(san)}
          result={lastAnswer ? (lastAnswer.correct ? 'correct' : 'incorrect') : null}
        />
      </div>

      <div className="mx-auto mt-4 max-w-[26rem]">
        {answer.isPending && <p className="text-center text-sm text-ink/50">Checking…</p>}
        {answer.isError && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-center text-sm text-red-800">
            {(answer.error as Error).message}
          </p>
        )}
        {lastAnswer && (
          <div className="rounded-xl border border-ink/10 bg-white/70 p-4 text-center">
            <p className="font-medium">{lastAnswer.correct ? 'Correct' : 'Not this one'}</p>
            {!lastAnswer.correct && (
              <p className="mt-1 text-sm text-ink/60">
                The move was <span className="font-mono font-semibold">{lastAnswer.solution}</span>.
              </p>
            )}
            <button onClick={next} className={`${buttonClass} mt-3`}>
              {lastAnswer.status.answered >= lastAnswer.status.total ? 'See my results' : 'Next position'}
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
