import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  Plus,
  Filter,
  GitPullRequest,
  Search,
  X,
  List,
  LayoutGrid,
  Columns3,
  CheckSquare,
  Check,
  Trash2,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { formatDistanceToNow } from 'date-fns'
import { apiClient } from '../api/client'
import {
  Button,
  Card,
  CardContent,
  StatusBadge,
  RiskBadge,
  Skeleton,
  EmptyState,
  Input,
  Textarea,
  Select,
  Label,
  Badge,
} from '../components/ui'

type ChangeItem = {
  id: string
  title: string
  change_type: string
  environment: string
  status: string
  risk_level: string | null
  risk_score: number | null
  created_at: string
}

type ViewMode = 'table' | 'card' | 'kanban'

const RISK_BORDER: Record<string, string> = {
  low: 'border-l-emerald-500',
  medium: 'border-l-amber-500',
  high: 'border-l-red-500',
  critical: 'border-l-red-700',
}

const STATUS_COLORS: Record<string, string> = {
  Draft: '#94a3b8',
  Pending: '#f59e0b',
  Analyzing: '#3b82f6',
  Approved: '#22c55e',
  Executing: '#8b5cf6',
  Completed: '#22c55e',
  Rejected: '#ef4444',
  RolledBack: '#ec4899',
}

const fadeUp = {
  hidden: { opacity: 0, y: 6 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.03, duration: 0.2, ease: 'easeOut' as const },
  }),
}

export default function ChangesPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('')
  const [envFilter, setEnvFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('table')
  const [showDrawer, setShowDrawer] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [createError, setCreateError] = useState<string | null>(null)

  const parseApiError = (err: unknown): string => {
    const payload = (err as { response?: { data?: unknown } })?.response?.data
    if (!payload) return 'Request failed'
    if (typeof payload === 'string') return payload

    const detail = (payload as { detail?: unknown })?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      const message = (detail as { message?: unknown })?.message
      const reasons = (detail as { reasons?: unknown })?.reasons
      if (typeof message === 'string' && Array.isArray(reasons) && reasons.length > 0) {
        return `${message}: ${reasons.filter((r) => typeof r === 'string').join(' | ')}`
      }
      if (typeof message === 'string') return message
    }
    return 'Request failed'
  }

  const params = new URLSearchParams()
  if (statusFilter) params.set('status', statusFilter)
  if (envFilter) params.set('env', envFilter)

  const { data: changes = [], isLoading } = useQuery<ChangeItem[]>({
    queryKey: ['changes', statusFilter, envFilter],
    queryFn: () => apiClient.get(`/changes?${params}`).then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => apiClient.post('/changes', body),
    onMutate: () => setCreateError(null),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['changes'] })
      setShowDrawer(false)
      navigate(`/changes/${res.data.id}`)
    },
    onError: (err) => setCreateError(parseApiError(err)),
  })

  /* ---------- Client-side search filter ---------- */
  const filteredChanges = useMemo(() => {
    if (!searchQuery.trim()) return changes
    const q = searchQuery.toLowerCase()
    return changes.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        c.change_type.toLowerCase().includes(q),
    )
  }, [changes, searchQuery])

  /* ---------- Active filter chips ---------- */
  const activeFilters: { label: string; clear: () => void }[] = []
  if (statusFilter)
    activeFilters.push({ label: `Status: ${statusFilter}`, clear: () => setStatusFilter('') })
  if (envFilter) activeFilters.push({ label: `Env: ${envFilter}`, clear: () => setEnvFilter('') })
  if (searchQuery)
    activeFilters.push({ label: `Search: "${searchQuery}"`, clear: () => setSearchQuery('') })

  /* ---------- Selection helpers ---------- */
  const toggleSelect = useCallback(
    (id: string) =>
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.has(id) ? next.delete(id) : next.add(id)
        return next
      }),
    [],
  )
  const selectAll = useCallback(
    () => setSelectedIds(new Set(filteredChanges.map((c) => c.id))),
    [filteredChanges],
  )
  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  /* ---------- Kanban columns ---------- */
  const kanbanColumns = useMemo(() => {
    const cols: Record<string, ChangeItem[]> = {
      Draft: [],
      Pending: [],
      Approved: [],
      Executing: [],
      Completed: [],
    }
    filteredChanges.forEach((c) => {
      if (cols[c.status]) cols[c.status].push(c)
      else cols[c.status] = [c]
    })
    return cols
  }, [filteredChanges])

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setShowDrawer(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          New Change
        </Button>

        {/* Search bar */}
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search changes…"
            className="w-full rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary pl-8 pr-3 py-1.5 text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus-ring"
          />
        </div>

        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <Filter className="h-4 w-4" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-2.5 py-1.5 text-sm text-slate-700 dark:text-slate-200 focus-ring"
          >
            <option value="">All Statuses</option>
            <option value="Draft">Draft</option>
            <option value="Pending">Pending</option>
            <option value="Analyzing">Analyzing</option>
            <option value="Approved">Approved</option>
            <option value="Executing">Executing</option>
            <option value="Completed">Completed</option>
            <option value="Rejected">Rejected</option>
            <option value="RolledBack">Rolled Back</option>
          </select>
          <select
            value={envFilter}
            onChange={(e) => setEnvFilter(e.target.value)}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-2.5 py-1.5 text-sm text-slate-700 dark:text-slate-200 focus-ring"
          >
            <option value="">All Environments</option>
            <option value="prod">prod</option>
            <option value="pre-prod">pre-prod</option>
            <option value="Prod">Prod</option>
            <option value="Preprod">Preprod</option>
            <option value="DC1">DC1</option>
            <option value="DC2">DC2</option>
          </select>
        </div>

        {/* View toggle */}
        <div className="ml-auto flex items-center gap-0.5 rounded-md border border-slate-200 dark:border-slate-700 p-0.5">
          {([
            { mode: 'table' as ViewMode, icon: List, label: 'Table' },
            { mode: 'card' as ViewMode, icon: LayoutGrid, label: 'Card' },
            { mode: 'kanban' as ViewMode, icon: Columns3, label: 'Kanban' },
          ] as const).map(({ mode, icon: Icon, label }) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              aria-label={`${label} view`}
              className={`rounded p-1.5 transition-colors ${
                viewMode === mode
                  ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400'
                  : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
              }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>
      </div>

      {/* Filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {activeFilters.map((f) => (
            <button
              key={f.label}
              onClick={f.clear}
              className="inline-flex items-center gap-1 rounded-full bg-brand-50 dark:bg-brand-900/20 px-2.5 py-0.5 text-xs font-medium text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-900/30 transition-colors"
            >
              {f.label}
              <X className="h-3 w-3" />
            </button>
          ))}
          <button
            onClick={() => {
              setStatusFilter('')
              setEnvFilter('')
              setSearchQuery('')
            }}
            className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Bulk actions bar */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-3 rounded-lg border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-900/20 px-4 py-2"
          >
            <span className="text-sm font-medium text-brand-700 dark:text-brand-300">
              {selectedIds.size} selected
            </span>
            <button
              onClick={selectAll}
              className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
            >
              Select all
            </button>
            <button
              onClick={clearSelection}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              Clear
            </button>
            <div className="ml-auto flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={clearSelection}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Cancel
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Content */}
      <AnimatePresence mode="wait">
        {isLoading ? (
          <Card>
            <CardContent>
              <div className="space-y-3 py-4">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} variant="table-row" />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : filteredChanges.length === 0 ? (
          <Card>
            <CardContent>
              <EmptyState
                icon={GitPullRequest}
                title="No changes found"
                description="Adjust your filters or create a new change request."
              />
            </CardContent>
          </Card>
        ) : viewMode === 'table' ? (
          /* ---------- TABLE VIEW ---------- */
          <motion.div key="table" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <Card>
              <CardContent>
                <div className="overflow-x-auto -mx-5">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-700/60 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                        <th className="px-5 py-3 w-8">
                          <input
                            type="checkbox"
                            checked={selectedIds.size === filteredChanges.length && filteredChanges.length > 0}
                            onChange={() =>
                              selectedIds.size === filteredChanges.length ? clearSelection() : selectAll()
                            }
                            className="rounded border-slate-300 dark:border-slate-600"
                          />
                        </th>
                        <th className="px-5 py-3">ID</th>
                        <th className="px-5 py-3">Title</th>
                        <th className="px-5 py-3">Type</th>
                        <th className="px-5 py-3">Env</th>
                        <th className="px-5 py-3">Status</th>
                        <th className="px-5 py-3">Risk</th>
                        <th className="px-5 py-3">Score</th>
                        <th className="px-5 py-3">Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredChanges.map((c, i) => (
                        <motion.tr
                          key={c.id}
                          custom={i}
                          initial="hidden"
                          animate="visible"
                          variants={fadeUp}
                          className={`border-b border-slate-50 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-surface-dark-tertiary cursor-pointer transition-colors border-l-2 ${RISK_BORDER[c.risk_level ?? ''] ?? 'border-l-transparent'}`}
                          onClick={() => navigate(`/changes/${c.id}`)}
                        >
                          <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={selectedIds.has(c.id)}
                              onChange={() => toggleSelect(c.id)}
                              className="rounded border-slate-300 dark:border-slate-600"
                            />
                          </td>
                          <td className="px-5 py-3 text-slate-400 dark:text-slate-500 font-mono text-xs">
                            #{c.id}
                          </td>
                          <td className="px-5 py-3">
                            <Link
                              to={`/changes/${c.id}`}
                              className="font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {c.title}
                            </Link>
                          </td>
                          <td className="px-5 py-3 text-slate-600 dark:text-slate-400">{c.change_type}</td>
                          <td className="px-5 py-3 text-slate-600 dark:text-slate-400">{c.environment}</td>
                          <td className="px-5 py-3">
                            <StatusBadge status={c.status} />
                          </td>
                          <td className="px-5 py-3">
                            <RiskBadge level={c.risk_level} />
                          </td>
                          <td className="px-5 py-3 text-slate-600 dark:text-slate-400 font-mono text-xs">
                            {c.risk_score ?? '—'}
                          </td>
                          <td className="px-5 py-3 text-xs text-slate-400">
                            {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : viewMode === 'card' ? (
          /* ---------- CARD VIEW ---------- */
          <motion.div
            key="card"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            {filteredChanges.map((c, i) => (
              <motion.div key={c.id} custom={i} initial="hidden" animate="visible" variants={fadeUp}>
                <Link to={`/changes/${c.id}`} className="block">
                  <Card
                    hover
                    className={`border-l-2 ${RISK_BORDER[c.risk_level ?? ''] ?? 'border-l-transparent'}`}
                  >
                    <CardContent>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs text-slate-400">#{c.id}</span>
                          <StatusBadge status={c.status} />
                        </div>
                        <p className="font-medium text-slate-700 dark:text-slate-200 line-clamp-2">
                          {c.title}
                        </p>
                        <div className="flex items-center gap-2">
                          <RiskBadge level={c.risk_level} />
                          <Badge color="neutral">{c.environment}</Badge>
                          <span className="ml-auto text-[10px] text-slate-400">
                            {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                          </span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </motion.div>
        ) : (
          /* ---------- KANBAN VIEW ---------- */
          <motion.div
            key="kanban"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-2 lg:grid-cols-5 gap-3"
          >
            {Object.entries(kanbanColumns).map(([status, items]) => (
              <div key={status} className="space-y-2 min-w-0">
                <div className="flex items-center gap-2 px-1">
                  <span
                    className="h-2 w-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: STATUS_COLORS[status] ?? '#6366f1' }}
                  />
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 truncate">
                    {status}
                  </span>
                  <Badge color="neutral" className="text-[10px] px-1.5 py-0">
                    {items.length}
                  </Badge>
                </div>
                <div className="space-y-2">
                  {items.map((c, i) => (
                    <motion.div key={c.id} custom={i} initial="hidden" animate="visible" variants={fadeUp}>
                      <Link to={`/changes/${c.id}`} className="block">
                        <div
                          className={`rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-3 hover:shadow-md dark:hover:border-slate-600 transition-all border-l-2 ${RISK_BORDER[c.risk_level ?? ''] ?? 'border-l-transparent'}`}
                        >
                          <p className="text-sm font-medium text-slate-700 dark:text-slate-200 line-clamp-2">
                            {c.title}
                          </p>
                          <div className="mt-2 flex items-center gap-2">
                            <RiskBadge level={c.risk_level} />
                            <span className="text-[10px] text-slate-400">{c.environment}</span>
                          </div>
                          <p className="mt-1 text-[10px] text-slate-400">
                            {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                          </p>
                        </div>
                      </Link>
                    </motion.div>
                  ))}
                  {items.length === 0 && (
                    <p className="px-1 text-xs text-slate-400 italic">No items</p>
                  )}
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Slide-in Drawer for Create */}
      <AnimatePresence>
        {showDrawer && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => setShowDrawer(false)}
            />
            {/* Drawer */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto bg-white dark:bg-surface-dark-secondary border-l border-slate-200 dark:border-slate-700 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-white">
                  Create Change Request
                </h2>
                <button
                  onClick={() => setShowDrawer(false)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6">
                <CreateChangeWizard
                  onSubmit={(b) => createMut.mutate(b)}
                  loading={createMut.isPending}
                  error={createError}
                />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ---------- Multi-step Create Wizard ---------- */
function CreateChangeWizard({
  onSubmit,
  loading,
  error,
}: {
  onSubmit: (b: Record<string, unknown>) => void
  loading: boolean
  error: string | null
}) {
  const [step, setStep] = useState(0)
  const [title, setTitle] = useState('')
  const [changeType, setChangeType] = useState('Preventive')
  const [action, setAction] = useState('')
  const [env, setEnv] = useState('prod')
  const [desc, setDesc] = useState('')
  const [executionPlan, setExecutionPlan] = useState('')
  const [rollbackPlan, setRollbackPlan] = useState('')
  const [mwStart, setMwStart] = useState('')
  const [mwEnd, setMwEnd] = useState('')
  const [targetNodeIds, setTargetNodeIds] = useState<string[]>([])
  const [targetComponentType, setTargetComponentType] = useState('all')
  const [componentSearch, setComponentSearch] = useState('')
  const [componentDropdownOpen, setComponentDropdownOpen] = useState(false)
  const componentDropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (componentDropdownRef.current && !componentDropdownRef.current.contains(e.target as Node)) {
        setComponentDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Human-readable labels for device types synced from lab machines
  const TYPE_LABELS: Record<string, string> = {
    firewall: 'Firewall',
    router: 'Router',
    switch: 'Switch',
    wlc: 'Wireless Controller',
    access_point: 'Access Point',
    vpn_gateway: 'VPN Gateway',
    ids: 'IDS / IPS',
    directory: 'Directory Service',
    reverse_proxy: 'Reverse Proxy / Load Balancer',
    database: 'Database',
    cache: 'Cache',
    search_engine: 'Search Engine',
    monitoring: 'Monitoring / Dashboards',
    metrics: 'Metrics',
  }

  const ALL_ACTION_OPTIONS = [
    // Firewall
    { value: 'add_rule', label: 'Add Rule', types: ['firewall'] },
    { value: 'remove_rule', label: 'Remove Rule', types: ['firewall'] },
    { value: 'modify_rule', label: 'Modify Rule', types: ['firewall'] },
    { value: 'disable_rule', label: 'Disable Rule', types: ['firewall'] },
    { value: 'modify_sg', label: 'Modify Security Group', types: ['firewall'] },
    { value: 'delete_sg', label: 'Delete Security Group', types: ['firewall'] },
    // Switch
    { value: 'change_vlan', label: 'Change VLAN Assignment', types: ['switch'] },
    { value: 'delete_vlan', label: 'Delete VLAN', types: ['switch'] },
    { value: 'modify_vlan', label: 'Modify VLAN', types: ['switch'] },
    // Switch / Router / WLC
    { value: 'disable_port', label: 'Disable Port', types: ['switch', 'router', 'wlc'] },
    { value: 'enable_port', label: 'Enable Port', types: ['switch', 'router', 'wlc'] },
    { value: 'shutdown_interface', label: 'Shutdown Interface', types: ['switch', 'router', 'wlc'] },
    // Router / VPN
    { value: 'modify_routing', label: 'Modify Routing', types: ['router', 'vpn_gateway'] },
    { value: 'modify_acl', label: 'Modify ACL', types: ['router', 'firewall'] },
    // Wireless
    { value: 'modify_ssid', label: 'Modify SSID', types: ['wlc', 'access_point'] },
    { value: 'disable_ssid', label: 'Disable SSID', types: ['wlc', 'access_point'] },
    // Security
    { value: 'update_signatures', label: 'Update Signatures', types: ['ids'] },
    { value: 'modify_vpn_tunnel', label: 'Modify VPN Tunnel', types: ['vpn_gateway'] },
    { value: 'modify_policy', label: 'Modify Policy', types: ['directory', 'ids'] },
    // Application
    { value: 'modify_config', label: 'Modify Configuration', types: ['reverse_proxy', 'database', 'cache', 'search_engine', 'monitoring', 'metrics'] },
    { value: 'restart_service', label: 'Restart Service', types: ['reverse_proxy', 'database', 'cache', 'search_engine', 'monitoring', 'metrics', 'directory'] },
    { value: 'scale_service', label: 'Scale Service', types: ['reverse_proxy', 'database', 'cache', 'search_engine'] },
    { value: 'rotate_credentials', label: 'Rotate Credentials', types: ['database', 'cache', 'directory', 'monitoring'] },
    // Universal
    { value: 'config_change', label: 'Config Change', types: [] },
    { value: 'firmware_upgrade', label: 'Firmware Upgrade', types: [] },
    { value: 'reboot_device', label: 'Reboot Device', types: [] },
    { value: 'decommission', label: 'Decommission', types: [] },
  ]

  const { data: graphDevices = [] } = useQuery<Record<string, unknown>[]>({
    queryKey: ['change-wizard-graph-devices'],
    queryFn: () => apiClient.get('/graph/devices').then((r) => r.data),
    staleTime: 15_000,
  })

  const deviceOptions = useMemo(() => {
    return graphDevices
      .map((item) => {
        // API returns flat objects: { id, type, vendor, hostname, display_name, ... }
        const id = typeof item.id === 'string' ? item.id : String(item.id ?? '')
        const displayName =
          (typeof item.display_name === 'string' && item.display_name.trim()) ||
          (typeof item.name === 'string' && (item.name as string).trim()) ||
          (typeof item.hostname === 'string' && (item.hostname as string).trim()) ||
          id
        const type = typeof item.type === 'string' ? item.type : 'unknown'
        const vendor = typeof item.vendor === 'string' ? item.vendor : ''
        return { id, name: displayName, type, vendor }
      })
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [graphDevices])

  const componentTypes = useMemo(
    () =>
      Array.from(new Set(deviceOptions.map((d) => d.type)))
        .filter((t) => t !== 'unknown')
        .sort((a, b) => (TYPE_LABELS[a] ?? a).localeCompare(TYPE_LABELS[b] ?? b)),
    [deviceOptions],
  )

  const filteredDeviceOptions = useMemo(() => {
    if (targetComponentType === 'all') return deviceOptions
    return deviceOptions.filter((device) => device.type === targetComponentType)
  }, [deviceOptions, targetComponentType])

  // Filter actions based on selected component type
  const filteredActionOptions = useMemo(() => {
    if (targetComponentType === 'all') return ALL_ACTION_OPTIONS
    const normalizedType = targetComponentType.toLowerCase()
    return ALL_ACTION_OPTIONS.filter(
      (a) => a.types.length === 0 || a.types.includes(normalizedType),
    )
  }, [targetComponentType])

  // Reset action when component type changes and current action is no longer valid
  useEffect(() => {
    if (action && !filteredActionOptions.find((a) => a.value === action)) {
      setAction('')
    }
  }, [filteredActionOptions, action])

  const steps = ['Basics', 'Plans', 'Window']
  const canNext =
    step === 0
      ? title.trim() !== '' && desc.trim() !== '' && action !== '' && targetNodeIds.length > 0
      : step === 1
        ? executionPlan.trim() !== '' && rollbackPlan.trim() !== ''
        : mwStart !== '' && mwEnd !== ''

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {steps.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <button
              onClick={() => i < step && setStep(i)}
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                i === step
                  ? 'bg-brand-600 text-white'
                  : i < step
                    ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400 cursor-pointer'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-400'
              }`}
            >
              {i + 1}
            </button>
            <span
              className={`text-xs font-medium ${
                i === step ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400'
              }`}
            >
              {s}
            </span>
            {i < steps.length - 1 && <div className="mx-1 h-px w-6 bg-slate-200 dark:bg-slate-700" />}
          </div>
        ))}
      </div>

      {error && (
        <div className="rounded-btn border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.div
            key="step0"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-4"
          >
            <div>
              <Label>Title</Label>
              <Input placeholder="Change title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label>Change Type</Label>
                <Select value={changeType} onChange={(e) => setChangeType(e.target.value)}>
                  <option value="Preventive">Preventive</option>
                  <option value="Evolution">Evolution</option>
                  <option value="Corrective">Corrective</option>
                </Select>
              </div>
              <div>
                <Label>Environment</Label>
                <Select value={env} onChange={(e) => setEnv(e.target.value)}>
                  <option value="prod">prod</option>
                  <option value="pre-prod">pre-prod</option>
                </Select>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label>Target Component Type</Label>
                <Select value={targetComponentType} onChange={(e) => { setTargetComponentType(e.target.value); setTargetNodeIds([]) }}>
                  <option value="all">All types</option>
                  {componentTypes.map((type) => (
                    <option key={type} value={type}>{TYPE_LABELS[type] ?? type}</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>Target Components</Label>
                <div ref={componentDropdownRef} className="relative">
                  {/* Trigger */}
                  <button
                    type="button"
                    onClick={() => setComponentDropdownOpen((o) => !o)}
                    className="flex w-full items-center justify-between rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-400 transition-colors"
                  >
                    <span className="truncate">
                      {targetNodeIds.length === 0
                        ? 'Select components…'
                        : `${targetNodeIds.length} selected`}
                    </span>
                    <ChevronDown className={`ml-2 h-4 w-4 shrink-0 text-slate-400 transition-transform ${componentDropdownOpen ? 'rotate-180' : ''}`} />
                  </button>

                  {/* Selected chips */}
                  {targetNodeIds.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {targetNodeIds.slice(0, 3).map((id) => {
                        const dev = filteredDeviceOptions.find((d) => d.id === id) ?? deviceOptions.find((d) => d.id === id)
                        return (
                          <span
                            key={id}
                            className="inline-flex items-center gap-1 rounded-full bg-brand-100 dark:bg-brand-900/30 px-2 py-0.5 text-xs font-medium text-brand-700 dark:text-brand-300"
                          >
                            {dev?.name ?? id}
                            <button
                              type="button"
                              onClick={() => setTargetNodeIds((prev) => prev.filter((n) => n !== id))}
                              className="ml-0.5 hover:text-brand-900 dark:hover:text-brand-100"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </span>
                        )
                      })}
                      {targetNodeIds.length > 3 && (
                        <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-700 px-2 py-0.5 text-xs text-slate-500 dark:text-slate-400">
                          +{targetNodeIds.length - 3} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Dropdown */}
                  {componentDropdownOpen && (
                    <div className="absolute z-30 mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary shadow-lg">
                      <div className="border-b border-slate-200 dark:border-slate-700 px-2 py-1.5">
                        <div className="flex items-center gap-2">
                          <Search className="h-4 w-4 text-slate-400" />
                          <input
                            autoFocus
                            value={componentSearch}
                            onChange={(e) => setComponentSearch(e.target.value)}
                            placeholder="Search components…"
                            className="w-full bg-transparent text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none"
                          />
                          {componentSearch && (
                            <button type="button" onClick={() => setComponentSearch('')} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                              <X className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                      <ul className="max-h-48 overflow-y-auto py-1">
                        {filteredDeviceOptions
                          .filter((d) => d.name.toLowerCase().includes(componentSearch.toLowerCase()))
                          .map((device) => {
                            const isSelected = targetNodeIds.includes(device.id)
                            return (
                              <li
                                key={device.id}
                                onClick={() => {
                                  setTargetNodeIds((prev) =>
                                    isSelected ? prev.filter((n) => n !== device.id) : [...prev, device.id],
                                  )
                                }}
                                className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/50 ${
                                  isSelected ? 'text-brand-600 dark:text-brand-400 font-medium' : 'text-slate-700 dark:text-slate-200'
                                }`}
                              >
                                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                                  isSelected
                                    ? 'border-brand-500 bg-brand-500 text-white'
                                    : 'border-slate-300 dark:border-slate-600'
                                }`}>
                                  {isSelected && <Check className="h-3 w-3" />}
                                </span>
                                <span className="truncate">{device.name}</span>
                              </li>
                            )
                          })}
                        {filteredDeviceOptions.filter((d) => d.name.toLowerCase().includes(componentSearch.toLowerCase())).length === 0 && (
                          <li className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">No components found</li>
                        )}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div>
              <Label>Action</Label>
              <Select value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="">Select an action…</option>
                {filteredActionOptions.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </Select>
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                The action determines how impact analysis traces affected components
              </p>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea
                placeholder="Describe this change in natural language"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                rows={3}
              />
            </div>
          </motion.div>
        )}
        {step === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-4"
          >
            <div>
              <Label>Execution Plan</Label>
              <Textarea
                placeholder="Step-by-step execution plan"
                value={executionPlan}
                onChange={(e) => setExecutionPlan(e.target.value)}
                rows={4}
              />
            </div>
            <div>
              <Label>Rollback Plan</Label>
              <Textarea
                placeholder="Step-by-step rollback plan"
                value={rollbackPlan}
                onChange={(e) => setRollbackPlan(e.target.value)}
                rows={4}
              />
            </div>
          </motion.div>
        )}
        {step === 2 && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-4"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label>Maintenance Start</Label>
                <input
                  type="datetime-local"
                  value={mwStart}
                  onChange={(e) => setMwStart(e.target.value)}
                  className="w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus-ring"
                />
              </div>
              <div>
                <Label>Maintenance End</Label>
                <input
                  type="datetime-local"
                  value={mwEnd}
                  onChange={(e) => setMwEnd(e.target.value)}
                  className="w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus-ring"
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Nav buttons */}
      <div className="flex items-center justify-between pt-2">
        <Button
          variant="ghost"
          disabled={step === 0}
          onClick={() => setStep((s) => s - 1)}
        >
          <ChevronLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
        {step < steps.length - 1 ? (
          <Button disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
            Next
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        ) : (
          <Button
            disabled={!canNext || loading}
            loading={loading}
            onClick={() =>
              onSubmit({
                title,
                change_type: changeType,
                action,
                environment: env,
                description: desc,
                execution_plan: executionPlan,
                rollback_plan: rollbackPlan,
                maintenance_window_start: new Date(mwStart).toISOString(),
                maintenance_window_end: new Date(mwEnd).toISOString(),
                target_components: targetNodeIds,
              })
            }
          >
            Create
          </Button>
        )}
      </div>
    </div>
  )
}
