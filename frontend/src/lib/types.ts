/** Types mirroring the backend Pydantic schemas. */

export interface User {
  id: number
  email: string
  display_name: string
  preferred_language: string
  current_rating_estimate: number
  goal: string
  assessment_completed: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface GameSummary {
  id: number
  white: string | null
  black: string | null
  result: string | null
  user_color: 'white' | 'black'
  source: string
  review_status: 'pending' | 'running' | 'done' | 'failed'
  accuracy: number | null
  played_at: string | null
  created_at: string
  ply_count: number
  outcome: 'win' | 'loss' | 'draw' | 'unknown'
}

export interface GameMove {
  ply: number
  move_number: number
  side: 'white' | 'black'
  san: string
  uci: string
  fen_before: string
}

export interface GameDetail extends GameSummary {
  pgn: string
  moves: GameMove[]
  fens: string[]
}

export interface ImportResult {
  imported: GameSummary[]
  skipped: string[]
}

export interface ReviewedMove {
  ply: number
  move_number: number
  side: 'white' | 'black'
  fen: string
  played_move: string
  best_move: string
  best_move_uci: string
  best_line: string[]
  eval_cp_before: number
  eval_cp_after: number
  cp_loss: number
  win_prob_loss: number
  move_label: 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder'
  detected_motif: string | null
  taxonomy_keys: string[]
  taxonomy_labels: string[]
}

export interface ReviewStatus {
  game_id: number
  state: 'pending' | 'queued' | 'running' | 'done' | 'failed' | 'unknown'
  progress: number
  total: number
  accuracy: number | null
  label_counts: Record<string, number>
  error: string | null
  moves: ReviewedMove[]
}

export interface Weakness {
  taxonomy_key: string
  label: string
  category: string
  description: string
  teaching_topic: string
  confidence: number
  evidence_count: number
  success_count: number
  status: 'active' | 'improving' | 'retired'
}
