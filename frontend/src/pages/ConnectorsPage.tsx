import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
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
  CheckCircle2,
  AlertCircle,
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
  discoveryApi,
  type DiscoveryEvidence,
  type DiscoveryResult,
  type DiscoverySession,
  type DiscoverySessionDetail,
} from '../api/discovery'
import {
  Button,
  Badge,
  Card,
  CardHeader,
  CardContent,
  CodeBlock,
  StatusBadge,
  StatusLED,
  Skeleton,
  EmptyState,
  Input,
  Select,
  Label,
  Textarea,
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
  'cisco-ftd': Shield,
  cisco: Wifi,
  juniper: Server,
}

const VENDOR_COLOR: Record<string, string> = {
  paloalto: '#e53935',
  fortinet: '#e53935',
  checkpoint: '#e8308c',
  'cisco-ftd': '#1ba0d8',
  cisco: '#1ba0d8',
  juniper: '#4caf50',
}

/* Connectors that use SSH (username/password) vs API key */
const SSH_CONNECTORS = new Set(['cisco', 'cisco-ftd', 'juniper'])
const APP_CONNECTORS = new Set(['elasticsearch', 'grafana', 'nginx', 'openldap', 'postgres', 'prometheus', 'redis'])

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
  const [discoveryName, setDiscoveryName] = useState('')
  const [discoveryTargets, setDiscoveryTargets] = useState('')
  const [discoveryCidrs, setDiscoveryCidrs] = useState('')
  const [discoveryTimeout, setDiscoveryTimeout] = useState('3')
  const [activeDiscoverySessionId, setActiveDiscoverySessionId] = useState<number | null>(null)
  const [discoverySearch, setDiscoverySearch] = useState('')
  const [discoveryStatusFilter, setDiscoveryStatusFilter] = useState<'all' | 'reachable' | 'unreachable'>('all')
  const [discoveryEvidenceFilter, setDiscoveryEvidenceFilter] = useState<'all' | 'service' | 'ssh' | 'api' | 'snmp' | 'bootstrap-ready'>('all')
  const [selectedDiscoveryResultIds, setSelectedDiscoveryResultIds] = useState<Set<number>>(new Set())
  const [discoveryConnectorOverrides, setDiscoveryConnectorOverrides] = useState<Record<number, string>>({})

  const { data: connectors = [], isLoading } = useQuery<Connector[]>({
    queryKey: ['connectors'],
    queryFn: () => apiClient.get('/connectors').then((r) => r.data),
  })

  const { data: discoverySessions = [], isLoading: isDiscoveryLoading } = useQuery<DiscoverySession[]>({
    queryKey: ['discovery-sessions'],
    queryFn: discoveryApi.listSessions,
    staleTime: 15_000,
  })

  const { data: activeDiscoverySession, isLoading: isDiscoverySessionLoading } = useQuery<DiscoverySessionDetail>({
    queryKey: ['discovery-session', activeDiscoverySessionId],
    queryFn: () => discoveryApi.getSession(activeDiscoverySessionId as number),
    enabled: activeDiscoverySessionId !== null,
  })

  useEffect(() => {
    if (!activeDiscoverySession) {
      setSelectedDiscoveryResultIds(new Set())
      setDiscoveryConnectorOverrides({})
      return
    }

    setSelectedDiscoveryResultIds(
      new Set(
        activeDiscoverySession.results
          .filter((result) => result.status === 'reachable')
          .map((result) => result.id),
      ),
    )

    setDiscoveryConnectorOverrides(
      Object.fromEntries(
        activeDiscoverySession.results
          .filter((result) => Boolean(result.selected_connector_type))
          .map((result) => [result.id, result.selected_connector_type as string]),
      ),
    )
  }, [activeDiscoverySession])

  /* ─── Per-connector sync state ─── */
  type SyncState = { phase: 'syncing' | 'done' | 'error'; startedAt: number; error?: string }
  const [syncStates, setSyncStates] = useState<Record<number, SyncState>>({})
  const syncTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  /* ─── Parallel sync queue (backend semaphore throttles to 5 concurrent) ─── */
  const syncQueue = useRef<number[]>([])
  const isProcessingQueue = useRef(false)

  const processQueue = useCallback(async () => {
    if (isProcessingQueue.current) return
    isProcessingQueue.current = true

    // Drain the queue into a local array and fire all at once
    const ids = [...syncQueue.current]
    syncQueue.current = []

    await Promise.allSettled(
      ids.map(async (id) => {
        clearTimeout(syncTimers.current[id])
        setSyncStates((prev) => ({ ...prev, [id]: { phase: 'syncing', startedAt: Date.now() } }))
        try {
          await apiClient.post(`/connectors/${id}/sync`)
          setSyncStates((prev) => ({ ...prev, [id]: { phase: 'done', startedAt: prev[id]?.startedAt ?? Date.now() } }))
          queryClient.invalidateQueries({ queryKey: ['connectors'] })
          syncTimers.current[id] = setTimeout(() => {
            setSyncStates((prev) => {
              const next = { ...prev }
              delete next[id]
              return next
            })
          }, 8_000)
        } catch (err: any) {
          const msg = err?.response?.data?.detail ?? err?.message ?? 'Sync failed'
          setSyncStates((prev) => ({ ...prev, [id]: { phase: 'error', startedAt: prev[id]?.startedAt ?? Date.now(), error: msg } }))
          queryClient.invalidateQueries({ queryKey: ['connectors'] })
        }
      }),
    )

    isProcessingQueue.current = false
  }, [queryClient])

  const startSync = useCallback(
    (id: number) => {
      // Clear any lingering "done" timer
      clearTimeout(syncTimers.current[id])
      setSyncStates((prev) => ({ ...prev, [id]: { phase: 'syncing', startedAt: Date.now() } }))

      apiClient
        .post(`/connectors/${id}/sync`)
        .then(() => {
          setSyncStates((prev) => ({ ...prev, [id]: { phase: 'done', startedAt: prev[id]?.startedAt ?? Date.now() } }))
          queryClient.invalidateQueries({ queryKey: ['connectors'] })
          // Auto-clear the "done" badge after 8s
          syncTimers.current[id] = setTimeout(() => {
            setSyncStates((prev) => {
              const next = { ...prev }
              delete next[id]
              return next
            })
          }, 8_000)
        })
        .catch((err) => {
          const msg = err?.response?.data?.detail ?? err?.message ?? 'Sync failed'
          setSyncStates((prev) => ({ ...prev, [id]: { phase: 'error', startedAt: prev[id]?.startedAt ?? Date.now(), error: msg } }))
          queryClient.invalidateQueries({ queryKey: ['connectors'] })
        })
    },
    [queryClient],
  )

  const isSyncingAny = Object.values(syncStates).some((s) => s.phase === 'syncing')

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

  const createDiscoveryMut = useMutation({
    mutationFn: discoveryApi.createSession,
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['discovery-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['discovery-session', session.id] })
      setActiveDiscoverySessionId(session.id)
      setDiscoveryName('')
      setDiscoveryTargets('')
      setDiscoveryCidrs('')
    },
  })

  const bootstrapDiscoveryMut = useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: number; payload: Parameters<typeof discoveryApi.bootstrapSession>[1] }) =>
      discoveryApi.bootstrapSession(sessionId, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
      queryClient.invalidateQueries({ queryKey: ['discovery-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['discovery-session', variables.sessionId] })
    },
  })

  const startSyncAll = useCallback(() => {
    // Queue all connectors for sequential processing
    syncQueue.current = connectors.map((c) => c.id)
    // Mark them all as syncing right away for UI feedback
    setSyncStates((prev) => {
      const next = { ...prev }
      for (const c of connectors) {
        next[c.id] = { phase: 'syncing', startedAt: Date.now() }
      }
      return next
    })
    processQueue()
  }, [connectors, processQueue])

  const bulkSync = useCallback(() => {
    // Queue selected IDs for sequential processing
    syncQueue.current = [...selectedIds]
    setSyncStates((prev) => {
      const next = { ...prev }
      for (const id of selectedIds) {
        next[id] = { phase: 'syncing', startedAt: Date.now() }
      }
      return next
    })
    setSelectedIds(new Set())
    processQueue()
  }, [selectedIds, processQueue])

  const toggleSelect = useCallback(
    (id: number) =>
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.has(id) ? next.delete(id) : next.add(id)
        return next
      }),
    [],
  )

  const handleStartDiscovery = useCallback(() => {
    const targets = parseDiscoveryList(discoveryTargets)
    const cidrs = parseDiscoveryList(discoveryCidrs)
    createDiscoveryMut.mutate({
      name: discoveryName.trim() || undefined,
      targets,
      cidrs,
      timeout_seconds: Number.parseInt(discoveryTimeout, 10) || 3,
    })
  }, [createDiscoveryMut, discoveryCidrs, discoveryName, discoveryTargets, discoveryTimeout])

  const discoveryCanSubmit =
    parseDiscoveryList(discoveryTargets).length > 0 || parseDiscoveryList(discoveryCidrs).length > 0

  const filteredDiscoveryResults = useMemo(() => {
    const results = activeDiscoverySession?.results ?? []
    const normalizedSearch = discoverySearch.trim().toLowerCase()

    return results.filter((result) => {
      const evidence = getDiscoveryEvidence(result)
      const matchesSearch =
        normalizedSearch.length === 0 ||
        result.host.toLowerCase().includes(normalizedSearch) ||
        (result.name_hint ?? '').toLowerCase().includes(normalizedSearch) ||
        result.suggested_connector_types.some((value) => value.toLowerCase().includes(normalizedSearch))

      const matchesStatus =
        discoveryStatusFilter === 'all' || result.status === discoveryStatusFilter

      const matchesEvidence =
        discoveryEvidenceFilter === 'all' ||
        (discoveryEvidenceFilter === 'service' && Boolean(evidence.service_detected)) ||
        (discoveryEvidenceFilter === 'ssh' && Boolean(evidence.ssh_manageable)) ||
        (discoveryEvidenceFilter === 'api' && Boolean(evidence.api_manageable)) ||
        (discoveryEvidenceFilter === 'snmp' && Boolean(evidence.snmp_identified)) ||
        (discoveryEvidenceFilter === 'bootstrap-ready' && isBootstrapReady(result, discoveryConnectorOverrides[result.id]))

      return matchesSearch && matchesStatus && matchesEvidence
    })
  }, [activeDiscoverySession, discoveryConnectorOverrides, discoveryEvidenceFilter, discoverySearch, discoveryStatusFilter])

  const selectedDiscoveryItems = useMemo(
    () => filteredDiscoveryResults.filter((result) => selectedDiscoveryResultIds.has(result.id)),
    [filteredDiscoveryResults, selectedDiscoveryResultIds],
  )

  const discoverySelectionStats = useMemo(() => {
    const selected = activeDiscoverySession?.results.filter((result) => selectedDiscoveryResultIds.has(result.id)) ?? []
    const ready = selected.filter((result) => isBootstrapReady(result, discoveryConnectorOverrides[result.id])).length
    return {
      selected: selected.length,
      ready,
    }
  }, [activeDiscoverySession, discoveryConnectorOverrides, selectedDiscoveryResultIds])

  const toggleDiscoveryResultSelection = useCallback((resultId: number) => {
    setSelectedDiscoveryResultIds((prev) => {
      const next = new Set(prev)
      if (next.has(resultId)) {
        next.delete(resultId)
      } else {
        next.add(resultId)
      }
      return next
    })
  }, [])

  const setDiscoveryOverride = useCallback((resultId: number, connectorType: string) => {
    setDiscoveryConnectorOverrides((prev) => {
      if (!connectorType) {
        const next = { ...prev }
        delete next[resultId]
        return next
      }
      return { ...prev, [resultId]: connectorType }
    })
  }, [])

  const selectFilteredDiscoveryResults = useCallback(() => {
    setSelectedDiscoveryResultIds(new Set(filteredDiscoveryResults.map((result) => result.id)))
  }, [filteredDiscoveryResults])

  const clearDiscoverySelection = useCallback(() => {
    setSelectedDiscoveryResultIds(new Set())
  }, [])

  const handleBootstrapSelected = useCallback(() => {
    if (activeDiscoverySessionId === null || selectedDiscoveryResultIds.size === 0) {
      return
    }

    const payloadItems = [...selectedDiscoveryResultIds].map((resultId) => ({
      result_id: resultId,
      connector_type: discoveryConnectorOverrides[resultId] || undefined,
      run_sync: true,
    }))

    bootstrapDiscoveryMut.mutate({
      sessionId: activeDiscoverySessionId,
      payload: {
        run_sync: true,
        items: payloadItems,
      },
    })
  }, [activeDiscoverySessionId, bootstrapDiscoveryMut, discoveryConnectorOverrides, selectedDiscoveryResultIds])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button onClick={() => setShowWizard(true)}>
          <Plus className="h-4 w-4" />
          Add Connector
        </Button>
        <Button
          variant="secondary"
          onClick={startSyncAll}
          disabled={isSyncingAny || connectors.length === 0}
        >
          <RefreshCw className={`h-4 w-4 ${isSyncingAny ? 'animate-spin' : ''}`} />
          {isSyncingAny ? 'Syncing…' : 'Sync All'}
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

                    {c.last_error && !syncStates[c.id] && (
                      <p className="mb-3 text-xs text-red-500 dark:text-red-400 truncate">Error: {c.last_error}</p>
                    )}

                    {/* Per-connector sync progress indicator */}
                    {syncStates[c.id] && (
                      <div className="mb-3">
                        {syncStates[c.id].phase === 'syncing' && (
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                              <motion.div
                                className="h-full rounded-full bg-brand-500"
                                initial={{ width: '5%' }}
                                animate={{ width: '90%' }}
                                transition={{ duration: 12, ease: 'easeOut' }}
                              />
                            </div>
                            <span className="text-[10px] font-medium text-brand-600 dark:text-brand-400 whitespace-nowrap">
                              Syncing…
                            </span>
                          </div>
                        )}
                        {syncStates[c.id].phase === 'done' && (
                          <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span className="text-xs font-medium">Sync complete</span>
                          </div>
                        )}
                        {syncStates[c.id].phase === 'error' && (
                          <div className="flex items-center gap-1.5 text-red-500 dark:text-red-400">
                            <AlertCircle className="h-3.5 w-3.5" />
                            <span className="text-xs font-medium truncate">{syncStates[c.id].error}</span>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={() => startSync(c.id)}
                        disabled={syncStates[c.id]?.phase === 'syncing'}
                      >
                        <RefreshCw className={`h-3 w-3 ${syncStates[c.id]?.phase === 'syncing' ? 'animate-spin' : ''}`} />
                        {syncStates[c.id]?.phase === 'syncing' ? 'Syncing…' : 'Sync Now'}
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

      <div className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              Discovery Sessions
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Run deterministic discovery, inspect suggested connector types, and review probe reasons before bootstrap.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['discovery-sessions'] })}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh Sessions
          </Button>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
          <Card>
            <CardHeader title="Start Discovery" />
            <CardContent>
              <div className="space-y-4">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Enter explicit targets or CIDRs. Results will show suggested connector types and the exact probe evidence used.
                </p>
                <div>
                  <Label htmlFor="discovery-name">Session Name</Label>
                  <Input
                    id="discovery-name"
                    placeholder="Edge scan, DC audit, branch inventory"
                    value={discoveryName}
                    onChange={(e) => setDiscoveryName(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="discovery-targets">Targets</Label>
                  <Textarea
                    id="discovery-targets"
                    rows={4}
                    placeholder="192.168.1.10&#10;fw-edge-01.local"
                    value={discoveryTargets}
                    onChange={(e) => setDiscoveryTargets(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="discovery-cidrs">CIDRs</Label>
                  <Textarea
                    id="discovery-cidrs"
                    rows={3}
                    placeholder="192.168.1.0/30"
                    value={discoveryCidrs}
                    onChange={(e) => setDiscoveryCidrs(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="discovery-timeout">Timeout (seconds)</Label>
                  <Input
                    id="discovery-timeout"
                    type="number"
                    min={1}
                    max={15}
                    value={discoveryTimeout}
                    onChange={(e) => setDiscoveryTimeout(e.target.value)}
                  />
                </div>
                {createDiscoveryMut.isError && (
                  <p className="text-sm text-red-500 dark:text-red-400">
                    {extractApiError(createDiscoveryMut.error)}
                  </p>
                )}
                <Button
                  onClick={handleStartDiscovery}
                  loading={createDiscoveryMut.isPending}
                  disabled={!discoveryCanSubmit || createDiscoveryMut.isPending}
                >
                  Start Discovery
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Recent Sessions" />
            <CardContent>
              <div className="space-y-3">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Inspect discovery facts before creating or syncing connectors.
                </p>
                {isDiscoveryLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-700 p-4">
                      <Skeleton className="mb-3 h-5 w-40" />
                      <Skeleton className="mb-2 h-3 w-52" />
                      <Skeleton className="h-3 w-28" />
                    </div>
                  ))
                ) : discoverySessions.length === 0 ? (
                  <EmptyState
                    title="No discovery sessions yet"
                    description="Run a discovery session to inspect deterministic classification evidence before bootstrap."
                  />
                ) : (
                  discoverySessions.map((session) => (
                    <div
                      key={session.id}
                      className="rounded-xl border border-slate-200 dark:border-slate-700 p-4 transition-colors hover:border-brand-300 dark:hover:border-brand-700"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h4 className="font-semibold text-slate-800 dark:text-slate-100">
                            {session.name || `Discovery #${session.id}`}
                          </h4>
                          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                            {formatDiscoverySummary(session)}
                          </p>
                        </div>
                        <DiscoveryStatusBadge status={session.status} />
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                        <span>{session.target_count} targets</span>
                        <span>&middot;</span>
                        <span>{session.ports.join(', ')}</span>
                        <span>&middot;</span>
                        <span>
                          {session.completed_at
                            ? formatDistanceToNow(new Date(session.completed_at), { addSuffix: true })
                            : 'In progress'}
                        </span>
                      </div>

                      {session.last_error && (
                        <p className="mt-3 text-sm text-red-500 dark:text-red-400">
                          {session.last_error}
                        </p>
                      )}

                      <div className="mt-4 flex gap-2">
                        <Button
                          variant="secondary"
                          size="xs"
                          onClick={() => setActiveDiscoverySessionId(session.id)}
                        >
                          Inspect Results
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
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

      <AnimatePresence>
        {activeDiscoverySessionId !== null && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => setActiveDiscoverySessionId(null)}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="fixed right-0 top-0 z-50 h-full w-full max-w-3xl overflow-y-auto bg-white dark:bg-surface-dark-secondary border-l border-slate-200 dark:border-slate-700 shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 px-6 py-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-800 dark:text-white">
                    {activeDiscoverySession?.name || `Discovery #${activeDiscoverySessionId}`}
                  </h2>
                  {activeDiscoverySession && (
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      {formatDiscoverySummary(activeDiscoverySession)}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      queryClient.invalidateQueries({
                        queryKey: ['discovery-session', activeDiscoverySessionId],
                      })
                    }
                  >
                    <RefreshCw className="h-4 w-4" />
                    Refresh
                  </Button>
                  <Button
                    size="sm"
                    loading={bootstrapDiscoveryMut.isPending}
                    disabled={
                      !activeDiscoverySession ||
                      activeDiscoverySession.status !== 'completed' ||
                      discoverySelectionStats.selected === 0
                    }
                    onClick={handleBootstrapSelected}
                  >
                    Bootstrap Selected ({discoverySelectionStats.selected})
                  </Button>
                  <button
                    onClick={() => setActiveDiscoverySessionId(null)}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-6">
                {bootstrapDiscoveryMut.isError && (
                  <p className="text-sm text-red-500 dark:text-red-400">
                    {extractApiError(bootstrapDiscoveryMut.error)}
                  </p>
                )}

                {isDiscoverySessionLoading || !activeDiscoverySession ? (
                  <div className="space-y-4">
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-40 w-full" />
                    <Skeleton className="h-40 w-full" />
                  </div>
                ) : (
                  <>
                    <Card>
                      <CardContent>
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                          <DiscoveryMetric label="Status" value={activeDiscoverySession.status} />
                          <DiscoveryMetric label="Targets" value={String(activeDiscoverySession.target_count)} />
                          <DiscoveryMetric label="Ports" value={activeDiscoverySession.ports.join(', ')} />
                          <DiscoveryMetric
                            label="Completed"
                            value={
                              activeDiscoverySession.completed_at
                                ? formatDistanceToNow(new Date(activeDiscoverySession.completed_at), { addSuffix: true })
                                : 'In progress'
                            }
                          />
                        </div>
                        {activeDiscoverySession.summary && (
                          <div className="mt-4 grid gap-3 md:grid-cols-2">
                            <CodeBlock language="summary">
                              {JSON.stringify(activeDiscoverySession.summary, null, 2)}
                            </CodeBlock>
                            <CodeBlock language="input">
                              {JSON.stringify(activeDiscoverySession.input_payload, null, 2)}
                            </CodeBlock>
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    <Card>
                      <CardContent>
                        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_repeat(3,minmax(0,0.55fr))]">
                          <div>
                            <Label htmlFor="discovery-search">Filter Results</Label>
                            <Input
                              id="discovery-search"
                              placeholder="Host, name hint, connector type"
                              value={discoverySearch}
                              onChange={(e) => setDiscoverySearch(e.target.value)}
                            />
                          </div>
                          <div>
                            <Label htmlFor="discovery-status-filter">Reachability</Label>
                            <Select
                              id="discovery-status-filter"
                              value={discoveryStatusFilter}
                              onChange={(e) => setDiscoveryStatusFilter(e.target.value as 'all' | 'reachable' | 'unreachable')}
                            >
                              <option value="all">All</option>
                              <option value="reachable">Reachable</option>
                              <option value="unreachable">Unreachable</option>
                            </Select>
                          </div>
                          <div>
                            <Label htmlFor="discovery-evidence-filter">Evidence</Label>
                            <Select
                              id="discovery-evidence-filter"
                              value={discoveryEvidenceFilter}
                              onChange={(e) =>
                                setDiscoveryEvidenceFilter(
                                  e.target.value as 'all' | 'service' | 'ssh' | 'api' | 'snmp' | 'bootstrap-ready',
                                )
                              }
                            >
                              <option value="all">All</option>
                              <option value="service">Service Detected</option>
                              <option value="ssh">SSH Confirmed</option>
                              <option value="api">API Confirmed</option>
                              <option value="snmp">SNMP Identified</option>
                              <option value="bootstrap-ready">Bootstrap Ready</option>
                            </Select>
                          </div>
                          <div className="rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3">
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                              Selection
                            </p>
                            <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                              {discoverySelectionStats.ready}/{discoverySelectionStats.selected} ready
                            </p>
                          </div>
                        </div>

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          <Button variant="secondary" size="xs" onClick={selectFilteredDiscoveryResults}>
                            Select Filtered ({filteredDiscoveryResults.length})
                          </Button>
                          <Button variant="ghost" size="xs" onClick={clearDiscoverySelection}>
                            Clear Selection
                          </Button>
                          <Badge color="neutral">Visible: {filteredDiscoveryResults.length}</Badge>
                          <Badge color={discoverySelectionStats.ready === discoverySelectionStats.selected && discoverySelectionStats.selected > 0 ? 'success' : 'warning'}>
                            Ready: {discoverySelectionStats.ready}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>

                    <div className="space-y-3">
                      {filteredDiscoveryResults.length === 0 ? (
                        <EmptyState
                          title="No results match the current filters"
                          description="Adjust the reachability, evidence, or search filters to inspect other discovery results."
                        />
                      ) : (
                        filteredDiscoveryResults.map((result) => (
                          <DiscoveryResultCard
                            key={result.id}
                            result={result}
                            isSelected={selectedDiscoveryResultIds.has(result.id)}
                            overrideConnectorType={discoveryConnectorOverrides[result.id]}
                            onToggleSelected={toggleDiscoveryResultSelection}
                            onOverrideConnectorType={setDiscoveryOverride}
                          />
                        ))
                      )}
                    </div>
                  </>
                )}
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

function DiscoveryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-sm font-medium text-slate-700 dark:text-slate-200">
        {value}
      </p>
    </div>
  )
}

function DiscoveryStatusBadge({ status }: { status: string }) {
  const color =
    status === 'completed'
      ? 'success'
      : status === 'running'
        ? 'info'
        : status === 'error'
          ? 'critical'
          : 'neutral'

  return <Badge color={color}>{status}</Badge>
}

function DiscoveryEvidenceBadge({ label, active }: { label: string; active: boolean }) {
  return <Badge color={active ? 'success' : 'neutral'}>{label}: {active ? 'yes' : 'no'}</Badge>
}

function DiscoveryResultCard({
  result,
  isSelected,
  overrideConnectorType,
  onToggleSelected,
  onOverrideConnectorType,
}: {
  result: DiscoveryResult
  isSelected: boolean
  overrideConnectorType?: string
  onToggleSelected: (resultId: number) => void
  onOverrideConnectorType: (resultId: number, connectorType: string) => void
}) {
  const evidence = getDiscoveryEvidence(result)
  const connectorOptions = getDiscoveryConnectorOptions(result)
  const effectiveConnectorType = overrideConnectorType || result.selected_connector_type || ''
  const bootstrapReady = isBootstrapReady(result, overrideConnectorType)
  const serviceOnlyAppSignal =
    Boolean(evidence.service_detected) &&
    !Boolean(evidence.ssh_manageable) &&
    !Boolean(evidence.api_manageable) &&
    !Boolean(evidence.snmp_identified) &&
    result.suggested_connector_types.some((connectorType) => APP_CONNECTORS.has(connectorType))

  return (
    <Card>
      <CardContent>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelected(result.id)}
              className="mt-1 h-4 w-4 rounded border-slate-300 dark:border-slate-600"
            />
            <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-slate-800 dark:text-slate-100">{result.host}</h3>
              <DiscoveryStatusBadge status={result.status} />
              <Badge color="neutral">{result.source_kind}</Badge>
              {result.selected_connector_type && <Badge color="info">detected: {result.selected_connector_type}</Badge>}
              {overrideConnectorType && overrideConnectorType !== result.selected_connector_type && (
                <Badge color="warning">override: {overrideConnectorType}</Badge>
              )}
            </div>
            {result.name_hint && (
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{result.name_hint}</p>
            )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            {result.suggested_connector_types.map((connectorType) => (
              <Badge key={connectorType} color={connectorType === result.selected_connector_type ? 'success' : 'purple'}>
                {connectorType}
              </Badge>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <DiscoveryMetric label="Preflight" value={result.preflight_status} />
          <DiscoveryMetric label="Bootstrap" value={result.bootstrap_status} />
          <DiscoveryMetric
            label="Bootstrap Ready"
            value={bootstrapReady ? 'ready' : 'needs selection'}
          />
          <DiscoveryMetric
            label="Connector"
            value={result.connector_name || effectiveConnectorType || 'Not selected'}
          />
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(240px,300px)]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Evidence States
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <DiscoveryEvidenceBadge label="Service Detected" active={Boolean(evidence.service_detected)} />
              <DiscoveryEvidenceBadge label="SSH Confirmed" active={Boolean(evidence.ssh_manageable)} />
              <DiscoveryEvidenceBadge label="API Confirmed" active={Boolean(evidence.api_manageable)} />
              <DiscoveryEvidenceBadge label="SNMP Identified" active={Boolean(evidence.snmp_identified)} />
            </div>
            {serviceOnlyAppSignal && (
              <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
                Service detection is present, but SSH, API, and SNMP confirmation are still absent. Bootstrap remains allowed, but manageability is not yet confirmed.
              </p>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-700 p-4">
            <Label htmlFor={`discovery-override-${result.id}`}>Connector Override</Label>
            <Select
              id={`discovery-override-${result.id}`}
              value={effectiveConnectorType}
              onChange={(e) => onOverrideConnectorType(result.id, e.target.value)}
            >
              <option value="">Use detected selection</option>
              {connectorOptions.map((connectorType) => (
                <option key={connectorType} value={connectorType}>
                  {connectorType}
                </option>
              ))}
            </Select>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Use this when discovery suggested multiple connector types and you want bootstrap to create only the chosen connector.
            </p>
          </div>
        </div>

        {result.classification_reasons.length > 0 && (
          <div className="mt-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Classification Reasons
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {result.classification_reasons.map((reason) => (
                <Badge key={reason} color="neutral" className="max-w-full whitespace-normal text-left">
                  {reason}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {result.error && (
          <p className="mt-4 text-sm text-red-500 dark:text-red-400">{result.error}</p>
        )}

        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          <CodeBlock language="probe detail">
            {JSON.stringify(result.probe_detail, null, 2)}
          </CodeBlock>
          <CodeBlock language="facts">
            {JSON.stringify(result.facts, null, 2)}
          </CodeBlock>
        </div>
      </CardContent>
    </Card>
  )
}

function parseDiscoveryList(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean)
}

function getDiscoveryEvidence(result: DiscoveryResult): DiscoveryEvidence {
  return ((result.facts.evidence as DiscoveryEvidence | undefined) ?? {})
}

function getDiscoveryConnectorOptions(result: DiscoveryResult): string[] {
  const values = new Set<string>()
  if (result.selected_connector_type) {
    values.add(result.selected_connector_type)
  }
  result.suggested_connector_types.forEach((connectorType) => values.add(connectorType))
  return [...values]
}

function isBootstrapReady(result: DiscoveryResult, overrideConnectorType?: string): boolean {
  return result.status === 'reachable' && Boolean(overrideConnectorType || result.selected_connector_type)
}

function extractApiError(error: unknown): string {
  const maybeAxios = error as { response?: { data?: { detail?: string } }; message?: string }
  return maybeAxios.response?.data?.detail || maybeAxios.message || 'Request failed'
}

function formatDiscoverySummary(session: DiscoverySession | DiscoverySessionDetail): string {
  const summary = session.summary || {}
  const reachable = typeof summary.reachable_targets === 'number' ? summary.reachable_targets : 0
  const unreachable = typeof summary.unreachable_targets === 'number' ? summary.unreachable_targets : 0
  return `${reachable} reachable, ${unreachable} unreachable`
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
                <option value="cisco-ftd">Cisco FTD</option>
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
