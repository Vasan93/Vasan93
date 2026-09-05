import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { RatingPoint } from '../../lib/types'
import ChartTooltip from './ChartTooltip'
import { AXIS_PROPS, GRID, MARK, SURFACE, makeTimeFormatter, roundedAxis } from './chartTheme'

/**
 * Rating over time. One series, so no legend: the heading says what is plotted, and the
 * last value is labelled directly.
 */
export default function RatingChart({ history }: { history: RatingPoint[] }) {
  if (history.length < 2) {
    return (
      <p className="py-10 text-center text-sm text-ink/50">
        Your rating line appears once you have a second reading. Ratings move slowly, so the weakness progress
        below is the better measure of a good week.
      </p>
    )
  }

  const data = history.map((point) => ({
    day: point.recorded_at,
    rating: point.rating,
    source: point.source,
  }))
  const ratings = data.map((point) => point.rating)
  const axis = roundedAxis(ratings)
  const formatX = makeTimeFormatter(data.map((point) => point.day))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 16, right: 44, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
        <XAxis dataKey="day" tickFormatter={formatX} {...AXIS_PROPS} minTickGap={28} />
        <YAxis domain={axis.domain} ticks={axis.ticks} width={44} allowDecimals={false} {...AXIS_PROPS} />
        <Tooltip
          cursor={{ stroke: GRID, strokeWidth: 1 }}
          content={<ChartTooltip labelFormatter={(value) => formatX(String(value))} />}
        />
        <Line
          // Straight segments, not a spline. A smoothed curve overshoots between points
          // and draws dips the learner never had.
          type="linear"
          dataKey="rating"
          stroke={MARK}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          // The ring keeps the end dot legible where it crosses the line.
          dot={{ r: 4, fill: MARK, stroke: SURFACE, strokeWidth: 2 }}
          activeDot={{ r: 5, fill: MARK, stroke: SURFACE, strokeWidth: 2 }}
          isAnimationActive={false}
          label={({ index, x, y, value }) =>
            index === data.length - 1 ? (
              <text x={Number(x) + 8} y={Number(y) + 4} className="fill-ink text-xs font-semibold">
                {value}
              </text>
            ) : (
              <g />
            )
          }
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
