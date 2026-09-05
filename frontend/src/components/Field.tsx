import type { ReactNode } from 'react'

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-ink/80">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink/50">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'mt-1 w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-ink outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20'

export const buttonClass =
  'rounded-lg bg-accent px-4 py-2 font-medium text-white transition hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50'
