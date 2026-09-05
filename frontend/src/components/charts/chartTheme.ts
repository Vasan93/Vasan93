/**
 * Shared chart constants.
 *
 * One mark hue across the dashboard. Every chart here plots a single series, so
 * identity never rides on colour: titles name what is plotted and status is carried by
 * text badges, not by hue. The hue was validated against the card surface for the
 * lightness band, chroma floor and 3:1 contrast.
 */
export const MARK = '#a85f28'
export const SURFACE = '#fbf9f5'
export const GRID = '#e7e1d6'

export const AXIS_PROPS = {
  stroke: GRID,
  strokeWidth: 1,
  tick: { fill: '#6b645c', fontSize: 11 },
  tickLine: false,
} as const

/** Bars never fill their slot; the leftover band is deliberate air. */
export const MAX_BAR_SIZE = 24

export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** Same-day readings need a time, or every tick reads identically. */
export function makeTimeFormatter(isoValues: string[]): (iso: string) => string {
  const times = isoValues.map((value) => new Date(value).getTime()).filter((time) => !Number.isNaN(time))
  if (times.length < 2) return formatDay
  const spanHours = (Math.max(...times) - Math.min(...times)) / 3_600_000
  if (spanHours > 36) return formatDay
  return (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

/**
 * A domain on round numbers, with ticks a reader can actually read.
 * Recharts' automatic domain lands on values like 954 and 1229.
 */
export function roundedAxis(values: number[], step = 50, tickCount = 4): { domain: [number, number]; ticks: number[] } {
  const low = Math.min(...values)
  const high = Math.max(...values)
  const padding = Math.max(step, Math.round(((high - low) * 0.2) / step) * step)
  const min = Math.floor((low - padding) / step) * step
  const max = Math.ceil((high + padding) / step) * step

  const rawStep = (max - min) / (tickCount - 1)
  const tickStep = Math.max(step, Math.round(rawStep / step) * step)

  // Keep stepping until the ticks cover the top of the range. Stopping at `max` can
  // leave the last tick below the highest value, which clips the mark off the chart.
  const ticks: number[] = [min]
  while (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + tickStep)
  return { domain: [min, ticks[ticks.length - 1]], ticks }
}
