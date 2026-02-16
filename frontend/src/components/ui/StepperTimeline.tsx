import { Check } from 'lucide-react'

const WORKFLOW_STEPS = ['Draft', 'Pending', 'Analyzing', 'Approved', 'Executing', 'Completed']
const TERMINAL_STATES = ['Rejected', 'RolledBack']

type WorkflowStepperProps = {
  currentStatus: string
  className?: string
}

export default function WorkflowStepper({ currentStatus, className = '' }: WorkflowStepperProps) {
  const isTerminal = TERMINAL_STATES.includes(currentStatus)
  const currentIndex = WORKFLOW_STEPS.indexOf(currentStatus)

  return (
    <div className={`flex items-center gap-0 w-full ${className}`}>
      {WORKFLOW_STEPS.map((step, i) => {
        const isCompleted = !isTerminal && currentIndex > i
        const isCurrent = currentStatus === step
        const isFuture = !isTerminal && currentIndex < i
        const isRejected = isTerminal && i === Math.max(currentIndex, WORKFLOW_STEPS.indexOf('Pending'))

        return (
          <div key={step} className="flex items-center flex-1 last:flex-none">
            {/* Step circle + label */}
            <div className="flex flex-col items-center gap-1.5 relative">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-all ${
                  isCompleted
                    ? 'bg-emerald-500 text-white'
                    : isCurrent
                      ? 'bg-brand-600 text-white ring-4 ring-brand-100 dark:ring-brand-900/40 animate-status-pulse'
                      : isRejected && isTerminal
                        ? 'bg-red-500 text-white'
                        : isFuture || isTerminal
                          ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500'
                          : 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500'
                }`}
              >
                {isCompleted ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>
              <span
                className={`text-[10px] font-medium whitespace-nowrap ${
                  isCompleted
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : isCurrent
                      ? 'text-brand-600 dark:text-brand-400 font-semibold'
                      : 'text-slate-400 dark:text-slate-500'
                }`}
              >
                {step}
              </span>
            </div>

            {/* Connector line */}
            {i < WORKFLOW_STEPS.length - 1 && (
              <div className="flex-1 mx-2 mt-[-18px]">
                <div
                  className={`h-0.5 w-full rounded-full transition-colors ${
                    isCompleted
                      ? 'bg-emerald-500'
                      : 'bg-slate-200 dark:bg-slate-700'
                  }`}
                />
              </div>
            )}
          </div>
        )
      })}

      {/* Terminal state indicator */}
      {isTerminal && (
        <div className="flex flex-col items-center gap-1.5 ml-4">
          <div
            className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
              currentStatus === 'Rejected'
                ? 'bg-red-500 text-white'
                : 'bg-orange-500 text-white'
            }`}
          >
            ✕
          </div>
          <span
            className={`text-[10px] font-semibold ${
              currentStatus === 'Rejected'
                ? 'text-red-600 dark:text-red-400'
                : 'text-orange-600 dark:text-orange-400'
            }`}
          >
            {currentStatus}
          </span>
        </div>
      )}
    </div>
  )
}
