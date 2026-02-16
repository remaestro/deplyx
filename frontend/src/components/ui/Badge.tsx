type BadgeColor = 'critical' | 'warning' | 'success' | 'info' | 'neutral' | 'purple' | 'orange'

const colorClasses: Record<BadgeColor, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  success: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  orange: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
}

const STATUS_COLOR_MAP: Record<string, BadgeColor> = {
  Draft: 'neutral',
  Pending: 'warning',
  Analyzing: 'info',
  Approved: 'success',
  Executing: 'purple',
  Completed: 'success',
  Rejected: 'critical',
  RolledBack: 'orange',
}

const RISK_COLOR_MAP: Record<string, BadgeColor> = {
  low: 'success',
  medium: 'warning',
  high: 'critical',
}

type BadgeProps = {
  color?: BadgeColor
  children: React.ReactNode
  className?: string
  dot?: boolean
}

export default function Badge({ color = 'neutral', children, className = '', dot }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClasses[color]} ${className}`}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            color === 'success'
              ? 'bg-emerald-500'
              : color === 'critical'
                ? 'bg-red-500'
                : color === 'warning'
                  ? 'bg-amber-500'
                  : color === 'info'
                    ? 'bg-blue-500'
                    : 'bg-slate-500'
          }`}
        />
      )}
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={STATUS_COLOR_MAP[status] ?? 'neutral'} dot>
      {status}
    </Badge>
  )
}

export function RiskBadge({ level }: { level: string | null }) {
  if (!level) return <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
  return (
    <Badge color={RISK_COLOR_MAP[level] ?? 'neutral'}>
      {level}
    </Badge>
  )
}
