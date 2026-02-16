import { type ReactNode } from 'react'

type CardProps = {
  children: ReactNode
  className?: string
  hover?: boolean
}

export default function Card({ children, className = '', hover }: CardProps) {
  return (
    <div
      className={`rounded-card border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary shadow-card dark:shadow-card-dark ${
        hover ? 'transition-all hover:shadow-card-hover dark:hover:shadow-card-dark-hover hover:-translate-y-0.5' : ''
      } ${className}`}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  action,
  className = '',
}: {
  title: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-5 py-4 ${className}`}
    >
      <h3 className="font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
      {action}
    </div>
  )
}

export function CardContent({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`p-5 ${className}`}>{children}</div>
}
