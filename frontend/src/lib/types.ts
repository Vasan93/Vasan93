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
