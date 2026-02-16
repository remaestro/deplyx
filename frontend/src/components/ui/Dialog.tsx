import * as DialogPrimitive from '@radix-ui/react-dialog'
import { AnimatePresence, motion } from 'framer-motion'
import { X, AlertTriangle } from 'lucide-react'
import Button from './Button'

type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'warning'
  onConfirm: () => void
  loading?: boolean
}

export default function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  onConfirm,
  loading,
}: ConfirmDialogProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
              />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content asChild>
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 8 }}
                transition={{ duration: 0.15 }}
                className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-card border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-6 shadow-xl"
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`rounded-full p-2 ${
                      variant === 'danger'
                        ? 'bg-red-100 dark:bg-red-900/30'
                        : 'bg-amber-100 dark:bg-amber-900/30'
                    }`}
                  >
                    <AlertTriangle
                      className={`h-5 w-5 ${
                        variant === 'danger' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'
                      }`}
                    />
                  </div>
                  <div className="flex-1">
                    <DialogPrimitive.Title className="text-base font-semibold text-slate-800 dark:text-slate-100">
                      {title}
                    </DialogPrimitive.Title>
                    <DialogPrimitive.Description className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                      {description}
                    </DialogPrimitive.Description>
                  </div>
                  <DialogPrimitive.Close asChild>
                    <button className="rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" aria-label="Close dialog">
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </DialogPrimitive.Close>
                </div>
                <div className="mt-6 flex justify-end gap-3">
                  <DialogPrimitive.Close asChild>
                    <Button variant="secondary" size="sm">
                      {cancelLabel}
                    </Button>
                  </DialogPrimitive.Close>
                  <Button
                    variant={variant === 'danger' ? 'danger' : 'warning'}
                    size="sm"
                    onClick={onConfirm}
                    loading={loading}
                  >
                    {confirmLabel}
                  </Button>
                </div>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  )
}
