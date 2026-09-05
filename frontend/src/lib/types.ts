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

export interface CoachingText {
  text: string
  source: 'claude' | 'template'
  /** The language the text is actually written in. */
  language: string
  /** The language the learner asked for; differs only in fallback mode. */
  requested_language: string
  language_fallback: boolean
  notes: string[]
}

export interface LessonSection {
  heading: string
  body: string
}

export interface LessonExample {
  fen: string
  move: string
  explanation: string
  from_your_game: boolean
}

export interface LessonCheck {
  fen: string
  question: string
  hint: string
}

export interface Lesson {
  id: number
  topic: string
  topic_label: string
  title: string
  language: string
  intro: string
  source: string
  opening: string
  sections: LessonSection[]
  examples: LessonExample[]
  check: LessonCheck | null
  passed: boolean | null
  score: number | null
}

export interface CheckResult {
  correct: boolean
  best_move: string
  cp_loss: number
  feedback: string
  source: string
  language_fallback: boolean
}

export interface PuzzleOut {
  id: string
  fen: string
  rating: number
  kind: 'tactical' | 'concept'
  themes: string[]
  taxonomy_keys: string[]
  targets: string
  targets_label: string
  side_to_move: 'white' | 'black'
  source: string
}

export interface PuzzleAttemptResult {
  correct: boolean
  solution: string
  cp_loss: number
  weakness_key: string
  weakness_label: string
  confidence: number
  interval_days: number
  successes: number
  next_due_at: string | null
  retired: boolean
  feedback: string
  feedback_source: string
}

export interface DueCard {
  weakness_key: string
  label: string
  confidence: number
  due_at: string | null
  interval_days: number
  successes: number
  status: string
}

export interface Curriculum {
  due: DueCard[]
  total_active: number
  puzzles_available: number
}

export interface AssessmentStatus {
  answered: number
  total: number
  finished: boolean
  rating_so_far: number
  next_puzzle: PuzzleOut | null
}

export interface AssessmentAnswerResult {
  correct: boolean
  solution: string
  status: AssessmentStatus
}

export interface AssessmentResult {
  rating: number
  confidence_interval: number
  answered: number
  correct: number
  area_summary: string
  top_weaknesses: Weakness[]
  summary: CoachingText
}

export interface PracticeState {
  game_id: number
  fen: string
  user_color: 'white' | 'black'
  turn: 'white' | 'black'
  move_history: string[]
  last_move_uci: string | null
  is_over: boolean
  result: string | null
  outcome_text: string
  opponent_kind: 'maia' | 'stockfish-limited'
  opponent_rating: number
  opponent_note: string
  in_check: boolean
  legal_move_count: number
  review_status: 'pending' | 'queued' | 'running' | 'done' | 'failed'
}

export interface RatingPoint {
  rating: number
  source: string
  recorded_at: string
}

export interface DailyActivity {
  day: string
  puzzles: number
  correct: number
}

export interface WeaknessProgress {
  taxonomy_key: string
  label: string
  category: string
  status: 'active' | 'improving' | 'retired'
  confidence: number
  evidence_count: number
  success_count: number
  attempts: number
  solved: number
  accuracy: number
}

export interface DashboardData {
  rating: number
  rating_history: RatingPoint[]
  rating_change_30d: number
  streak_days: number
  best_streak: number
  puzzles_attempted: number
  puzzles_solved: number
  lessons_completed: number
  games_reviewed: number
  average_accuracy: number | null
  weaknesses: WeaknessProgress[]
  activity: DailyActivity[]
  status_counts: Record<string, number>
}
