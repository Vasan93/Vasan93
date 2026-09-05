import { useCallback, useMemo, useState } from 'react'
import { Chessboard } from 'react-chessboard'
import type { Square } from 'react-chessboard/dist/chessboard/types'
import { Chess } from 'chess.js'

interface Props {
  fen: string
  orientation: 'white' | 'black'
  disabled?: boolean
  /** Called with the move in SAN once the learner makes a legal move. */
  onMove: (san: string) => void
  /** Highlight after the attempt: green for right, red for wrong. */
  result?: 'correct' | 'incorrect' | null
}

/** A board the learner moves on. Legality is enforced client-side and re-checked server-side. */
export default function PlayableBoard({ fen, orientation, disabled = false, onMove, result = null }: Props) {
  const [selected, setSelected] = useState<Square | null>(null)

  const game = useMemo(() => {
    try {
      return new Chess(fen)
    } catch {
      return null
    }
  }, [fen])

  const attempt = useCallback(
    (from: Square, to: Square): boolean => {
      if (disabled || !game) return false
      const probe = new Chess(game.fen())
      try {
        // Promotions default to a queen, which is right in almost every puzzle.
        const move = probe.move({ from, to, promotion: 'q' })
        if (!move) return false
        onMove(move.san)
        return true
      } catch {
        return false
      }
    },
    [disabled, game, onMove],
  )

  const legalTargets = useMemo(() => {
    if (!selected || !game) return {}
    const styles: Record<string, React.CSSProperties> = {}
    for (const move of game.moves({ square: selected, verbose: true })) {
      styles[move.to] = {
        background: 'radial-gradient(circle, rgba(75,107,83,0.35) 26%, transparent 28%)',
      }
    }
    styles[selected] = { background: 'rgba(180,112,58,0.3)' }
    return styles
  }, [selected, game])

  const border =
    result === 'correct'
      ? '0 0 0 3px rgba(75,107,83,0.8)'
      : result === 'incorrect'
        ? '0 0 0 3px rgba(185,28,28,0.7)'
        : '0 6px 24px rgba(18,16,14,0.14)'

  return (
    <div className="mx-auto w-full max-w-[26rem]">
      <Chessboard
        position={fen}
        boardOrientation={orientation}
        arePiecesDraggable={!disabled}
        onPieceDrop={(from, to) => attempt(from as Square, to as Square)}
        onSquareClick={(square) => {
          const sq = square as Square
          if (selected && selected !== sq) {
            if (attempt(selected, sq)) {
              setSelected(null)
              return
            }
          }
          setSelected(game?.get(sq) ? sq : null)
        }}
        customSquareStyles={legalTargets}
        customBoardStyle={{ borderRadius: '0.6rem', boxShadow: border }}
        customLightSquareStyle={{ backgroundColor: '#eadfc8' }}
        customDarkSquareStyle={{ backgroundColor: '#7a6a53' }}
      />
    </div>
  )
}
