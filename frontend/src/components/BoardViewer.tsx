import { useCallback, useEffect } from 'react'
import { Chessboard } from 'react-chessboard'
import type { Arrow, Square } from 'react-chessboard/dist/chessboard/types'

interface Props {
  fen: string
  orientation: 'white' | 'black'
  ply: number
  maxPly: number
  onPlyChange: (ply: number) => void
  /** Squares to highlight, e.g. the move just played. */
  highlight?: { from: Square; to: Square } | null
  arrows?: Arrow[]
}

/** A read-only board with keyboard-driven playback. */
export default function BoardViewer({ fen, orientation, ply, maxPly, onPlyChange, highlight, arrows }: Props) {
  const step = useCallback(
    (delta: number) => onPlyChange(Math.max(0, Math.min(maxPly, ply + delta))),
    [ply, maxPly, onPlyChange],
  )

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === 'ArrowLeft') step(-1)
      else if (event.key === 'ArrowRight') step(1)
      else if (event.key === 'Home') onPlyChange(0)
      else if (event.key === 'End') onPlyChange(maxPly)
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, onPlyChange, maxPly])

  const squareStyles = highlight
    ? {
        [highlight.from]: { background: 'rgba(180, 112, 58, 0.28)' },
        [highlight.to]: { background: 'rgba(180, 112, 58, 0.38)' },
      }
    : {}

  return (
    <div>
      <div className="mx-auto w-full max-w-[26rem]">
        <Chessboard
          position={fen}
          boardOrientation={orientation}
          arePiecesDraggable={false}
          customBoardStyle={{ borderRadius: '0.6rem', boxShadow: '0 6px 24px rgba(18,16,14,0.14)' }}
          customLightSquareStyle={{ backgroundColor: '#eadfc8' }}
          customDarkSquareStyle={{ backgroundColor: '#7a6a53' }}
          customSquareStyles={squareStyles}
          customArrows={arrows}
        />
      </div>

      <div className="mx-auto mt-3 flex max-w-[26rem] items-center justify-between gap-2">
        <div className="flex gap-1">
          {[
            { label: '⏮', delta: -ply, title: 'Start' },
            { label: '◀', delta: -1, title: 'Previous (←)' },
            { label: '▶', delta: 1, title: 'Next (→)' },
            { label: '⏭', delta: maxPly - ply, title: 'End' },
          ].map((btn) => (
            <button
              key={btn.title}
              title={btn.title}
              onClick={() => step(btn.delta)}
              disabled={btn.delta === 0}
              className="rounded-md border border-ink/15 bg-white px-2.5 py-1 text-sm transition hover:bg-ink/5 disabled:opacity-30"
            >
              {btn.label}
            </button>
          ))}
        </div>
        <span className="font-mono text-xs text-ink/50">
          {ply} / {maxPly}
        </span>
      </div>
    </div>
  )
}
