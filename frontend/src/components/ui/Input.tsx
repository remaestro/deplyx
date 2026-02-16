import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, type SelectHTMLAttributes } from 'react'

const baseInput =
  'w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-400 transition-colors'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className = '', ...props }, ref) => {
    return <input ref={ref} className={`${baseInput} ${className}`} {...props} />
  },
)
Input.displayName = 'Input'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className = '', ...props }, ref) => {
    return <textarea ref={ref} className={`${baseInput} resize-none ${className}`} {...props} />
  },
)
Textarea.displayName = 'Textarea'

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <select ref={ref} className={`${baseInput} ${className}`} {...props}>
        {children}
      </select>
    )
  },
)
Select.displayName = 'Select'

export function Label({ children, className = '', htmlFor }: { children: React.ReactNode; className?: string; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className={`mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300 ${className}`}>
      {children}
    </label>
  )
}
