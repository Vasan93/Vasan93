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
