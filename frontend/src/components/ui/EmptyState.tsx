import { type ReactNode } from 'react'
import { type LucideIcon, Inbox } from 'lucide-react'

type EmptyStateProps = {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-12 px-4 ${className}`}>
      <div className="rounded-full bg-slate-100 dark:bg-surface-dark-tertiary p-4 mb-4">
        <Icon className="h-8 w-8 text-slate-400 dark:text-slate-500" />
      </div>
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-slate-500 dark:text-slate-400 text-center max-w-sm mb-4">
          {description}
        </p>
      )}
      {action}
    </div>
  )
}
