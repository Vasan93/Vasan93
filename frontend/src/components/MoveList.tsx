import { useEffect, useRef } from 'react'
import type { GameMove } from '../lib/types'

interface Props {
  moves: GameMove[]
  currentPly: number
  onSelect: (ply: number) => void
  /** Optional per-ply annotation, e.g. an engine label. */
  annotate?: (move: GameMove) => { symbol: string; className: string } | null
}

/** Move list in move-number rows, with the current move highlighted. */
export default function MoveList({ moves, currentPly, onSelect, annotate }: Props) {
  const activeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest' })
  }, [currentPly])

  const rows: { number: number; white?: GameMove; black?: GameMove }[] = []
  for (const move of moves) {
    const last = rows[rows.length - 1]
    if (move.side === 'white' || !last || last.black) rows.push({ number: move.move_number, [move.side]: move })
    else last.black = move
  }

  return (
    <ol className="max-h-[26rem] overflow-y-auto pr-1 text-sm">
      {rows.map((row) => (
        <li key={row.number} className="flex items-baseline gap-2 border-b border-ink/5 py-0.5">
          <span className="w-8 shrink-0 text-right font-mono text-xs text-ink/40">{row.number}.</span>
          {(['white', 'black'] as const).map((side) => {
            const move = row[side]
            if (!move) return <span key={side} className="flex-1" />
            const note = annotate?.(move) ?? null
            return (
              <button
                key={side}
                ref={move.ply === currentPly ? activeRef : undefined}
                onClick={() => onSelect(move.ply)}
                className={`flex-1 rounded px-1.5 py-0.5 text-left transition ${
                  move.ply === currentPly ? 'bg-accent/20 font-semibold' : 'hover:bg-ink/5'
                }`}
              >
                {move.san}
                {note && <span className={`ml-1 font-bold ${note.className}`}>{note.symbol}</span>}
              </button>
            )
          })}
        </li>
      ))}
    </ol>
  )
}
