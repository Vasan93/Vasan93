import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import PageSkeleton from './components/Skeleton'
import Layout from './components/Layout'
import AuthPage from './pages/AuthPage'
import HomePage from './pages/HomePage'
import ProfilePage from './pages/ProfilePage'
import { useAuth } from './store/auth'

// Charts and the board are heavy; these routes load their code only when opened.
const AssessmentPage = lazy(() => import('./pages/AssessmentPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const GamesPage = lazy(() => import('./pages/GamesPage'))
const GameViewerPage = lazy(() => import('./pages/GameViewerPage'))
const LessonPage = lazy(() => import('./pages/LessonPage'))
const LessonsPage = lazy(() => import('./pages/LessonsPage'))
const PlayPage = lazy(() => import('./pages/PlayPage'))
const TrainPage = lazy(() => import('./pages/TrainPage'))
const WeaknessesPage = lazy(() => import('./pages/WeaknessesPage'))

export default function App() {
  const { status, restore } = useAuth()

  useEffect(() => {
    void restore()
  }, [restore])

  if (status === 'idle' || (status === 'loading' && !useAuth.getState().user)) {
    return <PageSkeleton cards={1} />
  }

  if (status !== 'authenticated') {
    return (
      <ErrorBoundary>
        <AuthPage />
      </ErrorBoundary>
    )
  }

  return (
    <ErrorBoundary>
    <BrowserRouter>
      <Suspense fallback={<PageSkeleton cards={2} />}>
        <Routes>
            <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="progress" element={<DashboardPage />} />
            <Route path="games" element={<GamesPage />} />
            <Route path="games/:gameId" element={<GameViewerPage />} />
            <Route path="weaknesses" element={<WeaknessesPage />} />
            <Route path="assessment" element={<AssessmentPage />} />
            <Route path="train" element={<TrainPage />} />
            <Route path="play" element={<PlayPage />} />
            <Route path="lessons" element={<LessonsPage />} />
            <Route path="lessons/:lessonId" element={<LessonPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
    </ErrorBoundary>
  )
}
