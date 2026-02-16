import * as TabsPrimitive from '@radix-ui/react-tabs'
import { type ReactNode } from 'react'

type TabsProps = {
  defaultValue: string
  children: ReactNode
  className?: string
}

export function Tabs({ defaultValue, children, className = '' }: TabsProps) {
  return (
    <TabsPrimitive.Root defaultValue={defaultValue} className={className}>
      {children}
    </TabsPrimitive.Root>
  )
}

export function TabList({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List
      className={`flex gap-1 border-b border-slate-200 dark:border-slate-700 px-1 ${className}`}
    >
      {children}
    </TabsPrimitive.List>
  )
}

export function Tab({ value, children }: { value: string; children: ReactNode }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="relative px-3 py-2 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors data-[state=active]:text-brand-600 dark:data-[state=active]:text-brand-400 focus-ring rounded-t-md outline-none after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:rounded-t after:bg-transparent data-[state=active]:after:bg-brand-600 dark:data-[state=active]:after:bg-brand-400"
    >
      {children}
    </TabsPrimitive.Trigger>
  )
}

export function TabPanel({ value, children, className = '' }: { value: string; children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.Content
      value={value}
      className={`animate-fade-in pt-4 outline-none ${className}`}
    >
      {children}
    </TabsPrimitive.Content>
  )
}
