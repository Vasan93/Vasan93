import { describe, expect, it } from 'vitest'
import { describeSwing, labelOf } from '../lib/moveLabels'
import type { ReviewedMove } from '../lib/types'

const base: ReviewedMove = {
  ply: 9, move_number: 5, side: 'white', fen: '', played_move: 'Qb3', best_move: 'Ne2',
  best_move_uci: 'g1e2', best_line: [], eval_cp_before: 100, eval_cp_after: -204, cp_loss: 304,
  win_prob_loss: 21, move_label: 'blunder', detected_motif: 'hung_piece',
  taxonomy_keys: ['hanging_pieces'], taxonomy_labels: ['Hanging pieces'],
}

describe('move labels', () => {
  it('gives each verdict its own annotation', () => {
    expect(labelOf({ ...base, move_label: 'blunder' }).symbol).toBe('??')
    expect(labelOf({ ...base, move_label: 'mistake' }).symbol).toBe('?')
    expect(labelOf({ ...base, move_label: 'inaccuracy' }).symbol).toBe('?!')
    expect(labelOf({ ...base, move_label: 'best' }).symbol).toBe('')
  })

  it('describes a missed mate in words rather than centipawns', () => {
    const missed = { ...base, eval_cp_before: 9998, eval_cp_after: 560, cp_loss: 9438 }
    expect(describeSwing(missed)).toContain('forced mate')
    expect(describeSwing(missed)).not.toMatch(/\d{3,}/)
  })

  it('describes an ordinary error in pawns', () => {
    expect(describeSwing(base)).toContain('3.0 pawns')
  })
})
