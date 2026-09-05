import type { Weakness } from '../lib/types'

const statusStyles: Record<string, string> = {
  active: 'bg-accent/15 text-accent',
  improving: 'bg-amber-100 text-amber-800',
  retired: 'bg-moss/15 text-moss',
}

/** One weakness with its confidence shown as a bar, not a raw number. */
export default function WeaknessCard({ weakness }: { weakness: Weakness }) {
  const percent = Math.round(weakness.confidence * 100)
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

      <p className="mt-2 text-xs text-ink/50">Next up: {weakness.teaching_topic}</p>
    </li>
  )
}
