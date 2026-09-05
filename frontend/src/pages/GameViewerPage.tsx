import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import type { Square } from 'react-chessboard/dist/chessboard/types'
import { api } from '../lib/api'
import type { GameDetail } from '../lib/types'
import BoardViewer from '../components/BoardViewer'
import MoveList from '../components/MoveList'

export default function GameViewerPage() {
  const { gameId } = useParams()
  const [ply, setPly] = useState(0)

  const { data: game, isLoading, error } = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => api<GameDetail>(`/games/${gameId}`),
  })

  if (isLoading) return <p className="p-10 text-ink/50">Loading game…</p>
  if (error || !game) return <p className="p-10 text-red-700">That game could not be loaded.</p>

  const fen = game.fens[ply] ?? game.fens[0]
  const lastMove = ply > 0 ? game.moves[ply - 1] : null
  const highlight = lastMove
    ? { from: lastMove.uci.slice(0, 2) as Square, to: lastMove.uci.slice(2, 4) as Square }
    : null

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link to="/games" className="text-sm text-ink/50 hover:text-accent">
        ← All games
      </Link>
      <h1 className="mt-2 font-serif text-2xl font-semibold">
        {game.white} vs {game.black}
      </h1>
      <p className="mt-1 text-sm text-ink/60">
        You played {game.user_color}. Result {game.result}. Use ← and → to step through the game.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-[1fr_16rem]">
        <BoardViewer
          fen={fen}
          orientation={game.user_color}
          ply={ply}
          maxPly={game.moves.length}
          onPlyChange={setPly}
          highlight={highlight}
        />
        <aside className="rounded-xl border border-ink/10 bg-white/60 p-3">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink/50">Moves</h2>
          <MoveList moves={game.moves} currentPly={ply} onSelect={setPly} />
        </aside>
      </div>
    </main>
  )
}
