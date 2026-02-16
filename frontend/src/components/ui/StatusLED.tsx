type StatusLEDStatus = 'active' | 'syncing' | 'error' | 'inactive'

const statusColors: Record<StatusLEDStatus, string> = {
  active: 'bg-emerald-500',
  syncing: 'bg-amber-500',
  error: 'bg-red-500',
  inactive: 'bg-slate-400 dark:bg-slate-500',
}

const pulseColors: Record<StatusLEDStatus, string> = {
  active: 'bg-emerald-400',
  syncing: 'bg-amber-400',
  error: 'bg-red-400',
  inactive: '',
}

type StatusLEDProps = {
  status: StatusLEDStatus
  className?: string
  size?: 'sm' | 'md'
}

export default function StatusLED({ status, className = '', size = 'sm' }: StatusLEDProps) {
  const dim = size === 'sm' ? 'h-2 w-2' : 'h-3 w-3'
  const pulseDim = size === 'sm' ? 'h-2 w-2' : 'h-3 w-3'

  return (
    <span className={`relative inline-flex ${className}`} role="status" aria-label={`Status: ${status}`}>
      {(status === 'active' || status === 'syncing') && (
        <span
          className={`absolute inline-flex ${pulseDim} rounded-full ${pulseColors[status]} animate-ping opacity-75`}
        />
      )}
      <span className={`relative inline-flex ${dim} rounded-full ${statusColors[status]}`} />
    </span>
  )
}
