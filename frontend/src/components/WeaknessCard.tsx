import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Lesson, Weakness } from '../lib/types'

const statusStyles: Record<string, string> = {
  active: 'bg-accent/15 text-accent',
  improving: 'bg-amber-100 text-amber-800',
  retired: 'bg-moss/15 text-moss',
}

/** One weakness with its confidence shown as a bar, not a raw number. */
export default function WeaknessCard({ weakness }: { weakness: Weakness }) {
  const navigate = useNavigate()
  const percent = Math.round(weakness.confidence * 100)

  const teach = useMutation({
    mutationFn: () =>
      api<Lesson>('/coach/lessons', {
        method: 'POST',
        body: JSON.stringify({ taxonomy_key: weakness.taxonomy_key }),
      }),
    onSuccess: (lesson) => navigate(`/lessons/${lesson.id}`),
  })
  return (
    <li className="rounded-xl border border-ink/10 bg-white/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">{weakness.label}</h3>
        <span className={`rounded-md px-2 py-0.5 text-xs font-medium capitalize ${statusStyles[weakness.status]}`}>
          {weakness.status}
        </span>
        <span className="ml-auto text-xs text-ink/50">
          seen {weakness.evidence_count}×
          {weakness.success_count > 0 && ` · ${weakness.success_count} clean`}
        </span>
      </div>

      <p className="mt-1 text-sm text-ink/70">{weakness.description}</p>

      <div className="mt-3 flex items-center gap-2">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/10"
          role="meter"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Confidence that ${weakness.label} is a real pattern`}
        >
          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} />
        </div>
        <span className="w-20 shrink-0 text-right text-xs text-ink/50">{percent}% sure</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={() => teach.mutate()}
          disabled={teach.isPending}
          className="rounded-lg border border-accent/40 px-3 py-1.5 text-sm text-accent transition hover:bg-accent/10 disabled:opacity-50"
        >
          {teach.isPending ? 'Preparing your lesson…' : `Teach me: ${weakness.teaching_topic}`}
        </button>
      </div>
      {teach.isError && <p className="mt-2 text-sm text-amber-800">{(teach.error as Error).message}</p>}
    </li>
  )
}
