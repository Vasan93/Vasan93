import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import type { Curriculum, PuzzleAttemptResult, PuzzleOut } from '../lib/types'
import PlayableBoard from '../components/PlayableBoard'
import { buttonClass } from '../components/Field'

export default function TrainPage() {
  const queryClient = useQueryClient()
  const [result, setResult] = useState<PuzzleAttemptResult | null>(null)
  const startedAt = useRef<number>(Date.now())

  const { data: curriculum } = useQuery({
    queryKey: ['curriculum'],
    queryFn: () => api<Curriculum>('/curriculum'),
  })

  const {
    data: puzzle,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['next-puzzle'],
    queryFn: () => api<PuzzleOut>('/puzzles/next'),
    retry: false,
  })

  useEffect(() => {
    startedAt.current = Date.now()
    setResult(null)
  }, [puzzle?.id])

  const attempt = useMutation({
    mutationFn: (san: string) =>
      api<PuzzleAttemptResult>(`/puzzles/${puzzle!.id}/attempt`, {
        method: 'POST',
        body: JSON.stringify({
          answer: san,
          seconds: (Date.now() - startedAt.current) / 1000,
          targets: puzzle!.targets,
        }),
      }),
    onSuccess: (data) => {
      setResult(data)
      void queryClient.invalidateQueries({ queryKey: ['curriculum'] })
      void queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    },
  })

  async function nextPuzzle() {
    setResult(null)
    await refetch()
  }

  if (isLoading) return <p className="p-10 text-ink/50">Finding the right puzzle for you…</p>

  if (error) {
    const message =
      error instanceof ApiError && error.status === 404
        ? 'You have worked through every puzzle in the bank. Import more, or review another game.'
        : (error as Error).message
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="font-serif text-3xl font-semibold">Training</h1>
        <p className="mt-6 rounded-xl border border-dashed border-ink/20 px-4 py-8 text-center text-ink/60">{message}</p>
      </main>
    )
  }

  if (!puzzle) return null

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-serif text-3xl font-semibold">Training</h1>
        <p className="text-ink/60">
          Working on <span className="font-medium text-ink">{puzzle.targets_label}</span>
        </p>
        <span className="ml-auto text-sm text-ink/50">
          Puzzle rating <span className="font-mono">{puzzle.rating}</span>
        </span>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-[1fr_16rem]">
        <div>
          <PlayableBoard
            fen={puzzle.fen}
            orientation={puzzle.side_to_move}
            disabled={attempt.isPending || result !== null}
            onMove={(san) => attempt.mutate(san)}
            result={result ? (result.correct ? 'correct' : 'incorrect') : null}
          />
          <p className="mt-3 text-center text-sm text-ink/60">
            <span className="font-medium capitalize">{puzzle.side_to_move}</span> to move.
            {puzzle.kind === 'concept'
              ? ' Find a good plan; more than one move may work.'
              : ' There is one move that works.'}
          </p>
        </div>

        <aside className="space-y-4">
          {attempt.isPending && <p className="text-sm text-ink/50">Checking…</p>}
          {attempt.isError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{(attempt.error as Error).message}</p>
          )}

          {result && (
            <div
              className={`rounded-xl border p-4 ${
                result.correct ? 'border-moss/40 bg-moss/10' : 'border-amber-300 bg-amber-50'
              }`}
            >
              <p className="font-medium">{result.correct ? 'Correct' : 'Not this time'}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink/80">{result.feedback}</p>
              {!result.correct && (
                <p className="mt-2 text-sm text-ink/60">
                  The move was <span className="font-mono font-semibold">{result.solution}</span>.
                </p>
              )}
              <dl className="mt-3 space-y-1 text-xs text-ink/60">
                <div className="flex justify-between">
                  <dt>Clean solves</dt>
                  <dd className="font-mono">{result.successes}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Next review</dt>
                  <dd className="font-mono">
                    {result.interval_days >= 1 ? `${Math.round(result.interval_days)} days` : 'soon'}
                  </dd>
                </div>
              </dl>
              {result.retired && (
                <p className="mt-3 rounded-lg bg-moss/20 px-2 py-1.5 text-xs text-moss">
                  {result.weakness_label} is no longer a weakness. Well done.
                </p>
              )}
              <button onClick={nextPuzzle} className={`${buttonClass} mt-4 w-full`}>
                Next puzzle
              </button>
            </div>
          )}

          {curriculum && (
            <section className="rounded-xl border border-ink/10 bg-white/60 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-ink/50">Due today</h2>
              {curriculum.due.length === 0 ? (
                <p className="mt-2 text-sm text-ink/50">Nothing due. Anything you solve now is a bonus.</p>
              ) : (
                <ul className="mt-2 space-y-1 text-sm">
                  {curriculum.due.slice(0, 5).map((card) => (
                    <li key={card.weakness_key} className="flex justify-between gap-2">
                      <span className={card.weakness_key === puzzle.targets ? 'font-medium' : 'text-ink/70'}>
                        {card.label}
                      </span>
                      <span className="font-mono text-xs text-ink/40">{card.successes}✓</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-ink/40">{curriculum.puzzles_available} puzzles in the bank</p>
            </section>
          )}
        </aside>
      </div>
    </main>
  )
}
