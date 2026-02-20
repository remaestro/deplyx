import { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  RefreshCw,
  Trash2,
  X,
  ChevronRight,
  ChevronLeft,
  Shield,
  Server,
  Wifi,
  History,
} from 'lucide-react'
import { apiClient } from '../api/client'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart,
  Area,
  ResponsiveContainer,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import {
  Button,
  Card,
  CardHeader,
  CardContent,
  StatusBadge,
  StatusLED,
  Skeleton,
  EmptyState,
  Input,
  Select,
  Label,
} from '../components/ui'

type Connector = {
  id: number
  name: string
  connector_type: string
  sync_mode: string
  sync_interval_minutes: number
  status: string
  last_sync_at: string | null
  last_error: string | null
  created_at: string
}

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06 } }),
}

/* Vendor icons mapping */
const VENDOR_ICON: Record<string, typeof Shield> = {
  paloalto: Shield,
  fortinet: Shield,
  checkpoint: Shield,
  cisco: Wifi,
  juniper: Server,
}

const VENDOR_COLOR: Record<string, string> = {
  paloalto: '#e53935',
  fortinet: '#e53935',
  checkpoint: '#e8308c',
  cisco: '#1ba0d8',
  juniper: '#4caf50',
}

/* Connectors that use SSH (username/password) vs API key */
const SSH_CONNECTORS = new Set(['cisco', 'juniper'])

/* Mock sparkline data for sync history */
function useSyncSparkline() {
  return useMemo(
    () => Array.from({ length: 7 }, (_, i) => ({ v: Math.round(40 + Math.random() * 50 + i * 2) })),
    [],
  )
}

function ConnectorSparkline({ color }: { color: string }) {
  const data = useSyncSparkline()
  return (
    <div className="h-6 w-16">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 1, right: 1, bottom: 1, left: 1 }}>
          <defs>
            <linearGradient id={`cs-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#cs-${color.replace('#', '')})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function ConnectorsPage() {
  const queryClient = useQueryClient()
  const [showWizard, setShowWizard] = useState(false)
  const [syncLogDrawer, setSyncLogDrawer] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  const { data: connectors = [], isLoading } = useQuery<Connector[]>({
    queryKey: ['connectors'],
    queryFn: () => apiClient.get('/connectors').then((r) => r.data),
  })

  const syncMut = useMutation({
    mutationFn: (id: number) => apiClient.post(`/connectors/${id}/sync`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/connectors/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => apiClient.post('/connectors', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
      setShowWizard(false)
    },
  })

  const bulkSync = useCallback(() => {
    selectedIds.forEach((id) => syncMut.mutate(id))
    setSelectedIds(new Set())
  }, [selectedIds, syncMut])

  const toggleSelect = useCallback(
    (id: number) =>
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.has(id) ? next.delete(id) : next.add(id)
        return next
      }),
    [],
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button onClick={() => setShowWizard(true)}>
          <Plus className="h-4 w-4" />
          Add Connector
        </Button>
        <Button
          variant="secondary"
          onClick={() => connectors.forEach((c) => syncMut.mutate(c.id))}
          disabled={syncMut.isPending || connectors.length === 0}
        >
          <RefreshCw className={`h-4 w-4 ${syncMut.isPending ? 'animate-spin' : ''}`} />
          {syncMut.isPending ? 'Syncing…' : 'Sync All'}
        </Button>
        {selectedIds.size > 0 && (
          <Button variant="secondary" size="sm" onClick={bulkSync}>
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
            Bulk Sync ({selectedIds.size})
          </Button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent>
                <Skeleton className="mb-3 h-5 w-32" />
                <Skeleton className="mb-2 h-3 w-20" />
                <Skeleton className="mb-2 h-3 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </CardContent>
            </Card>
          ))
        ) : connectors.length === 0 ? (
          <div className="col-span-full">
            <EmptyState title="No connectors configured" description="Add a connector to sync your network infrastructure." />
          </div>
        ) : (
          connectors.map((c, i) => {
            const VendorIcon = VENDOR_ICON[c.connector_type] ?? Server
            const vendorColor = VENDOR_COLOR[c.connector_type] ?? '#6366f1'
            return (
              <motion.div key={c.id} variants={fadeUp} initial="hidden" animate="visible" custom={i}>
                <Card hover>
                  <CardContent>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2.5">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(c.id)}
                          onChange={() => toggleSelect(c.id)}
                          className="rounded border-slate-300 dark:border-slate-600 h-3.5 w-3.5"
                        />
                        <div
                          className="rounded-lg p-2"
                          style={{ backgroundColor: `${vendorColor}15` }}
                        >
                          <VendorIcon className="h-4 w-4" style={{ color: vendorColor }} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-slate-800 dark:text-slate-100">{c.name}</h3>
                          <p className="text-[10px] text-slate-400 uppercase tracking-wider">{c.connector_type}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <StatusLED
                          status={c.status === 'active' ? 'active' : c.status === 'error' ? 'error' : 'syncing'}
                        />
                        <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400">{c.status}</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between mb-3">
                      <div className="text-xs text-slate-500 dark:text-slate-400 space-y-0.5">
                        <p>Mode: {c.sync_mode} &middot; Every {c.sync_interval_minutes}m</p>
                        <p>
                          Last sync:{' '}
                          {c.last_sync_at
                            ? formatDistanceToNow(new Date(c.last_sync_at), { addSuffix: true })
                            : 'Never'}
                        </p>
                      </div>
                      <ConnectorSparkline color={vendorColor} />
                    </div>

                    {c.last_error && (
                      <p className="mb-3 text-xs text-red-500 dark:text-red-400 truncate">Error: {c.last_error}</p>
                    )}

                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={() => syncMut.mutate(c.id)}
                        disabled={syncMut.isPending}
                        loading={syncMut.isPending && syncMut.variables === c.id}
                      >
                        <RefreshCw className={`h-3 w-3 ${syncMut.isPending && syncMut.variables === c.id ? 'animate-spin' : ''}`} />
                        {syncMut.isPending && syncMut.variables === c.id ? 'Syncing…' : 'Sync Now'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => setSyncLogDrawer(c.id)}
                      >
                        <History className="h-3 w-3" />
                        Log
                      </Button>
                      <Button
                        variant="danger"
                        size="xs"
                        onClick={() => deleteMut.mutate(c.id)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })
        )}
      </div>

      {/* Sync Log Drawer */}
      <AnimatePresence>
        {syncLogDrawer !== null && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => setSyncLogDrawer(null)}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="fixed right-0 top-0 z-50 h-full w-full max-w-md overflow-y-auto bg-white dark:bg-surface-dark-secondary border-l border-slate-200 dark:border-slate-700 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-white">
                  Sync History
                </h2>
                <button
                  onClick={() => setSyncLogDrawer(null)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Sync history for connector #{syncLogDrawer}. Log data will appear here when the backend endpoint is available.
                </p>
                <div className="mt-4 space-y-3">
                  {[1, 2, 3].map((n) => (
                    <div
                      key={n}
                      className="flex items-center gap-3 rounded-lg border border-slate-200 dark:border-slate-700 p-3"
                    >
                      <StatusLED status="active" />
                      <div className="text-sm text-slate-600 dark:text-slate-300">
                        <p className="font-medium">Sync #{n}</p>
                        <p className="text-[10px] text-slate-400">Mock entry — {n * 15}m ago</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Create Wizard Drawer */}
      <AnimatePresence>
        {showWizard && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => setShowWizard(false)}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-y-auto bg-white dark:bg-surface-dark-secondary border-l border-slate-200 dark:border-slate-700 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-white">
                  Add Connector
                </h2>
                <button
                  onClick={() => setShowWizard(false)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6">
                <ConnectorWizard
                  onSubmit={(b) => createMut.mutate(b)}
                  loading={createMut.isPending}
                />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ---------- Multi-step Connector Wizard ---------- */
function ConnectorWizard({
  onSubmit,
  loading,
}: {
  onSubmit: (b: Record<string, unknown>) => void
  loading: boolean
}) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [type, setType] = useState('paloalto')
  const [host, setHost] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const isSSH = SSH_CONNECTORS.has(type)
  const steps = ['Type & Name', 'Connection']
  const canNext = step === 0 ? name.trim() !== '' : host.trim() !== '' && (isSSH ? username.trim() !== '' : true)

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-3">
        {steps.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                i === step
                  ? 'bg-brand-600 text-white'
                  : i < step
                    ? 'bg-brand-100 dark:bg-brand-900/30 text-brand-600'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-400'
              }`}
            >
              {i + 1}
            </div>
            <span className={`text-xs font-medium ${i === step ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400'}`}>
              {s}
            </span>
            {i < steps.length - 1 && <div className="mx-1 h-px w-6 bg-slate-200 dark:bg-slate-700" />}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.div key="s0" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-4">
            <div>
              <Label htmlFor="wiz-name">Name</Label>
              <Input id="wiz-name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="wiz-type">Type</Label>
              <Select id="wiz-type" value={type} onChange={(e) => setType(e.target.value)}>
                <option value="paloalto">Palo Alto</option>
                <option value="fortinet">Fortinet</option>
                <option value="checkpoint">Check Point</option>
                <option value="cisco">Cisco (SSH)</option>
                <option value="juniper">Juniper (SSH)</option>
              </Select>
            </div>
          </motion.div>
        )}
        {step === 1 && (
          <motion.div key="s1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="space-y-4">
            <div>
              <Label htmlFor="wiz-host">Host / IP Address</Label>
              <Input id="wiz-host" placeholder={isSSH ? '10.100.0.20' : 'https://10.100.0.10'} value={host} onChange={(e) => setHost(e.target.value)} />
            </div>
            {isSSH ? (
              <>
                <div>
                  <Label htmlFor="wiz-user">Username</Label>
                  <Input id="wiz-user" placeholder="admin" value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="wiz-pass">Password</Label>
                  <Input id="wiz-pass" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
              </>
            ) : type === 'checkpoint' ? (
              <>
                <div>
                  <Label htmlFor="wiz-user">Username</Label>
                  <Input id="wiz-user" placeholder="admin" value={username} onChange={(e) => setUsername(e.target.value)} />
                </div>
                <div>
                  <Label htmlFor="wiz-pass">Password</Label>
                  <Input id="wiz-pass" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
                </div>
              </>
            ) : (
              <div>
                <Label htmlFor="wiz-key">API Key / Token</Label>
                <Input id="wiz-key" type="password" placeholder="API key or token" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center justify-between pt-2">
        <Button variant="ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
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
            onClick={() => onSubmit({
              name,
              connector_type: type,
              config: isSSH || type === 'checkpoint'
                ? { host, username, password }
                : { host, api_key: apiKey },
            })}
          >
            Create
          </Button>
        )}
      </div>
    </div>
  )
}
