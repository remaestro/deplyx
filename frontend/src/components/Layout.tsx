import { useState, useCallback, useMemo } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  GitPullRequest,
  Network,
  Plug,
  ShieldCheck,
  FileText,
  LogOut,
  Menu,
  X,
  ChevronsLeft,
  ChevronsRight,
  Search,
  Keyboard,
  Bell,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../store/useAppStore'
import { apiClient } from '../api/client'
import { CommandPalette, ThemeToggle } from './ui'
import Tooltip from './ui/Tooltip'
import { useKeyboardShortcuts, SHORTCUTS } from '../hooks/useKeyboardShortcuts'

const operationsNav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/changes', label: 'Changes', icon: GitPullRequest },
  { to: '/graph', label: 'Topology', icon: Network },
]

const configNav = [
  { to: '/connectors', label: 'Connectors', icon: Plug },
  { to: '/policies', label: 'Policies', icon: ShieldCheck },
  { to: '/audit-log', label: 'Audit Log', icon: FileText },
]

const navItems = [...operationsNav, ...configNav]

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout, sidebarOpen, setSidebarOpen, sidebarCollapsed, setSidebarCollapsed } =
    useAppStore()
  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleShowHelp = useCallback(() => setShowShortcuts(true), [])
  useKeyboardShortcuts({ onShowHelp: handleShowHelp })

  // Pending approvals count for notification bell
  const { data: changes = [] } = useQuery<{ status: string }[]>({
    queryKey: ['changes'],
    queryFn: () => apiClient.get('/changes').then((r) => r.data),
    staleTime: 30_000,
  })
  const pendingCount = useMemo(
    () => changes.filter((c) => c.status === 'pending_approval').length,
    [changes],
  )

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const isCollapsed = sidebarCollapsed && !sidebarOpen // desktops: collapsed; mobile: use sidebarOpen

  const sidebarWidth = isCollapsed ? 'w-[64px]' : 'w-[240px]'

  return (
    <div className="flex h-screen overflow-hidden bg-surface-light dark:bg-surface-dark">
      {/* Skip navigation */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-btn focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? sidebarWidth : 'w-0 -ml-[240px]'
        } flex flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-dark-secondary transition-all duration-200 md:${sidebarWidth} md:ml-0 shrink-0`}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 border-b border-slate-200 dark:border-slate-800 px-4 py-4 h-[57px]">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 dark:bg-brand-500 shrink-0">
            <Network className="h-4 w-4 text-white" />
          </div>
          {!isCollapsed && (
            <span className="text-lg font-bold text-slate-800 dark:text-white tracking-tight">
              Deplyx
            </span>
          )}
        </div>

        {/* Environment badge */}
        {!isCollapsed && (
          <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-800">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Production
            </span>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4" aria-label="Main navigation">
          {/* Operations group */}
          <div>
            {!isCollapsed && (
              <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                Operations
              </p>
            )}
            <div className="space-y-0.5">
              {operationsNav.map((item) => (
                <NavItem
                  key={item.to}
                  item={item}
                  collapsed={isCollapsed}
                  active={
                    location.pathname === item.to ||
                    (item.to !== '/' && location.pathname.startsWith(item.to))
                  }
                />
              ))}
            </div>
          </div>

          {/* Config group */}
          <div>
            {!isCollapsed && (
              <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                Configuration
              </p>
            )}
            <div className="space-y-0.5">
              {configNav.map((item) => (
                <NavItem
                  key={item.to}
                  item={item}
                  collapsed={isCollapsed}
                  active={
                    location.pathname === item.to ||
                    (item.to !== '/' && location.pathname.startsWith(item.to))
                  }
                />
              ))}
            </div>
          </div>
        </nav>

        {/* User section */}
        <div className="border-t border-slate-200 dark:border-slate-800 px-3 py-3">
          {!isCollapsed ? (
            <>
              {/* User info */}
              <div className="flex items-center gap-2.5 mb-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-900/40 text-brand-700 dark:text-brand-300 text-xs font-bold shrink-0">
                  {user?.email?.charAt(0).toUpperCase() ?? 'U'}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-slate-700 dark:text-slate-200">
                    {user?.email}
                  </div>
                  <div className="inline-block rounded bg-brand-100 dark:bg-brand-900/30 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:text-brand-300 mt-0.5">
                    {user?.role}
                  </div>
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="flex w-full items-center gap-2 rounded-btn px-3 py-2 text-sm text-slate-500 dark:text-slate-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </>
          ) : (
            <Tooltip content="Logout" side="right">
              <button
                onClick={handleLogout}
                className="flex w-full items-center justify-center rounded-btn p-2 text-slate-500 dark:text-slate-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-colors"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </Tooltip>
          )}
        </div>

        {/* Collapse toggle (desktop only) */}
        <div className="hidden md:flex border-t border-slate-200 dark:border-slate-800 px-3 py-2">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="flex w-full items-center justify-center rounded-btn p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            {isCollapsed ? (
              <ChevronsRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header bar */}
        <header className="flex items-center gap-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-dark-secondary px-4 py-3 md:px-6 h-[57px] shrink-0">
          {/* Mobile hamburger */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
            className="rounded p-1 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary md:hidden"
          >
            {sidebarOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
          </button>

          {/* Page title */}
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
            {navItems.find(
              (i) =>
                i.to === location.pathname ||
                (i.to !== '/' && location.pathname.startsWith(i.to)),
            )?.label ?? 'Deplyx'}
          </h2>

          <div className="flex-1" />

          {/* Notification bell */}
          <Tooltip content={pendingCount > 0 ? `${pendingCount} pending approvals` : 'No pending approvals'}>
            <button
              onClick={() => useAppStore.getState().toggleCommandPalette()}
              className="relative rounded p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              aria-label={`Notifications${pendingCount > 0 ? `, ${pendingCount} pending` : ''}`}
            >
              <Bell className="h-4 w-4" aria-hidden="true" />
              {pendingCount > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
                  {pendingCount > 9 ? '9+' : pendingCount}
                </span>
              )}
            </button>
          </Tooltip>

          {/* Search trigger */}
          <button
            onClick={() => useAppStore.getState().toggleCommandPalette()}
            className="hidden sm:flex items-center gap-2 rounded-btn border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-surface-dark-tertiary px-3 py-1.5 text-sm text-slate-400 dark:text-slate-500 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
          >
            <Search className="h-3.5 w-3.5" />
            <span>Search...</span>
            <kbd className="ml-4 rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-1.5 py-0.5 text-[10px] font-medium text-slate-400 dark:text-slate-500">
              ⌘K
            </kbd>
          </button>

          {/* Theme toggle */}
          <ThemeToggle />

          {/* Shortcuts help trigger */}
          <Tooltip content="Keyboard shortcuts (?)">
            <button
              onClick={() => setShowShortcuts(true)}
              className="rounded p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            >
              <Keyboard className="h-4 w-4" />
            </button>
          </Tooltip>
        </header>

        {/* Page content with enter animation */}
        <main id="main-content" className="flex-1 overflow-y-auto p-4 md:p-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              className="h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Keyboard shortcuts help dialog */}
      <AnimatePresence>
        {showShortcuts && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[60] bg-black"
              onClick={() => setShowShortcuts(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="shortcuts-title"
              className="fixed left-1/2 top-1/2 z-[61] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-5 shadow-2xl"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 id="shortcuts-title" className="text-sm font-semibold text-slate-800 dark:text-slate-100">Keyboard Shortcuts</h3>
                <button onClick={() => setShowShortcuts(false)} aria-label="Close shortcuts help" className="rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-2">
                {SHORTCUTS.map((s) => (
                  <div key={s.description} className="flex items-center justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-300">{s.description}</span>
                    <div className="flex items-center gap-1">
                      {s.keys.map((k) => (
                        <kbd
                          key={k}
                          className="inline-flex h-6 min-w-[24px] items-center justify-center rounded border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-800 px-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400"
                        >
                          {k}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Command palette overlay */}
      <CommandPalette />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Nav item with collapsed tooltip support                           */
/* ------------------------------------------------------------------ */
function NavItem({
  item,
  collapsed,
  active,
}: {
  item: { to: string; label: string; icon: React.ComponentType<{ className?: string }> }
  collapsed: boolean
  active: boolean
}) {
  const link = (
    <Link
      to={item.to}
      className={`relative flex items-center gap-3 rounded-btn px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'
          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary hover:text-slate-900 dark:hover:text-slate-200'
      } ${collapsed ? 'justify-center' : ''}`}
    >
      {/* Active indicator bar */}
      {active && (
        <motion.div
          layoutId="nav-active"
          className="absolute left-0 top-1 bottom-1 w-[3px] rounded-full bg-brand-600 dark:bg-brand-400"
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        />
      )}
      <item.icon className="h-4 w-4 shrink-0" />
      {!collapsed && item.label}
    </Link>
  )

  if (collapsed) {
    return (
      <Tooltip content={item.label} side="right">
        {link}
      </Tooltip>
    )
  }

  return link
}
