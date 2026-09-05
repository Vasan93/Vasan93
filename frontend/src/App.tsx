import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AuthPage from './pages/AuthPage'
import HomePage from './pages/HomePage'
import AssessmentPage from './pages/AssessmentPage'
import GamesPage from './pages/GamesPage'
import GameViewerPage from './pages/GameViewerPage'
import LessonPage from './pages/LessonPage'
import LessonsPage from './pages/LessonsPage'
import ProfilePage from './pages/ProfilePage'
import TrainPage from './pages/TrainPage'
import WeaknessesPage from './pages/WeaknessesPage'
import { useAuth } from './store/auth'

export default function App() {
  const { status, restore } = useAuth()

  useEffect(() => {
    void restore()
  }, [restore])

  if (status === 'idle' || (status === 'loading' && !useAuth.getState().user)) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink/50">
        <span className="animate-pulse">Loading…</span>
      </div>
    )
  }

  if (status !== 'authenticated') return <AuthPage />

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="games" element={<GamesPage />} />
          <Route path="games/:gameId" element={<GameViewerPage />} />
          <Route path="weaknesses" element={<WeaknessesPage />} />
          <Route path="assessment" element={<AssessmentPage />} />
          <Route path="train" element={<TrainPage />} />
          <Route path="lessons" element={<LessonsPage />} />
          <Route path="lessons/:lessonId" element={<LessonPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
