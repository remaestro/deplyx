import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  GitPullRequest,
  Network,
  ShieldCheck,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  Clock,
  LayoutGrid,
  List,
  Activity,
} from 'lucide-react'
import { apiClient } from '../api/client'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import {
  Card,
  CardHeader,
  CardContent,
  StatusBadge,
  RiskBadge,
  Skeleton,
  EmptyState,
  Badge,
} from '../components/ui'

type Change = {
  id: string
  title: string
  status: string
  risk_level: string | null
  environment: string
  created_at: string
}

type Kpis = {
  total_changes: number
  auto_approved_pct: number
  avg_validation_minutes: number | null
  incidents_post_change_pct: number
  scoring_precision_pct: number | null
  core_changes_detected_pct: number
  definitions?: Record<string, string>
}

type AuditEntry = {
  id: string
  action: string
  user_email: string
  change_id: string | null
  details: string | Record<string, unknown> | null
  created_at: string
}

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.3, ease: 'easeOut' as const },
  }),
}

/* ---------- Sparkline Mini-chart ---------- */
function Sparkline({ color }: { color: string }) {
  // Mock 7-point trend data for visual polish
  const data = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) => ({
        v: Math.round(20 + Math.random() * 60 + i * 3),
      })),
    [],
  )
  return (
    <div className="h-8 w-20">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#spark-${color})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- Status color constants for charts ---------- */
const STATUS_COLORS: Record<string, string> = {
  draft: '#94a3b8',
  pending_approval: '#f59e0b',
  approved: '#22c55e',
  rejected: '#ef4444',
  deployed: '#6366f1',
  rolled_back: '#ec4899',
}

const RISK_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
  critical: '#dc2626',
}

const TIME_RANGES = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
  { label: 'All', value: 'all' },
] as const

type ViewMode = 'table' | 'kanban'

export default function DashboardPage() {
  const [timeRange, setTimeRange] = useState<string>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('table')

  const { data: kpis, isLoading: kpisLoading } = useQuery<Kpis>({
    queryKey: ['dashboard-kpis'],
    queryFn: () => apiClient.get('/dashboard/kpis').then((r) => r.data),
  })

  const { data: changes = [], isLoading: changesLoading } = useQuery<Change[]>({
    queryKey: ['changes'],
    queryFn: () => apiClient.get('/changes').then((r) => r.data),
  })

  const { data: auditLog = [] } = useQuery<AuditEntry[]>({
    queryKey: ['audit-log-recent'],
    queryFn: () =>
      apiClient
        .get('/audit-log', { params: { limit: 20 } })
        .then((r) => r.data)
        .catch(() => []),
  })

  /* ---------- Filtered changes by time range ---------- */
  const filteredChanges = useMemo(() => {
    if (timeRange === 'all') return changes
    const now = Date.now()
    const ms: Record<string, number> = {
      '24h': 86_400_000,
      '7d': 604_800_000,
      '30d': 2_592_000_000,
    }
    const cutoff = now - (ms[timeRange] ?? 0)
    return changes.filter((c) => {
      const d = new Date(c.created_at);
      return !isNaN(d.getTime()) && d.getTime() >= cutoff;
    })
  }, [changes, timeRange])

  /* ---------- Chart data ---------- */
  const statusChartData = useMemo(() => {
    const counts: Record<string, number> = {}
    filteredChanges.forEach((c) => {
      counts[c.status] = (counts[c.status] || 0) + 1
    })
    return Object.entries(counts).map(([status, count]) => ({
      name: status.replace(/_/g, ' '),
      value: count,
      fill: STATUS_COLORS[status] ?? '#6366f1',
    }))
  }, [filteredChanges])

  const riskChartData = useMemo(() => {
    const counts: Record<string, number> = {}
    filteredChanges.forEach((c) => {
      const lvl = c.risk_level ?? 'unknown'
      counts[lvl] = (counts[lvl] || 0) + 1
    })
    return Object.entries(counts).map(([level, count]) => ({
      name: level,
      value: count,
      fill: RISK_COLORS[level] ?? '#94a3b8',
    }))
  }, [filteredChanges])

  /* ---------- Kanban columns ---------- */
  const kanbanColumns = useMemo(() => {
    const cols: Record<string, Change[]> = {
      draft: [],
      pending_approval: [],
      approved: [],
      deployed: [],
    }
    filteredChanges.forEach((c) => {
      if (cols[c.status]) cols[c.status].push(c)
      else if (!cols[c.status]) cols[c.status] = [c]
    })
    return cols
  }, [filteredChanges])

  const stats = [
    {
      label: 'Total Changes',
      value: kpis?.total_changes ?? changes.length,
      icon: GitPullRequest,
      iconBg: 'bg-brand-100 dark:bg-brand-900/30',
      iconColor: 'text-brand-600 dark:text-brand-400',
      sparkColor: '#6366f1',
    },
    {
      label: 'Auto-approved %',
      value: `${kpis?.auto_approved_pct ?? 0}%`,
      icon: ShieldCheck,
      iconBg: 'bg-emerald-100 dark:bg-emerald-900/30',
      iconColor: 'text-emerald-600 dark:text-emerald-400',
      sparkColor: '#22c55e',
    },
    {
      label: 'Avg Validation (min)',
      value: kpis?.avg_validation_minutes ?? '—',
      icon: Clock,
      iconBg: 'bg-amber-100 dark:bg-amber-900/30',
      iconColor: 'text-amber-600 dark:text-amber-400',
      sparkColor: '#f59e0b',
    },
    {
      label: 'Post-change Incidents %',
      value: `${kpis?.incidents_post_change_pct ?? 0}%`,
      icon: AlertTriangle,
      iconBg: 'bg-red-100 dark:bg-red-900/30',
      iconColor: 'text-red-600 dark:text-red-400',
      sparkColor: '#ef4444',
    },
    {
      label: 'Scoring Precision %',
      value: kpis?.scoring_precision_pct ?? '—',
      icon: TrendingUp,
      iconBg: 'bg-sky-100 dark:bg-sky-900/30',
      iconColor: 'text-sky-600 dark:text-sky-400',
      sparkColor: '#0ea5e9',
    },
    {
      label: 'Core Changes Detected %',
      value: `${kpis?.core_changes_detected_pct ?? 0}%`,
      icon: Network,
      iconBg: 'bg-violet-100 dark:bg-violet-900/30',
      iconColor: 'text-violet-600 dark:text-violet-400',
      sparkColor: '#8b5cf6',
    },
  ]

  return (
    <div className="space-y-6">
      {/* Time range picker */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800 dark:text-white">Dashboard</h1>
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-0.5">
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.value}
              onClick={() => setTimeRange(tr.value)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                timeRange === tr.value
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              {tr.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats grid with sparklines */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kpisLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-5"
              >
                <Skeleton variant="text" />
              </div>
            ))
          : stats.map((s, i) => (
              <motion.div key={s.label} custom={i} initial="hidden" animate="visible" variants={fadeUp}>
                <Card hover>
                  <CardContent>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3.5">
                        <div className={`rounded-lg p-2.5 ${s.iconBg}`}>
                          <s.icon className={`h-5 w-5 ${s.iconColor}`} />
                        </div>
                        <div>
                          <p className="text-sm text-slate-500 dark:text-slate-400">{s.label}</p>
                          <p className="text-2xl font-bold text-slate-800 dark:text-white">{s.value}</p>
                        </div>
                      </div>
                      <Sparkline color={s.sparkColor} />
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
      </div>

      {/* Charts row */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Risk Distribution Donut */}
        <motion.div initial="hidden" animate="visible" custom={0} variants={fadeUp}>
          <Card>
            <CardHeader title="Risk Distribution" />
            <CardContent>
              {changesLoading ? (
                <Skeleton variant="text" />
              ) : riskChartData.length === 0 ? (
                <p className="text-sm text-slate-400">No data</p>
              ) : (
                <div className="flex items-center justify-center gap-6">
                  <div className="h-48 w-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={riskChartData}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={70}
                          paddingAngle={3}
                          strokeWidth={0}
                        >
                          {riskChartData.map((d, idx) => (
                            <Cell key={idx} fill={d.fill} />
                          ))}
                        </Pie>
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: 'var(--color-surface, #fff)',
                            border: '1px solid var(--color-border, #e2e8f0)',
                            borderRadius: '8px',
                            fontSize: '12px',
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="space-y-2">
                    {riskChartData.map((d) => (
                      <div key={d.name} className="flex items-center gap-2 text-sm">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: d.fill }}
                        />
                        <span className="capitalize text-slate-600 dark:text-slate-400">{d.name}</span>
                        <span className="font-semibold text-slate-800 dark:text-white">{d.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Changes by Status Bar Chart */}
        <motion.div initial="hidden" animate="visible" custom={1} variants={fadeUp}>
          <Card>
            <CardHeader title="Changes by Status" />
            <CardContent>
              {changesLoading ? (
                <Skeleton variant="text" />
              ) : statusChartData.length === 0 ? (
                <p className="text-sm text-slate-400">No data</p>
              ) : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={statusChartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        axisLine={false}
                        tickLine={false}
                        allowDecimals={false}
                      />
                      <RechartsTooltip
                        contentStyle={{
                          backgroundColor: 'var(--color-surface, #fff)',
                          border: '1px solid var(--color-border, #e2e8f0)',
                          borderRadius: '8px',
                          fontSize: '12px',
                        }}
                      />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {statusChartData.map((d, idx) => (
                          <Cell key={idx} fill={d.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Recent changes with view toggle */}
      <Card>
        <CardHeader
          title="Recent Changes"
          action={
            <div className="flex items-center gap-3">
              {/* View toggle */}
              <div className="flex items-center gap-0.5 rounded-md border border-slate-200 dark:border-slate-700 p-0.5">
                <button
                  onClick={() => setViewMode('table')}
                  className={`rounded p-1 transition-colors ${
                    viewMode === 'table'
                      ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400'
                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                  }`}
                  aria-label="Table view"
                >
                  <List className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setViewMode('kanban')}
                  className={`rounded p-1 transition-colors ${
                    viewMode === 'kanban'
                      ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400'
                      : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300'
                  }`}
                  aria-label="Kanban view"
                >
                  <LayoutGrid className="h-3.5 w-3.5" />
                </button>
              </div>
              <Link
                to="/changes"
                className="flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
              >
                View all
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          }
        />
        <CardContent>
          {changesLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} variant="table-row" />
              ))}
            </div>
          ) : filteredChanges.length === 0 ? (
            <EmptyState
              icon={GitPullRequest}
              title="No changes yet"
              description="Create your first change request to get started."
              action={
                <Link
                  to="/changes"
                  className="inline-flex items-center gap-1.5 rounded-btn bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
                >
                  New Change
                </Link>
              }
            />
          ) : (
            <AnimatePresence mode="wait">
              {viewMode === 'table' ? (
                <motion.div
                  key="table"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="overflow-x-auto -mx-5"
                >
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-700/60 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                        <th className="px-5 py-3">Title</th>
                        <th className="px-5 py-3">Status</th>
                        <th className="px-5 py-3">Risk</th>
                        <th className="px-5 py-3">Environment</th>
                        <th className="px-5 py-3">Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredChanges.slice(0, 10).map((c, i) => (
                        <motion.tr
                          key={c.id}
                          custom={i}
                          initial="hidden"
                          animate="visible"
                          variants={fadeUp}
                          className="border-b border-slate-50 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-surface-dark-tertiary transition-colors"
                        >
                          <td className="px-5 py-3">
                            <Link
                              to={`/changes/${c.id}`}
                              className="font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
                            >
                              {c.title}
                            </Link>
                          </td>
                          <td className="px-5 py-3">
                            <StatusBadge status={c.status} />
                          </td>
                          <td className="px-5 py-3">
                            <RiskBadge level={c.risk_level} />
                          </td>
                          <td className="px-5 py-3 text-slate-600 dark:text-slate-400">{c.environment}</td>
                          <td className="px-5 py-3 text-xs text-slate-400">
                            {isNaN(new Date(c.created_at).getTime()) ? 'Unknown' : formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </motion.div>
              ) : (
                <motion.div
                  key="kanban"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="grid grid-cols-2 lg:grid-cols-4 gap-3 -mx-1"
                >
                  {Object.entries(kanbanColumns).map(([status, items]) => (
                    <div key={status} className="space-y-2">
                      <div className="flex items-center gap-2 px-1">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: STATUS_COLORS[status] ?? '#6366f1' }}
                        />
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                          {status.replace(/_/g, ' ')}
                        </span>
                        <Badge color="neutral" className="text-[10px] px-1.5 py-0">
                          {items.length}
                        </Badge>
                      </div>
                      <div className="space-y-2">
                        {items.slice(0, 5).map((c, i) => (
                          <motion.div key={c.id} custom={i} initial="hidden" animate="visible" variants={fadeUp}>
                            <Link to={`/changes/${c.id}`} className="block">
                              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-3 hover:shadow-md dark:hover:border-slate-600 transition-all">
                                <p className="text-sm font-medium text-slate-700 dark:text-slate-200 line-clamp-2">
                                  {c.title}
                                </p>
                                <div className="mt-2 flex items-center gap-2">
                                  <RiskBadge level={c.risk_level} />
                                  <span className="text-[10px] text-slate-400">{c.environment}</span>
                                </div>
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
          )}
        </CardContent>
      </Card>

      {/* Activity Feed */}
      <Card>
        <CardHeader
          title="Activity Feed"
          action={
            <Link
              to="/audit-log"
              className="flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
            >
              View all
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          }
        />
        <CardContent>
          {auditLog.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-slate-500">No recent activity.</p>
          ) : (
            <div className="relative space-y-0">
              {/* Vertical line */}
              <div className="absolute left-3 top-2 bottom-2 w-px bg-slate-200 dark:bg-slate-700" />
              {auditLog.slice(0, 8).map((entry, i) => (
                <motion.div
                  key={entry.id}
                  custom={i}
                  initial="hidden"
                  animate="visible"
                  variants={fadeUp}
                  className="relative flex items-start gap-3 py-2.5"
                >
                  <div className="relative z-10 mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-900/30">
                    <Activity className="h-3 w-3 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-700 dark:text-slate-300">
                      <span className="font-medium">{entry.user_email}</span>{' '}
                      <span className="text-slate-500 dark:text-slate-400">{entry.action.replace(/_/g, ' ')}</span>
                    </p>
                    {entry.details && (
                      <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500 truncate">
                        {typeof entry.details === 'string' ? entry.details : JSON.stringify(entry.details)}
                      </p>
                    )}
                    <p className="mt-0.5 text-[10px] text-slate-400">
                      {isNaN(new Date(entry.created_at).getTime()) ? 'Unknown' : formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
                    </p>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* KPI Definitions */}
      {kpis?.definitions && (
        <Card>
          <CardHeader title="KPI Definitions" />
          <CardContent>
            <div className="space-y-2.5 text-sm">
              {[
                { key: 'auto_approved_pct', label: 'Auto-approved %' },
                { key: 'avg_validation_minutes', label: 'Avg Validation' },
                { key: 'incidents_post_change_pct', label: 'Post-change Incidents %' },
                { key: 'scoring_precision_pct', label: 'Scoring Precision %' },
                { key: 'core_changes_detected_pct', label: 'Core Changes Detected %' },
              ].map(({ key, label }) => (
                <p key={key} className="text-slate-600 dark:text-slate-400">
                  <span className="font-medium text-slate-700 dark:text-slate-300">{label}:</span>{' '}
                  {kpis.definitions?.[key]}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
