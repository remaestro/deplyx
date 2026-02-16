import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { type ReactNode } from 'react'

type TooltipProps = {
  children: ReactNode
  content: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  delayDuration?: number
}

export function TooltipProvider({ children }: { children: ReactNode }) {
  return <TooltipPrimitive.Provider delayDuration={300}>{children}</TooltipPrimitive.Provider>
}

export default function Tooltip({ children, content, side = 'top', delayDuration }: TooltipProps) {
  return (
    <TooltipPrimitive.Root delayDuration={delayDuration}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-xs rounded-md bg-slate-800 dark:bg-slate-200 px-3 py-1.5 text-xs text-white dark:text-slate-800 shadow-lg animate-fade-in"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-slate-800 dark:fill-slate-200" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}
