import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { PracticeState } from '../lib/types'
import PlayableBoard from '../components/PlayableBoard'
import { buttonClass } from '../components/Field'

type Colour = 'white' | 'black' | 'random'

export default function PlayPage() {
  const queryClient = useQueryClient()
  const [colour, setColour] = useState<Colour>('white')
  const [error, setError] = useState<string | null>(null)

  const { data: game, isLoading } = useQuery({
    queryKey: ['practice-current'],
    queryFn: () => api<PracticeState | null>('/practice/current'),
    // Poll while the post-game review runs so the link appears on its own.
    refetchInterval: (query) => {
      const state = query.state.data
      return state?.is_over && state.review_status !== 'done' ? 2000 : false
    },
  })

  const start = useMutation({
    mutationFn: () => api<PracticeState>('/practice/new', { method: 'POST', body: JSON.stringify({ color: colour }) }),
    onSuccess: (state) => {
      setError(null)
      queryClient.setQueryData(['practice-current'], state)
    },
  })

  const move = useMutation({
    mutationFn: (san: string) =>
      api<PracticeState>(`/practice/${game!.game_id}/move`, { method: 'POST', body: JSON.stringify({ move: san }) }),
    onSuccess: (state) => {
      setError(null)
      queryClient.setQueryData(['practice-current'], state)
    },
    onError: (err: Error) => setError(err.message),
  })

  const resign = useMutation({
    mutationFn: () => api<PracticeState>(`/practice/${game!.game_id}/resign`, { method: 'POST' }),
    onSuccess: (state) => queryClient.setQueryData(['practice-current'], state),
  })

  if (isLoading) return <p className="p-10 text-ink/50">Loading…</p>

  if (!game) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="font-serif text-3xl font-semibold">Play a game</h1>
        <p className="mt-2 max-w-prose text-ink/70">
          Your opponent plays at roughly your level. Afterwards your coach reviews the game and adds what it finds to
          your weaknesses.
        </p>

        <div className="mt-6 rounded-xl border border-ink/10 bg-white/70 p-6">
          <p className="text-sm font-medium text-ink/80">Which side would you like?</p>
          <div className="mt-3 flex gap-2">
            {(['white', 'black', 'random'] as const).map((option) => (
              <button
                key={option}
                onClick={() => setColour(option)}
                className={`rounded-lg border px-4 py-2 text-sm capitalize transition ${
                  colour === option ? 'border-accent bg-accent/10 font-medium text-accent' : 'border-ink/15 hover:bg-ink/5'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
          <button onClick={() => start.mutate()} className={`${buttonClass} mt-5`} disabled={start.isPending}>
            {start.isPending ? 'Setting up…' : 'Start playing'}
          </button>
        </div>
      </main>
    )
  }

  const yourTurn = !game.is_over && game.turn === game.user_color

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-serif text-3xl font-semibold">Practice game</h1>
        <p className="text-sm text-ink/60">
          You are {game.user_color}, against a bot around {game.opponent_rating}.
        </p>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-[1fr_16rem]">
        <div>
          <PlayableBoard
            fen={game.fen}
            orientation={game.user_color}
            disabled={!yourTurn || move.isPending}
            onMove={(san) => move.mutate(san)}
          />
          <p className="mt-3 text-center text-sm text-ink/60">
            {game.is_over
              ? game.outcome_text
              : move.isPending
                ? 'Your opponent is thinking…'
                : yourTurn
                  ? game.in_check
                    ? 'You are in check.'
                    : 'Your move.'
                  : 'Waiting for your opponent…'}
          </p>
          {error && <p className="mt-2 text-center text-sm text-red-700">{error}</p>}
        </div>

        <aside className="space-y-4">
          <section className="rounded-xl border border-ink/10 bg-white/60 p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink/50">Moves</h2>
            <ol className="mt-2 max-h-56 overflow-y-auto text-sm">
              {game.move_history.map((san, index) => (
                <li key={`${san}-${index}`} className="flex gap-2 border-b border-ink/5 py-0.5">
                  {index % 2 === 0 && (
                    <span className="w-7 shrink-0 text-right font-mono text-xs text-ink/40">{index / 2 + 1}.</span>
                  )}
                  <span className={index % 2 === 0 ? '' : 'ml-9'}>{san}</span>
                </li>
              ))}
              {game.move_history.length === 0 && <li className="text-ink/40">No moves yet.</li>}
            </ol>
          </section>

          {game.is_over ? (
            <section className="rounded-xl border border-accent/30 bg-accent/5 p-4">
              <p className="font-medium">{game.outcome_text}</p>
              {game.review_status === 'done' ? (
                <Link to={`/games/${game.game_id}`} className={`${buttonClass} mt-3 inline-block`}>
                  See the review
                </Link>
              ) : (
                <p className="mt-2 text-sm text-ink/60">Your coach is reviewing the game…</p>
              )}
              <button
                onClick={() => start.mutate()}
                className="mt-3 block w-full rounded-lg border border-ink/20 px-3 py-2 text-sm transition hover:bg-ink/5"
              >
                Play again
              </button>
            </section>
          ) : (
            <button
              onClick={() => resign.mutate()}
              className="w-full rounded-lg border border-ink/20 px-3 py-2 text-sm text-ink/60 transition hover:bg-ink/5"
              disabled={resign.isPending}
            >
              Resign
            </button>
          )}

          <p className="text-xs leading-relaxed text-ink/40">{game.opponent_note}</p>
        </aside>
      </div>
    </main>
  )
}
