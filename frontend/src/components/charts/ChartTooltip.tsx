import type { TooltipProps } from 'recharts'
import { MARK } from './chartTheme'

/**
 * One readout for the hovered position. The value leads and the label follows, because
 * the reader already knows which series they are on and wants the number.
 */
export default function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  unit = '',
}: TooltipProps<number, string> & { unit?: string }) {
  if (!active || !payload?.length) return null
  const point = payload[0]

  return (
    <div className="rounded-lg border border-ink/10 bg-white px-3 py-2 shadow-sm">
      <p className="flex items-baseline gap-2">
        {/* A short stroke keys the series; a filled box would be data-weight ink. */}
        <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: MARK }} />
        <span className="font-mono text-base font-semibold text-ink">
          {point.value}
          {unit}
        </span>
      </p>
      <p className="mt-0.5 text-xs text-ink/60">
        {labelFormatter ? String(labelFormatter(label, payload)) : String(label)}
      </p>
    </div>
  )
}
