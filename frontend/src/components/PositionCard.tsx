import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'

/** A small static board used inside lessons. */
export default function PositionCard({
  fen,
  caption,
  size = 240,
}: {
  fen: string
  caption?: string
  size?: number
}) {
  let orientation: 'white' | 'black' = 'white'
  try {
    orientation = new Chess(fen).turn() === 'b' ? 'black' : 'white'
  } catch {
    /* an unparseable FEN still renders as an empty board rather than crashing the page */
  }

  return (
    <figure>
      <div style={{ width: size }} className="max-w-full">
        <Chessboard
          position={fen}
          boardOrientation={orientation}
          arePiecesDraggable={false}
          customBoardStyle={{ borderRadius: '0.5rem' }}
          customLightSquareStyle={{ backgroundColor: '#eadfc8' }}
          customDarkSquareStyle={{ backgroundColor: '#7a6a53' }}
        />
      </div>
      {caption && <figcaption className="mt-2 text-sm text-ink/70">{caption}</figcaption>}
      <p className="mt-1 text-xs text-ink/40">{orientation === 'white' ? 'White' : 'Black'} to move</p>
    </figure>
  )
}
