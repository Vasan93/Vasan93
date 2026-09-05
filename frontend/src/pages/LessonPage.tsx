import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { CheckResult, Lesson } from '../lib/types'
import PositionCard from '../components/PositionCard'
import { buttonClass, inputClass } from '../components/Field'

export default function LessonPage() {
  const { lessonId } = useParams()
  const queryClient = useQueryClient()
  const [answer, setAnswer] = useState('')

  const { data: lesson, isLoading } = useQuery({
    queryKey: ['lesson', lessonId],
    queryFn: () => api<Lesson>(`/coach/lessons/${lessonId}`),
  })

  const submit = useMutation({
    mutationFn: (move: string) =>
      api<CheckResult>(`/coach/lessons/${lessonId}/check`, { method: 'POST', body: JSON.stringify({ answer: move }) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['lessons'] }),
  })

  if (isLoading) return <p className="p-10 text-ink/50">Loading lesson…</p>
  if (!lesson) return <p className="p-10 text-red-700">That lesson could not be loaded.</p>

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (answer.trim()) submit.mutate(answer.trim())
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <Link to="/lessons" className="text-sm text-ink/50 hover:text-accent">
        ← All lessons
      </Link>
      <h1 className="mt-2 font-serif text-3xl font-semibold">{lesson.title}</h1>
      {lesson.opening && <p className="mt-2 text-ink/70">{lesson.opening}</p>}
      {lesson.intro && lesson.intro !== lesson.opening && (
        <p className="mt-2 text-ink/70">{lesson.intro}</p>
      )}

      {lesson.sections.map((section) => (
        <section key={section.heading} className="mt-6">
          <h2 className="font-medium">{section.heading}</h2>
          <p className="mt-1 text-ink/75">{section.body}</p>
        </section>
      ))}

      {lesson.examples.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink/50">Worked examples</h2>
          <div className="mt-3 space-y-6">
            {lesson.examples.map((example, index) => (
              <div key={`${example.fen}-${index}`} className="rounded-xl border border-ink/10 bg-white/60 p-4">
                {example.from_your_game && (
                  <span className="mb-2 inline-block rounded bg-accent/15 px-2 py-0.5 text-xs text-accent">
                    From your own game
                  </span>
                )}
                <PositionCard fen={example.fen} caption={example.explanation} />
                <p className="mt-2 text-sm">
                  The move: <span className="font-mono font-semibold">{example.move}</span>
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {lesson.check && (
        <section className="mt-8 rounded-xl border border-accent/25 bg-accent/5 p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-accent">Your turn</h2>
          <p className="mt-2 font-medium">{lesson.check.question}</p>
          <div className="mt-3">
            <PositionCard fen={lesson.check.fen} size={260} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 flex flex-wrap items-end gap-3">
            <label className="flex-1">
              <span className="text-sm text-ink/70">Your move</span>
              <input
                className={inputClass}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="e.g. Nf3 or Qxc5"
                disabled={submit.isPending}
              />
            </label>
            <button type="submit" className={buttonClass} disabled={submit.isPending || !answer.trim()}>
              {submit.isPending ? 'Checking…' : 'Check my answer'}
            </button>
          </form>

          {lesson.check.hint && !submit.data && (
            <p className="mt-2 text-xs text-ink/50">Hint: {lesson.check.hint}</p>
          )}
          {submit.isError && <p className="mt-3 text-sm text-red-700">{(submit.error as Error).message}</p>}

          {submit.data && (
            <div
              className={`mt-4 rounded-lg p-3 ${
                submit.data.correct ? 'bg-moss/10 text-ink' : 'bg-white/70 text-ink'
              }`}
            >
              <p className="text-sm font-medium">{submit.data.correct ? 'Correct' : 'Not quite'}</p>
              <p className="mt-1 text-sm leading-relaxed">{submit.data.feedback}</p>
              {!submit.data.correct && (
                <p className="mt-2 text-sm text-ink/60">
                  The move was <span className="font-mono font-semibold">{submit.data.best_move}</span>.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </main>
  )
}
