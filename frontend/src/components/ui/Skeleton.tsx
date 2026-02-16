type SkeletonVariant = 'text' | 'card' | 'table-row' | 'circle'

type SkeletonProps = {
  variant?: SkeletonVariant
  className?: string
  count?: number
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`skeleton animate-shimmer ${className}`} />
}

export default function Skeleton({ variant = 'text', className = '', count = 1 }: SkeletonProps) {
  const items = Array.from({ length: count })

  if (variant === 'circle') {
    return (
      <div className={`flex gap-3 ${className}`}>
        {items.map((_, i) => (
          <SkeletonBlock key={i} className="h-10 w-10 rounded-full" />
        ))}
      </div>
    )
  }

  if (variant === 'card') {
    return (
      <div className={`space-y-4 ${className}`}>
        {items.map((_, i) => (
          <div key={i} className="rounded-card border border-slate-200 dark:border-slate-700 p-5 space-y-3">
            <SkeletonBlock className="h-4 w-1/3" />
            <SkeletonBlock className="h-8 w-1/2" />
            <SkeletonBlock className="h-3 w-2/3" />
          </div>
        ))}
      </div>
    )
  }

  if (variant === 'table-row') {
    return (
      <div className={`space-y-2 ${className}`}>
        {items.map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-5 py-3">
            <SkeletonBlock className="h-4 w-16" />
            <SkeletonBlock className="h-4 w-40" />
            <SkeletonBlock className="h-4 w-20" />
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    )
  }

  // text
  return (
    <div className={`space-y-2 ${className}`}>
      {items.map((_, i) => (
        <SkeletonBlock key={i} className="h-4 w-full" />
      ))}
    </div>
  )
}
