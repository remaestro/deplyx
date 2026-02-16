import { Command } from 'cmdk'
import { useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  LayoutDashboard,
  GitPullRequest,
  Network,
  Plug,
  ShieldCheck,
  FileText,
  Search,
  Plus,
} from 'lucide-react'
import { useAppStore } from '../../store/useAppStore'

const PAGES = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard, keywords: 'home overview kpis' },
  { name: 'Changes', path: '/changes', icon: GitPullRequest, keywords: 'change request cr firewall' },
  { name: 'Topology', path: '/graph', icon: Network, keywords: 'graph network map nodes' },
  { name: 'Connectors', path: '/connectors', icon: Plug, keywords: 'connector sync paloalto cisco' },
  { name: 'Policies', path: '/policies', icon: ShieldCheck, keywords: 'policy rule guard' },
  { name: 'Audit Log', path: '/audit-log', icon: FileText, keywords: 'audit log trail history' },
]

const ACTIONS = [
  { name: 'Create New Change', path: '/changes', icon: Plus, keywords: 'new create add change' },
]

export default function CommandPalette() {
  const navigate = useNavigate()
  const { commandPaletteOpen, toggleCommandPalette } = useAppStore()

  const handleSelect = useCallback(
    (path: string) => {
      navigate(path)
      toggleCommandPalette()
    },
    [navigate, toggleCommandPalette],
  )

  // Cmd+K shortcut
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        toggleCommandPalette()
      }
      if (e.key === 'Escape' && commandPaletteOpen) {
        toggleCommandPalette()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [commandPaletteOpen, toggleCommandPalette])

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.1 }}
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
            onClick={toggleCommandPalette}
          />

          {/* Command dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.15 }}
            className="fixed left-1/2 top-[20%] z-50 w-full max-w-lg -translate-x-1/2"
          >
            <Command
              label="Command Palette"
              className="rounded-card border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary shadow-2xl overflow-hidden"
            >
              <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-700 px-4">
                <Search className="h-4 w-4 text-slate-400 shrink-0" />
                <Command.Input
                  placeholder="Search pages, changes, devices..."
                  className="flex-1 bg-transparent py-3 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none"
                />
                <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:text-slate-400">
                  ESC
                </kbd>
              </div>

              <Command.List className="max-h-80 overflow-y-auto p-2">
                <Command.Empty className="py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                  No results found.
                </Command.Empty>

                <Command.Group heading="Pages" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-slate-400 dark:[&_[cmdk-group-heading]]:text-slate-500">
                  {PAGES.map((page) => (
                    <Command.Item
                      key={page.path}
                      value={`${page.name} ${page.keywords}`}
                      onSelect={() => handleSelect(page.path)}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-700 dark:text-slate-200 cursor-pointer aria-selected:bg-brand-50 dark:aria-selected:bg-brand-900/20 aria-selected:text-brand-700 dark:aria-selected:text-brand-300 transition-colors"
                    >
                      <page.icon className="h-4 w-4 shrink-0" />
                      {page.name}
                    </Command.Item>
                  ))}
                </Command.Group>

                <Command.Separator className="my-1 h-px bg-slate-200 dark:bg-slate-700" />

                <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-slate-400 dark:[&_[cmdk-group-heading]]:text-slate-500">
                  {ACTIONS.map((action) => (
                    <Command.Item
                      key={action.name}
                      value={`${action.name} ${action.keywords}`}
                      onSelect={() => handleSelect(action.path)}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-700 dark:text-slate-200 cursor-pointer aria-selected:bg-brand-50 dark:aria-selected:bg-brand-900/20 aria-selected:text-brand-700 dark:aria-selected:text-brand-300 transition-colors"
                    >
                      <action.icon className="h-4 w-4 shrink-0" />
                      {action.name}
                    </Command.Item>
                  ))}
                </Command.Group>
              </Command.List>

              <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-2 flex items-center gap-4 text-[10px] text-slate-400 dark:text-slate-500">
                <span>
                  <kbd className="font-mono">↑↓</kbd> navigate
                </span>
                <span>
                  <kbd className="font-mono">↵</kbd> select
                </span>
                <span>
                  <kbd className="font-mono">esc</kbd> close
                </span>
              </div>
            </Command>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
