import type { WeaknessProgress } from '../../lib/types'
import { MARK } from './chartTheme'

const STATUS_STYLE: Record<string, { badge: string; note: string }> = {
  active: { badge: 'bg-accent/15 text-accent', note: 'still costing you points' },
  improving: { badge: 'bg-amber-100 text-amber-800', note: 'getting better' },
  retired: { badge: 'bg-moss/15 text-moss', note: 'held over time' },
}

/**
 * Per-weakness progress as horizontal bars.
 *
 * Rating moves slowly and noisily for a beginner; this moves faster and is the honest
 * measure of a good week. Confidence is the magnitude, so one hue carries it, and status
 * rides a text badge rather than a second colour.
 */
export default function WeaknessProgressChart({ weaknesses }: { weaknesses: WeaknessProgress[] }) {
  if (weaknesses.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-ink/50">
        Nothing tracked yet. Review a game or finish the assessment.
      </p>
    )
  }

  return (
    <ul className="space-y-3">
      {weaknesses.map((weakness) => {
        const percent = Math.round(weakness.confidence * 100)
        const style = STATUS_STYLE[weakness.status] ?? STATUS_STYLE.active
        return (
          <li key={weakness.taxonomy_key}>
            <div className="flex flex-wrap items-baseline gap-2 text-sm">
              <span className="font-medium">{weakness.label}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs font-medium capitalize ${style.badge}`}>
                {weakness.status}
              </span>
              <span className="text-xs text-ink/50">{style.note}</span>
              <span className="ml-auto font-mono text-xs text-ink/60">
                {weakness.attempts > 0 ? `${weakness.solved}/${weakness.attempts} solved` : 'not practised yet'}
              </span>
            </div>
            <div
              className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink/8"
              role="meter"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`How sure your coach is that ${weakness.label} is a real pattern`}
            >
              <div
                className="h-full rounded-r-[4px] transition-all"
                style={{ width: `${Math.max(percent, 2)}%`, background: MARK }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}
