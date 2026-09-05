import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import type { Arrow, Square } from 'react-chessboard/dist/chessboard/types'
import { api } from '../lib/api'
import type { CoachingText, GameDetail, ReviewStatus } from '../lib/types'
import { describeSwing, labelOf, MOVE_LABELS } from '../lib/moveLabels'
import BoardViewer from '../components/BoardViewer'
import MoveList from '../components/MoveList'
import CoachNote from '../components/CoachNote'
import { buttonClass } from '../components/Field'
import PageSkeleton from '../components/Skeleton'

export default function GameViewerPage() {
  const { gameId } = useParams()
  const queryClient = useQueryClient()
  const [ply, setPly] = useState(0)

  const { data: game, isLoading } = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => api<GameDetail>(`/games/${gameId}`),
  })

  const { data: review } = useQuery({
    queryKey: ['review', gameId],
    queryFn: () => api<ReviewStatus>(`/games/${gameId}/review`),
    // Poll only while the engine is working.
    refetchInterval: (query) => {
      const state = query.state.data?.state
      return state === 'queued' || state === 'running' ? 1200 : false
    },
  })

  const explain = useMutation({
    mutationFn: (ply: number) =>
      api<CoachingText>('/coach/explain', { method: 'POST', body: JSON.stringify({ game_id: Number(gameId), ply }) }),
  })

  const startReview = useMutation({
    mutationFn: () => api<ReviewStatus>(`/games/${gameId}/review`, { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['review', gameId] })
      void queryClient.invalidateQueries({ queryKey: ['weaknesses'] })
    },
  })

  const byPly = useMemo(() => {
    const map = new Map<number, ReviewStatus['moves'][number]>()
    for (const move of review?.moves ?? []) map.set(move.ply, move)
    return map
  }, [review])

  if (isLoading) return <PageSkeleton cards={2} />
  if (!game) return <p className="p-10 text-red-700">That game could not be loaded.</p>

  const fen = game.fens[ply] ?? game.fens[0]
  const lastMove = ply > 0 ? game.moves[ply - 1] : null
  const highlight = lastMove
    ? { from: lastMove.uci.slice(0, 2) as Square, to: lastMove.uci.slice(2, 4) as Square }
    : null
  const reviewed = lastMove ? byPly.get(lastMove.ply) : undefined
  const busy = review?.state === 'queued' || review?.state === 'running'
  const done = review?.state === 'done'

  // Show the engine's preferred move as an arrow, but only where it teaches something.
  const showBetterMove =
    reviewed && reviewed.move_label !== 'best' && reviewed.move_label !== 'good' && reviewed.best_move_uci.length >= 4
  const arrows: Arrow[] = showBetterMove
    ? [[reviewed.best_move_uci.slice(0, 2) as Square, reviewed.best_move_uci.slice(2, 4) as Square, '#4b6b53']]
    : []

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Link to="/games" className="text-sm text-ink/50 hover:text-accent">
        ← All games
      </Link>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="font-serif text-2xl font-semibold">
          {game.white} vs {game.black}
        </h1>
        <p className="text-sm text-ink/60">
          You played {game.user_color}. Result {game.result}.
        </p>
        {done && review?.accuracy != null && (
          <span className="ml-auto rounded-lg bg-white/70 px-3 py-1 text-sm">
            Accuracy <span className="font-mono font-semibold">{review.accuracy}%</span>
          </span>
        )}
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-[1fr_18rem]">
        <div>
          <BoardViewer
            fen={fen}
            orientation={game.user_color}
            ply={ply}
            maxPly={game.moves.length}
            onPlyChange={setPly}
            highlight={highlight}
            arrows={arrows}
          />

          <section className="mt-4 min-h-[7rem] rounded-xl border border-ink/10 bg-white/60 p-4">
            {!review || review.state === 'pending' || review.state === 'unknown' ? (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-ink/60">
                  Have your coach study this game to find the patterns behind your mistakes.
                </p>
                <button onClick={() => startReview.mutate()} className={buttonClass} disabled={startReview.isPending}>
                  Review this game
                </button>
              </div>
            ) : busy ? (
              <div>
                <p className="text-sm text-ink/70">Studying your moves…</p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/10">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{ width: `${review.total ? (review.progress / review.total) * 100 : 8}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-ink/50">
                  {review.progress} of {review.total || '…'} moves
                </p>
              </div>
            ) : review.state === 'failed' ? (
              <p className="text-sm text-red-700">The review failed: {review.error}</p>
            ) : reviewed ? (
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${labelOf(reviewed).badge}`}>
                    {labelOf(reviewed).text}
                  </span>
                  <span className="font-medium">
                    {reviewed.move_number}. {reviewed.played_move}
                  </span>
                  {reviewed.move_label !== 'best' && (
                    <span className="text-sm text-ink/60">
                      the engine prefers <span className="font-medium text-ink">{reviewed.best_move}</span>
                    </span>
                  )}
                </div>
                {showBetterMove && (
                  <>
                    <p className="mt-2 text-sm text-ink/70">
                      {describeSwing(reviewed)}. The green arrow shows what the engine wanted.
                    </p>
                    {reviewed.taxonomy_labels.length > 0 && (
                      <p className="mt-2 flex flex-wrap gap-1.5 text-xs">
                        {reviewed.taxonomy_labels.map((label) => (
                          <span key={label} className="rounded-md bg-ink/5 px-2 py-0.5 text-ink/70">
                            {label}
                          </span>
                        ))}
                      </p>
                    )}
                    {reviewed.best_line.length > 0 && (
                      <p className="mt-2 font-mono text-xs text-ink/50">Better: {reviewed.best_line.slice(0, 6).join(' ')}</p>
                    )}

                    <div className="mt-3">
                      {explain.data && explain.variables === reviewed.ply ? (
                        <CoachNote note={explain.data} compact />
                      ) : (
                        <button
                          onClick={() => explain.mutate(reviewed.ply)}
                          disabled={explain.isPending}
                          className="rounded-lg border border-accent/40 px-3 py-1.5 text-sm text-accent transition hover:bg-accent/10 disabled:opacity-50"
                        >
                          {explain.isPending ? 'Your coach is thinking…' : 'Why was this wrong?'}
                        </button>
                      )}
                      {explain.isError && (
                        <p className="mt-2 text-sm text-red-700">{(explain.error as Error).message}</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <p className="text-sm text-ink/50">
                Step to one of your own moves to see what your coach found.
                {review.label_counts &&
                  ` This game: ${Object.entries(review.label_counts)
                    .filter(([key]) => key in MOVE_LABELS && key !== 'best' && key !== 'good')
                    .map(([key, count]) => `${count} ${key}${count > 1 ? 's' : ''}`)
                    .join(', ') || 'no serious mistakes'}.`}
              </p>
            )}
          </section>
        </div>

        <aside className="rounded-xl border border-ink/10 bg-white/60 p-3">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">Moves</h2>
          <MoveList
            moves={game.moves}
            currentPly={ply}
            onSelect={setPly}
            annotate={(move) => {
              const found = byPly.get(move.ply)
              if (!found) return null
              const style = labelOf(found)
              return style.symbol ? { symbol: style.symbol, className: style.className } : null
            }}
          />
        </aside>
      </div>
    </main>
  )
}
