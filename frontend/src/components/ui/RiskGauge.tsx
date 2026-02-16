import { useMemo } from 'react'

type RiskGaugeProps = {
  score: number | null
  level: string | null
  size?: number
  className?: string
}

export default function RiskGauge({ score, level, size = 140, className = '' }: RiskGaugeProps) {
  const displayScore = score ?? 0
  const clampedScore = Math.min(100, Math.max(0, displayScore))

  const { path, gradient } = useMemo(() => {
    const cx = size / 2
    const cy = size / 2 + 8
    const r = size / 2 - 12

    // Semicircle from left to right (180 degrees)
    const startAngle = Math.PI
    const endAngle = 0
    const sweepAngle = startAngle - (startAngle - endAngle) * (clampedScore / 100)

    const startX = cx + r * Math.cos(startAngle)
    const startY = cy - r * Math.sin(startAngle)
    const endX = cx + r * Math.cos(sweepAngle)
    const endY = cy - r * Math.sin(sweepAngle)

    const largeArc = clampedScore > 50 ? 1 : 0

    const arcPath = `M ${startX} ${startY} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY}`

    // Background arc (full semicircle)
    const bgEndX = cx + r * Math.cos(endAngle)
    const bgEndY = cy - r * Math.sin(endAngle)
    const bgPath = `M ${startX} ${startY} A ${r} ${r} 0 1 1 ${bgEndX} ${bgEndY}`

    return {
      path: { fg: arcPath, bg: bgPath },
      gradient:
        clampedScore <= 30
          ? ['#10b981', '#34d399'] // green
          : clampedScore <= 70
            ? ['#f59e0b', '#fbbf24'] // amber
            : ['#ef4444', '#f87171'], // red
    }
  }, [clampedScore, size])

  const levelLabel = level ?? (score === null ? 'N/A' : clampedScore <= 30 ? 'low' : clampedScore <= 70 ? 'medium' : 'high')
  const levelColor =
    levelLabel === 'high'
      ? 'text-red-500'
      : levelLabel === 'medium'
        ? 'text-amber-500'
        : levelLabel === 'low'
          ? 'text-emerald-500'
          : 'text-slate-400 dark:text-slate-500'

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <svg width={size} height={size / 2 + 24} viewBox={`0 0 ${size} ${size / 2 + 24}`}>
        <defs>
          <linearGradient id="risk-gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={gradient[0]} />
            <stop offset="100%" stopColor={gradient[1]} />
          </linearGradient>
        </defs>
        {/* Background track */}
        <path
          d={path.bg}
          fill="none"
          stroke="currentColor"
          strokeWidth={10}
          strokeLinecap="round"
          className="text-slate-200 dark:text-slate-700"
        />
        {/* Filled arc */}
        {score !== null && (
          <path
            d={path.fg}
            fill="none"
            stroke="url(#risk-gauge-grad)"
            strokeWidth={10}
            strokeLinecap="round"
            style={{
              transition: 'stroke-dashoffset 0.8s ease-out',
            }}
          />
        )}
        {/* Score text */}
        <text
          x={size / 2}
          y={size / 2 + 4}
          textAnchor="middle"
          className="fill-slate-800 dark:fill-slate-100 text-3xl font-bold"
          style={{ fontSize: size * 0.22 }}
        >
          {score !== null ? displayScore : '—'}
        </text>
      </svg>
      <span className={`-mt-1 text-sm font-semibold uppercase tracking-wide ${levelColor}`}>
        {levelLabel}
      </span>
    </div>
  )
}
