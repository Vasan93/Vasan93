import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { DailyActivity } from '../../lib/types'
import ChartTooltip from './ChartTooltip'
import { AXIS_PROPS, GRID, MARK, MAX_BAR_SIZE, formatDay } from './chartTheme'

/** Puzzles attempted per day. One series, columns, hover on the mark itself. */
export default function ActivityChart({ activity }: { activity: DailyActivity[] }) {
  if (activity.length === 0) {
    return <p className="py-10 text-center text-sm text-ink/50">No practice recorded yet.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={activity} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
        <XAxis dataKey="day" tickFormatter={formatDay} {...AXIS_PROPS} minTickGap={24} />
        <YAxis width={28} allowDecimals={false} {...AXIS_PROPS} />
        <Tooltip
          cursor={{ fill: 'rgba(18,16,14,0.04)' }}
          content={<ChartTooltip labelFormatter={(value) => formatDay(String(value))} unit=" puzzles" />}
        />
        <Bar
          dataKey="puzzles"
          fill={MARK}
          maxBarSize={MAX_BAR_SIZE}
          radius={[4, 4, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
