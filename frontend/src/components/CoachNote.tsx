import type { CoachingText } from '../lib/types'

/**
 * The coach's own voice. When no coaching model is configured the text comes from a
 * template, which is correct but plain and English-only -- say so rather than passing it
 * off as coaching.
 */
export default function CoachNote({ note, compact = false }: { note: CoachingText; compact?: boolean }) {
  return (
    <div className={`rounded-xl border border-accent/25 bg-accent/5 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-accent">Your coach</span>
        {note.source === 'template' && (
          <span className="rounded bg-ink/10 px-1.5 py-0.5 text-[0.65rem] text-ink/60">basic mode</span>
        )}
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink/85">{note.text}</p>
      {note.language_fallback && (
        <p className="mt-2 text-xs text-ink/50">
          Written in {note.language}. Coaching in {note.requested_language} needs a coaching model configured.
        </p>
      )}
    </div>
  )
}
