import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, CheckCircle, AlertTriangle, Info, AlertCircle } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

type Toast = {
  id: number
  type: ToastType
  title: string
  description?: string
}

type ToastContextValue = {
  toast: (type: ToastType, title: string, description?: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let toastId = 0

const icons: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const iconColors: Record<ToastType, string> = {
  success: 'text-emerald-500',
  error: 'text-red-500',
  warning: 'text-amber-500',
  info: 'text-blue-500',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, title: string, description?: string) => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, type, title, description }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      {/* Toast container */}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none" role="status" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => {
            const Icon = icons[t.type]
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, x: 80, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 80, scale: 0.95 }}
                transition={{ duration: 0.2 }}
                className="pointer-events-auto flex items-start gap-3 rounded-card border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary shadow-lg px-4 py-3 min-w-[320px] max-w-[420px]"
              >
                <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${iconColors[t.type]}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{t.title}</p>
                  {t.description && (
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{t.description}</p>
                  )}
                </div>
                <button
                  onClick={() => removeToast(t.id)}
                  aria-label="Dismiss notification"
                  className="shrink-0 rounded p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
