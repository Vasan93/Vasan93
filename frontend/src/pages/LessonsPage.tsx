import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Lesson } from '../lib/types'

export default function LessonsPage() {
  const { data: lessons = [], isLoading } = useQuery({
    queryKey: ['lessons'],
    queryFn: () => api<Lesson[]>('/coach/lessons'),
  })

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-serif text-3xl font-semibold">Your lessons</h1>
      <p className="mt-1 text-ink/60">Each one targets a weakness your coach found in your own games.</p>

      {isLoading && <p className="mt-6 text-ink/50">Loading…</p>}
      {!isLoading && lessons.length === 0 && (
        <p className="mt-6 rounded-xl border border-dashed border-ink/20 px-4 py-8 text-center text-ink/50">
          No lessons yet. Open <Link to="/weaknesses" className="text-accent underline">What to work on</Link> and ask
          your coach to teach one.
        </p>
      )}

      <ul className="mt-6 space-y-2">
        {lessons.map((lesson) => (
          <li key={lesson.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-ink/10 bg-white/60 px-4 py-3">
            <Link to={`/lessons/${lesson.id}`} className="font-medium hover:text-accent">
              {lesson.title}
            </Link>
            <span className="text-xs text-ink/50">{lesson.topic_label}</span>
            <span className="ml-auto text-xs">
              {lesson.passed === true && <span className="text-moss">Check passed</span>}
              {lesson.passed === false && <span className="text-amber-700">Check failed</span>}
              {lesson.passed === null && <span className="text-ink/40">Not attempted</span>}
            </span>
          </li>
        ))}
      </ul>
    </main>
  )
}
