import { describe, expect, it } from 'vitest'
import { makeTimeFormatter, roundedAxis } from '../components/charts/chartTheme'

describe('roundedAxis', () => {
  it('lands on round numbers rather than the data extremes', () => {
    const { domain, ticks } = roundedAxis([1004, 1183, 1210])
    expect(domain[0] % 50).toBe(0)
    expect(domain[1] % 50).toBe(0)
    expect(ticks.every((tick) => tick % 50 === 0)).toBe(true)
  })

  it('covers every value it is given', () => {
    const values = [954, 1229]
    const { domain } = roundedAxis(values)
    expect(domain[0]).toBeLessThanOrEqual(Math.min(...values))
    expect(domain[1]).toBeGreaterThanOrEqual(Math.max(...values))
  })

  it('still produces a readable axis when every value is identical', () => {
    const { domain, ticks } = roundedAxis([1000, 1000])
    expect(domain[1]).toBeGreaterThan(domain[0])
    expect(ticks.length).toBeGreaterThan(1)
  })
})

describe('makeTimeFormatter', () => {
  it('shows dates across a long span', () => {
    const format = makeTimeFormatter(['2026-08-01T10:00:00Z', '2026-09-01T10:00:00Z'])
    expect(format('2026-08-01T10:00:00Z')).toMatch(/Aug|8/)
  })

  it('shows times when every reading is from the same day', () => {
    const format = makeTimeFormatter(['2026-09-05T09:00:00Z', '2026-09-05T15:00:00Z'])
    expect(format('2026-09-05T09:00:00Z')).toMatch(/\d{1,2}:\d{2}/)
  })
})
