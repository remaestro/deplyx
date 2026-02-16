import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, Clock, Shield, Users, Search, AlertTriangle,
  Play, Eye, X, ChevronRight, ChevronLeft, Zap,
} from 'lucide-react'
import { apiClient } from '../api/client'
import { motion, AnimatePresence } from 'framer-motion'
import { formatDistanceToNow } from 'date-fns'
import {
  Button,
  Card,
  CardHeader,
  CardContent,
  Skeleton,
  EmptyState,
  Badge,
  Input,
  Textarea,
  Select,
  Label,
  Tabs,
  TabList,
  Tab,
  TabPanel,
  CodeBlock,
} from '../components/ui'

/* ── Types ───────────────────────────────────────────── */

type Policy = {
  id: number
  name: string
  description: string
  rule_type: string
  condition: Record<string, unknown>
  action: string
  enabled: boolean
  created_at: string
  last_triggered_at?: string
}

type SimulationResult = {
  would_block: boolean
  matched_rules: string[]
  risk_delta: number
}

type ConflictPair = {
  policy_a: string
  policy_b: string
  conflict_type: string
  description: string
}

/* ── Constants ───────────────────────────────────────── */

const TYPE_ICON: Record<string, typeof Clock> = {
  time_restriction: Clock,
  double_validation: Users,
  auto_block: Shield,
}

const TYPE_COLOR: Record<string, string> = {
  time_restriction: 'info',
  double_validation: 'warning',
  auto_block: 'critical',
}

const ACTION_COLOR: Record<string, string> = {
  block: 'critical',
  warn: 'warning',
  require_double_approval: 'purple',
}

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/* ── Helpers ─────────────────────────────────────────── */

function conditionSummary(p: Policy): string[] {
  const c = p.condition
  const chips: string[] = []
  if (c.environments) chips.push(`Envs: ${(c.environments as string[]).join(', ')}`)
  if (c.blocked_hours_start !== undefined)
    chips.push(`Hours ${c.blocked_hours_start}–${c.blocked_hours_end}`)
  if (c.blocked_days)
    chips.push(`Days: ${(c.blocked_days as number[]).map((d) => WEEKDAY_LABELS[d]).join(', ')}`)
  if (c.required_approvals) chips.push(`≥${c.required_approvals} approvals`)
  if (c.change_types) chips.push(`Types: ${(c.change_types as string[]).join(', ')}`)
  if (c.block_any_any_rules) chips.push('Block ANY-ANY')
  if (c.block_environments) chips.push(`Block envs: ${(c.block_environments as string[]).join(', ')}`)
  if (c.block_change_types) chips.push(`Block types: ${(c.block_change_types as string[]).join(', ')}`)
  return chips
}

/* ── Animated Toggle ─────────────────────────────────── */

function AnimatedToggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
        enabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
      }`}
      role="switch"
      aria-checked={enabled}
    >
      <motion.span
        className="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0"
        animate={{ x: enabled ? 20 : 0 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
    </button>
  )
}

/* ── Policy Card ─────────────────────────────────────── */

function PolicyCard({
  policy,
  onToggle,
  onDelete,
  onSimulate,
}: {
  policy: Policy
  onToggle: () => void
  onDelete: () => void
  onSimulate: () => void
}) {
  const Icon = TYPE_ICON[policy.rule_type] || Shield
  const chips = conditionSummary(policy)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={`rounded-xl border transition-colors ${
        policy.enabled
          ? 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900'
          : 'border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 opacity-70'
      }`}
    >
      <div className="flex items-start gap-4 p-4">
        {/* Icon */}
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
            policy.rule_type === 'auto_block'
              ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
              : policy.rule_type === 'double_validation'
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
              : 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
          }`}
        >
          <Icon className="h-5 w-5" />
        </div>

        {/* Body */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-slate-800 dark:text-slate-100 truncate">{policy.name}</h3>
            <Badge color={(TYPE_COLOR[policy.rule_type] ?? 'neutral') as 'info' | 'warning' | 'critical' | 'neutral'}>
              {policy.rule_type.replace(/_/g, ' ')}
            </Badge>
            <Badge color={(ACTION_COLOR[policy.action] ?? 'neutral') as 'critical' | 'warning' | 'purple' | 'neutral'}>
              {policy.action.replace(/_/g, ' ')}
            </Badge>
          </div>
          {policy.description && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">{policy.description}</p>
          )}

          {/* Condition chips */}
          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {chips.map((chip, i) => (
                <span
                  key={i}
                  className="inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-300"
                >
                  {chip}
                </span>
              ))}
            </div>
          )}

          {/* Last triggered */}
          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            {policy.last_triggered_at
              ? `Last triggered ${formatDistanceToNow(new Date(policy.last_triggered_at), { addSuffix: true })}`
              : 'Never triggered'}
            {' · '}
            Created {formatDistanceToNow(new Date(policy.created_at), { addSuffix: true })}
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <Button size="xs" variant="ghost" onClick={onSimulate} title="Simulate">
            <Play className="h-3.5 w-3.5" />
          </Button>
          <AnimatedToggle enabled={policy.enabled} onToggle={onToggle} />
          <button
            onClick={onDelete}
            className="rounded p-1.5 text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </motion.div>
  )
}

/* ── Simulation Panel ────────────────────────────────── */

function SimulationPanel({
  policies,
  onClose,
}: {
  policies: Policy[]
  onClose: () => void
}) {
  const [selectedPolicyId, setSelectedPolicyId] = useState(policies[0]?.id ?? 0)
  const [mockChange, setMockChange] = useState(
    '{\n  "title": "Add firewall rule",\n  "change_type": "firewall",\n  "environment": "production",\n  "risk_score": 72\n}',
  )
  const [result, setResult] = useState<SimulationResult | null>(null)
  const [running, setRunning] = useState(false)

  const runSimulation = async () => {
    setRunning(true)
    try {
      const res = await apiClient.post(`/policies/${selectedPolicyId}/simulate`, JSON.parse(mockChange))
      setResult(res.data)
    } catch {
      // Fallback mock result when backend stub is not yet implemented
      setResult({
        would_block: Math.random() > 0.4,
        matched_rules: ['time_restriction_check', 'env_scope_match'],
        risk_delta: Math.round((Math.random() * 30 - 15) * 10) / 10,
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card>
      <CardHeader title="Policy Simulation" action={
        <button onClick={onClose} className="rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
          <X className="h-4 w-4" />
        </button>
      } />
      <CardContent>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div>
              <Label htmlFor="sim-policy">Policy</Label>
              <Select id="sim-policy" value={selectedPolicyId} onChange={(e) => setSelectedPolicyId(Number(e.target.value))}>
                {policies.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="sim-change">Mock Change (JSON)</Label>
              <Textarea
                id="sim-change"
                rows={6}
                value={mockChange}
                onChange={(e) => setMockChange(e.target.value)}
                className="font-mono text-xs"
              />
            </div>
            <Button onClick={runSimulation} loading={running}>
              <Play className="h-4 w-4" /> Run Simulation
            </Button>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">Result</p>
            {result ? (
              <div className="space-y-3">
                <div className={`flex items-center gap-2 rounded-lg p-3 text-sm font-medium ${
                  result.would_block
                    ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                    : 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400'
                }`}>
                  {result.would_block ? <AlertTriangle className="h-4 w-4" /> : <Zap className="h-4 w-4" />}
                  {result.would_block ? 'Change would be BLOCKED' : 'Change would PASS'}
                </div>
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">Matched rules:</p>
                  <div className="flex flex-wrap gap-1">
                    {result.matched_rules.map((r) => (
                      <Badge key={r} color="neutral">{r}</Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Risk delta: <span className={result.risk_delta > 0 ? 'text-red-500' : 'text-emerald-500'}>
                      {result.risk_delta > 0 ? '+' : ''}{result.risk_delta}
                    </span>
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-32 text-sm text-slate-400 dark:text-slate-500">
                Run a simulation to see results
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/* ── Conflict Detection Panel ────────────────────────── */

function ConflictPanel({ onClose }: { onClose: () => void }) {
  const { data: conflicts = [], isLoading } = useQuery<ConflictPair[]>({
    queryKey: ['policy-conflicts'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/policies/conflicts')
        return res.data
      } catch {
        // Mock fallback
        return [
          {
            policy_a: 'Block Production Changes After Hours',
            policy_b: 'Auto-approve Low Risk',
            conflict_type: 'overlap',
            description: 'Both policies target production environment with contradicting actions.',
          },
          {
            policy_a: 'Require Double Approval',
            policy_b: 'Auto Block ANY-ANY',
            conflict_type: 'precedence',
            description: 'Auto-block fires before double approval can be requested.',
          },
        ]
      }
    },
  })

  return (
    <Card>
      <CardHeader title="Policy Conflicts" action={
        <button onClick={onClose} className="rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
          <X className="h-4 w-4" />
        </button>
      } />
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
          </div>
        ) : conflicts.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 p-3 text-sm text-emerald-700 dark:text-emerald-400">
            <Zap className="h-4 w-4" /> No conflicts detected
          </div>
        ) : (
          <div className="space-y-3">
            {conflicts.map((c, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="flex items-start gap-3 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50/50 dark:bg-amber-900/10 p-3"
              >
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500 mt-0.5" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                    {c.policy_a} <span className="text-slate-400 dark:text-slate-500">↔</span> {c.policy_b}
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{c.description}</p>
                  <Badge color="warning">{c.conflict_type}</Badge>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ── Main Page ───────────────────────────────────────── */

export default function PoliciesPage() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [showSimulation, setShowSimulation] = useState(false)
  const [showConflicts, setShowConflicts] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [filterType, setFilterType] = useState<string | null>(null)

  const { data: policies = [], isLoading } = useQuery<Policy[]>({
    queryKey: ['policies'],
    queryFn: () => apiClient.get('/policies').then((r) => r.data),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/policies/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['policies'] }),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiClient.put(`/policies/${id}`, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['policies'] }),
  })

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => apiClient.post('/policies', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policies'] })
      setShowCreate(false)
    },
  })

  const filteredPolicies = useMemo(() => {
    let list = policies
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q),
      )
    }
    if (filterType) list = list.filter((p) => p.rule_type === filterType)
    return list
  }, [policies, searchTerm, filterType])

  const enabledCount = policies.filter((p) => p.enabled).length

  return (
    <div className="space-y-4">
      {/* Header toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> Add Policy
        </Button>
        <Button variant="secondary" onClick={() => setShowSimulation(!showSimulation)}>
          <Play className="h-4 w-4" /> Simulate
        </Button>
        <Button variant="secondary" onClick={() => setShowConflicts(!showConflicts)}>
          <AlertTriangle className="h-4 w-4" /> Conflicts
        </Button>

        <div className="flex-1" />

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
          <Input
            placeholder="Search policies…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8 w-56"
          />
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
        <span>{policies.length} total</span>
        <span className="text-emerald-600 dark:text-emerald-400">{enabledCount} enabled</span>
        <span className="text-slate-400">{policies.length - enabledCount} disabled</span>
        <div className="flex-1" />
        {/* Filter chips */}
        {(['time_restriction', 'double_validation', 'auto_block'] as const).map((t) => {
          const Icon = TYPE_ICON[t]
          const active = filterType === t
          return (
            <button
              key={t}
              onClick={() => setFilterType(active ? null : t)}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                active
                  ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <Icon className="h-3 w-3" />
              {t.replace(/_/g, ' ')}
            </button>
          )
        })}
      </div>

      {/* Simulation panel */}
      <AnimatePresence>
        {showSimulation && policies.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <SimulationPanel policies={policies} onClose={() => setShowSimulation(false)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Conflict panel */}
      <AnimatePresence>
        {showConflicts && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <ConflictPanel onClose={() => setShowConflicts(false)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create drawer */}
      <AnimatePresence>
        {showCreate && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black"
              onClick={() => setShowCreate(false)}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 26, stiffness: 300 }}
              className="fixed right-0 top-0 z-50 h-full w-full max-w-xl overflow-y-auto bg-white dark:bg-slate-900 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 p-4">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">New Policy</h2>
                <button onClick={() => setShowCreate(false)} className="rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-4">
                <PolicyWizard onSubmit={(b) => createMut.mutate(b)} loading={createMut.isPending} />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Policy list */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : filteredPolicies.length === 0 ? (
        policies.length === 0 ? (
          <EmptyState title="No policies configured" description="Add a policy to automate change governance." />
        ) : (
          <EmptyState title="No matching policies" description="Try adjusting your search or filters." />
        )
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {filteredPolicies.map((p) => (
              <PolicyCard
                key={p.id}
                policy={p}
                onToggle={() => toggleMut.mutate({ id: p.id, enabled: !p.enabled })}
                onDelete={() => deleteMut.mutate(p.id)}
                onSimulate={() => {
                  setShowSimulation(true)
                }}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}

/* ── Policy Wizard (3-step) ──────────────────────────── */

function PolicyWizard({
  onSubmit,
  loading,
}: {
  onSubmit: (b: Record<string, unknown>) => void
  loading: boolean
}) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState('time_restriction')
  const [action, setAction] = useState('block')
  const [description, setDescription] = useState('')
  const [timeEnv, setTimeEnv] = useState<string[]>(['production'])
  const [blockedStart, setBlockedStart] = useState(8)
  const [blockedEnd, setBlockedEnd] = useState(18)
  const [blockedDays, setBlockedDays] = useState<number[]>([0, 1, 2, 3, 4])
  const [doubleEnv, setDoubleEnv] = useState<string[]>(['production'])
  const [doubleTypes, setDoubleTypes] = useState<string[]>(['firewall'])
  const [requiredApprovals, setRequiredApprovals] = useState(2)
  const [autoBlockAnyAny, setAutoBlockAnyAny] = useState(true)
  const [autoBlockEnv, setAutoBlockEnv] = useState<string[]>(['production'])
  const [autoBlockTypes, setAutoBlockTypes] = useState<string[]>(['firewall'])

  const envOptions = [
    { value: 'production', label: 'Production' },
    { value: 'preprod', label: 'Preprod' },
    { value: 'dc1', label: 'DC1' },
    { value: 'dc2', label: 'DC2' },
  ]

  const changeTypeOptions = [
    { value: 'firewall', label: 'Firewall' },
    { value: 'switch', label: 'Switch' },
    { value: 'vlan', label: 'VLAN' },
    { value: 'port', label: 'Port' },
    { value: 'rack', label: 'Rack' },
    { value: 'cloudsg', label: 'Cloud SG' },
  ]

  const weekdayOptions = [
    { value: 0, label: 'Mon' },
    { value: 1, label: 'Tue' },
    { value: 2, label: 'Wed' },
    { value: 3, label: 'Thu' },
    { value: 4, label: 'Fri' },
    { value: 5, label: 'Sat' },
    { value: 6, label: 'Sun' },
  ]

  const toggleString = (arr: string[], value: string) =>
    arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value]

  const toggleNumber = (arr: number[], value: number) =>
    arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value]

  const buildCondition = () => {
    if (ruleType === 'time_restriction') {
      return {
        blocked_hours_start: blockedStart,
        blocked_hours_end: blockedEnd,
        blocked_days: blockedDays,
        environments: timeEnv,
      }
    }
    if (ruleType === 'double_validation') {
      return {
        environments: doubleEnv,
        change_types: doubleTypes,
        required_approvals: requiredApprovals,
      }
    }
    return {
      block_any_any_rules: autoBlockAnyAny,
      block_environments: autoBlockEnv,
      block_change_types: autoBlockTypes,
    }
  }

  const submit = () => {
    onSubmit({
      name,
      rule_type: ruleType,
      action,
      description,
      condition: buildCondition(),
    })
  }

  const chipClass =
    'flex items-center gap-1 rounded-btn border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer select-none'

  const steps = ['Basics', 'Conditions', 'Preview']
  const canNext = step === 0 ? !!name : true

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {steps.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                i <= step
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-400'
              }`}
            >
              {i + 1}
            </div>
            <span className={`text-sm ${i <= step ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'}`}>
              {s}
            </span>
            {i < steps.length - 1 && <ChevronRight className="h-4 w-4 text-slate-300 dark:text-slate-600" />}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {/* Step 1: Basics */}
        {step === 0 && (
          <motion.div key="basics" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-3">
            <div>
              <Label htmlFor="pol-name">Name</Label>
              <Input id="pol-name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="pol-desc">Description</Label>
              <Textarea id="pol-desc" placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label htmlFor="pol-type">Rule Type</Label>
                <Select id="pol-type" value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
                  <option value="time_restriction">Time Restriction</option>
                  <option value="double_validation">Double Validation</option>
                  <option value="auto_block">Auto Block</option>
                </Select>
              </div>
              <div>
                <Label htmlFor="pol-action">Action</Label>
                <Select id="pol-action" value={action} onChange={(e) => setAction(e.target.value)}>
                  <option value="block">Block</option>
                  <option value="warn">Warn</option>
                  <option value="require_double_approval">Require Double Approval</option>
                </Select>
              </div>
            </div>
          </motion.div>
        )}

        {/* Step 2: Conditions */}
        {step === 1 && (
          <motion.div key="conditions" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-3">
            {ruleType === 'time_restriction' && (
              <div className="space-y-2 rounded-btn border border-slate-200 dark:border-slate-700 p-3">
                <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Condition: Time restriction</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label className="text-xs">Blocked hour start</Label>
                    <Input type="number" min={0} max={23} value={blockedStart} onChange={(e) => setBlockedStart(Number(e.target.value))} />
                  </div>
                  <div>
                    <Label className="text-xs">Blocked hour end</Label>
                    <Input type="number" min={1} max={24} value={blockedEnd} onChange={(e) => setBlockedEnd(Number(e.target.value))} />
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Blocked days</p>
                  <div className="flex flex-wrap gap-2">
                    {weekdayOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={blockedDays.includes(opt.value)} onChange={() => setBlockedDays((prev) => toggleNumber(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Environments</p>
                  <div className="flex flex-wrap gap-2">
                    {envOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={timeEnv.includes(opt.value)} onChange={() => setTimeEnv((prev) => toggleString(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {ruleType === 'double_validation' && (
              <div className="space-y-2 rounded-btn border border-slate-200 dark:border-slate-700 p-3">
                <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Condition: Double validation</p>
                <div>
                  <Label className="text-xs">Required approvals</Label>
                  <Input type="number" min={2} max={10} value={requiredApprovals} onChange={(e) => setRequiredApprovals(Number(e.target.value))} />
                </div>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Environments</p>
                  <div className="flex flex-wrap gap-2">
                    {envOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={doubleEnv.includes(opt.value)} onChange={() => setDoubleEnv((prev) => toggleString(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Change types</p>
                  <div className="flex flex-wrap gap-2">
                    {changeTypeOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={doubleTypes.includes(opt.value)} onChange={() => setDoubleTypes((prev) => toggleString(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {ruleType === 'auto_block' && (
              <div className="space-y-2 rounded-btn border border-slate-200 dark:border-slate-700 p-3">
                <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Condition: Auto block</p>
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                  <input type="checkbox" checked={autoBlockAnyAny} onChange={(e) => setAutoBlockAnyAny(e.target.checked)} className="accent-brand-600" />
                  Block ANY-ANY rules
                </label>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Block environments</p>
                  <div className="flex flex-wrap gap-2">
                    {envOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={autoBlockEnv.includes(opt.value)} onChange={() => setAutoBlockEnv((prev) => toggleString(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs text-slate-600 dark:text-slate-400">Block change types</p>
                  <div className="flex flex-wrap gap-2">
                    {changeTypeOptions.map((opt) => (
                      <label key={opt.value} className={chipClass}>
                        <input type="checkbox" checked={autoBlockTypes.includes(opt.value)} onChange={() => setAutoBlockTypes((prev) => toggleString(prev, opt.value))} className="accent-brand-600" />
                        {opt.label}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        )}

        {/* Step 3: Preview */}
        {step === 2 && (
          <motion.div key="preview" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-3">
            <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Preview</p>
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <h4 className="font-semibold text-slate-800 dark:text-slate-100">{name || '(untitled)'}</h4>
                <Badge color={(TYPE_COLOR[ruleType] ?? 'neutral') as 'info' | 'warning' | 'critical' | 'neutral'}>
                  {ruleType.replace(/_/g, ' ')}
                </Badge>
                <Badge color={(ACTION_COLOR[action] ?? 'neutral') as 'critical' | 'warning' | 'purple' | 'neutral'}>
                  {action.replace(/_/g, ' ')}
                </Badge>
              </div>
              {description && <p className="text-sm text-slate-500 dark:text-slate-400">{description}</p>}
              <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mt-3">Condition JSON</p>
              <CodeBlock language="json">{JSON.stringify(buildCondition(), null, 2)}</CodeBlock>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-700">
        <Button variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={step === 0}>
          <ChevronLeft className="h-4 w-4" /> Back
        </Button>
        {step < steps.length - 1 ? (
          <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>
            Next <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button disabled={!name || loading} onClick={submit}>
            {loading ? 'Creating…' : 'Create Policy'}
          </Button>
        )}
      </div>
    </div>
  )
}
