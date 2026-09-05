import type { ReviewedMove } from './types'

/** Presentation for each engine label. Symbols follow chess annotation convention. */
export const MOVE_LABELS: Record<string, { symbol: string; text: string; className: string; badge: string }> = {
  best: { symbol: '', text: 'Best move', className: 'text-moss', badge: 'bg-moss/15 text-moss' },
  good: { symbol: '', text: 'Good', className: 'text-moss', badge: 'bg-moss/10 text-moss' },
  inaccuracy: { symbol: '?!', text: 'Inaccuracy', className: 'text-amber-700', badge: 'bg-amber-100 text-amber-800' },
  mistake: { symbol: '?', text: 'Mistake', className: 'text-orange-700', badge: 'bg-orange-100 text-orange-800' },
  blunder: { symbol: '??', text: 'Blunder', className: 'text-red-700', badge: 'bg-red-100 text-red-800' },
}

export function labelOf(move: ReviewedMove) {
  return MOVE_LABELS[move.move_label] ?? MOVE_LABELS.good
}

/** Engine numbers are for the app, not the learner. Render them as plain language. */
export function describeSwing(move: ReviewedMove): string {
  if (move.eval_cp_before > 9000 && move.eval_cp_after < 9000) return 'a forced mate was available'
  if (move.eval_cp_after < -9000) return 'this allows a forced mate'
  const pawns = (move.cp_loss / 100).toFixed(1)
  return `about ${pawns} pawns of advantage given away`
}
