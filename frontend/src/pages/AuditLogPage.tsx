import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search, Download, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle2, Edit3, Trash2, Play, Eye, LogIn,
  Plus, RefreshCw, Shield,
} from 'lucide-react'
import { apiClient } from '../api/client'
import { motion, AnimatePresence } from 'framer-motion'
import { formatDistanceToNow, format, isAfter, subDays, subHours } from 'date-fns'
import {
  Button,
  Card,
  CardContent,
  Skeleton,
  EmptyState,
  Badge,
  Input,
  Select,
  Label,
} from '../components/ui'

/* ── Types ───────────────────────────────────────────── */

type AuditEntry = {
  id: number
  change_id: number | null
  user_id: number | null
  action: string
  details: Record<string, unknown> | null
  timestamp: string
}

/* ── Action icon / color map ─────────────────────────── */

const ACTION_META: Record<string, { icon: typeof Edit3; color: string; bg: string }> = {
  created:   { icon: Plus,           color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-900/30' },
  approved:  { icon: CheckCircle2,   color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-100 dark:bg-emerald-900/30' },
  rejected:  { icon: AlertTriangle,  color: 'text-red-600 dark:text-red-400',         bg: 'bg-red-100 dark:bg-red-900/30' },
  executed:  { icon: Play,           color: 'text-blue-600 dark:text-blue-400',       bg: 'bg-blue-100 dark:bg-blue-900/30' },
  rolled_back: { icon: RefreshCw,    color: 'text-amber-600 dark:text-amber-400',     bg: 'bg-amber-100 dark:bg-amber-900/30' },
  deleted:   { icon: Trash2,         color: 'text-red-600 dark:text-red-400',         bg: 'bg-red-100 dark:bg-red-900/30' },
  updated:   { icon: Edit3,          color: 'text-blue-600 dark:text-blue-400',       bg: 'bg-blue-100 dark:bg-blue-900/30' },
  viewed:    { icon: Eye,            color: 'text-slate-500 dark:text-slate-400',     bg: 'bg-slate-100 dark:bg-slate-800' },
  login:     { icon: LogIn,          color: 'text-purple-600 dark:text-purple-400',   bg: 'bg-purple-100 dark:bg-purple-900/30' },
  policy_triggered: { icon: Shield,  color: 'text-amber-600 dark:text-amber-400',     bg: 'bg-amber-100 dark:bg-amber-900/30' },
}

const DEFAULT_META = { icon: Edit3, color: 'text-slate-500 dark:text-slate-400', bg: 'bg-slate-100 dark:bg-slate-800' }

function actionMeta(action: string) {
  const key = action.toLowerCase().replace(/\s+/g, '_')
  return ACTION_META[key] ?? DEFAULT_META
}

const ACTION_BADGE_COLOR: Record<string, 'success' | 'critical' | 'warning' | 'info' | 'neutral' | 'purple'> = {
  created: 'success',
  approved: 'success',
  rejected: 'critical',
  executed: 'info',
  rolled_back: 'warning',
  deleted: 'critical',
  updated: 'info',
  login: 'purple',
  policy_triggered: 'warning',
}

/* ── Time range filter values ────────────────────────── */

const TIME_RANGES = [
  { label: 'Last 1 h', value: '1h' },
  { label: 'Last 24 h', value: '24h' },
  { label: 'Last 7 d', value: '7d' },
  { label: 'Last 30 d', value: '30d' },
  { label: 'All time', value: 'all' },
]

function timeCutoff(range: string): Date | null {
  const now = new Date()
  switch (range) {
    case '1h': return subHours(now, 1)
    case '24h': return subHours(now, 24)
    case '7d': return subDays(now, 7)
    case '30d': return subDays(now, 30)
    default: return null
  }
}

/* ── Export helpers ───────────────────────────────────── */

function downloadJSON(entries: AuditEntry[]) {
  const blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-log-${format(new Date(), 'yyyy-MM-dd')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function downloadCSV(entries: AuditEntry[]) {
  const header = 'id,timestamp,action,change_id,user_id,details'
  const rows = entries.map(
    (e) =>
      `${e.id},"${e.timestamp}","${e.action}",${e.change_id ?? ''},${e.user_id ?? ''},"${e.details ? JSON.stringify(e.details).replace(/"/g, '""') : ''}"`,
  )
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit-log-${format(new Date(), 'yyyy-MM-dd')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/* ── Expandable Entry ────────────────────────────────── */

function TimelineEntry({ entry, isLast }: { entry: AuditEntry; isLast: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const meta = actionMeta(entry.action)
  const Icon = meta.icon
  const badgeColor = ACTION_BADGE_COLOR[entry.action.toLowerCase().replace(/\s+/g, '_')] ?? 'neutral'

  return (
    <div className="flex gap-3">
      {/* Timeline line + dot */}
      <div className="flex flex-col items-center">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${meta.bg}`}>
          <Icon className={`h-4 w-4 ${meta.color}`} />
        </div>
        {!isLast && <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700" />}
      </div>

      {/* Card */}
      <motion.div
        initial={{ opacity: 0, x: -6 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex-1 mb-4"
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 hover:border-slate-300 dark:hover:border-slate-600 transition-colors group"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge color={badgeColor}>{entry.action}</Badge>
              {entry.change_id && (
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  Change #{entry.change_id}
                </span>
              )}
              {entry.user_id && (
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  User {entry.user_id}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-[11px] text-slate-400 dark:text-slate-500"
                title={format(new Date(entry.timestamp), 'PPpp')}
              >
                {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
              </span>
              {entry.details && (
                expanded ? (
                  <ChevronUp className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-300 transition-colors" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-300 transition-colors" />
                )
              )}
            </div>
          </div>
        </button>

        <AnimatePresence>
          {expanded && entry.details && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="ml-3 mt-1 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-3">
                <pre className="text-xs font-mono text-slate-600 dark:text-slate-300 whitespace-pre-wrap overflow-x-auto">
                  {JSON.stringify(entry.details, null, 2)}
                </pre>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

/* ── Main Page ───────────────────────────────────────── */

export default function AuditLogPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [filterAction, setFilterAction] = useState<string>('all')
  const [filterUser, setFilterUser] = useState<string>('')
  const [filterChange, setFilterChange] = useState<string>('')
  const [timeRange, setTimeRange] = useState('all')
  const [exportOpen, setExportOpen] = useState(false)

  const { data: entries = [], isLoading } = useQuery<AuditEntry[]>({
    queryKey: ['audit-log'],
    queryFn: () => apiClient.get('/audit-log').then((r) => r.data),
  })

  // Unique action types for filter dropdown
  const actionTypes = useMemo(
    () => Array.from(new Set(entries.map((e) => e.action))).sort(),
    [entries],
  )

  const filtered = useMemo(() => {
    let list = entries
    // Full-text search
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      list = list.filter(
        (e) =>
          e.action.toLowerCase().includes(q) ||
          (e.details && JSON.stringify(e.details).toLowerCase().includes(q)) ||
          String(e.change_id).includes(q) ||
          String(e.user_id).includes(q),
      )
    }
    // Action filter
    if (filterAction !== 'all') list = list.filter((e) => e.action === filterAction)
    // User filter
    if (filterUser) list = list.filter((e) => String(e.user_id) === filterUser)
    // Change filter
    if (filterChange) list = list.filter((e) => String(e.change_id) === filterChange)
    // Time range
    const cutoff = timeCutoff(timeRange)
    if (cutoff) list = list.filter((e) => isAfter(new Date(e.timestamp), cutoff))
    return list
  }, [entries, searchTerm, filterAction, filterUser, filterChange, timeRange])

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-end gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <Input
            placeholder="Full-text search…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8"
          />
        </div>

        {/* Action filter */}
        <div className="w-40">
          <Label className="text-xs">Action</Label>
          <Select value={filterAction} onChange={(e) => setFilterAction(e.target.value)}>
            <option value="all">All actions</option>
            {actionTypes.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </Select>
        </div>

        {/* User filter */}
        <div className="w-28">
          <Label className="text-xs">User ID</Label>
          <Input placeholder="Any" value={filterUser} onChange={(e) => setFilterUser(e.target.value)} />
        </div>

        {/* Change filter */}
        <div className="w-28">
          <Label className="text-xs">Change ID</Label>
          <Input placeholder="Any" value={filterChange} onChange={(e) => setFilterChange(e.target.value)} />
        </div>

        {/* Time range */}
        <div className="flex items-center gap-1">
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.value}
              onClick={() => setTimeRange(tr.value)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                timeRange === tr.value
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {tr.label}
            </button>
          ))}
        </div>

        {/* Export */}
        <div className="relative">
          <Button variant="secondary" onClick={() => setExportOpen(!exportOpen)}>
            <Download className="h-4 w-4" /> Export
          </Button>
          <AnimatePresence>
            {exportOpen && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="absolute right-0 top-full z-20 mt-1 w-36 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg py-1"
              >
                <button
                  onClick={() => { downloadJSON(filtered); setExportOpen(false) }}
                  className="w-full text-left px-3 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Export JSON
                </button>
                <button
                  onClick={() => { downloadCSV(filtered); setExportOpen(false) }}
                  className="w-full text-left px-3 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Export CSV
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
        <span>{filtered.length} of {entries.length} entries</span>
      </div>

      {/* Timeline */}
      {isLoading ? (
        <Card>
          <CardContent>
            <div className="space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex gap-3">
                  <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                  <Skeleton className="h-14 flex-1 rounded-lg" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        entries.length === 0 ? (
          <EmptyState title="No audit entries yet" description="Actions on changes will appear here." />
        ) : (
          <EmptyState title="No matching entries" description="Try adjusting your search or filters." />
        )
      ) : (
        <div className="pl-1">
          {filtered.map((entry, i) => (
            <TimelineEntry key={entry.id} entry={entry} isLast={i === filtered.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}
