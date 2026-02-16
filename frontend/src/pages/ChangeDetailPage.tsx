import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Play, Check, X, RotateCcw, Send, Shield, Pencil, AlertTriangle, Layers, Server, Globe, Zap } from 'lucide-react'
import { apiClient } from '../api/client'
import { useAppStore } from '../store/useAppStore'
import { useEffect, useMemo, useState } from 'react'
import ReactFlow, { Background, type Edge, MarkerType, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import { motion } from 'framer-motion'
import {
  Button,
  Card,
  CardHeader,
  CardContent,
  StatusBadge,
  RiskBadge,
  RiskGauge,
  Skeleton,
  Input,
  Textarea,
  Label,
  WorkflowStepper,
  Tabs,
  TabList,
  Tab,
  TabPanel,
  CodeBlock,
} from '../components/ui'
import NodePicker from '../components/NodePicker'

type ChangeDetail = {
  id: string
  title: string
  change_type: string
  action: string | null
  environment: string
  description: string | null
  execution_plan: string | null
  rollback_plan: string | null
  maintenance_window_start: string | null
  maintenance_window_end: string | null
  status: string
  risk_score: number | null
  risk_level: string | null
  reject_reason: string | null
  created_by: number
  created_at: string
  updated_at: string
  impacted_components: { graph_node_id: string; component_type: string; impact_level: string }[]
}

type Approval = {
  id: number
  role_required: string
  status: string
  comment: string | null
  decided_at: string | null
}

type AuditEntry = {
  action: string
  details: Record<string, unknown> | null
  timestamp: string
  user_id: number | null
}

type ImpactEntry = {
  id: string
  label: string
  properties: Record<string, unknown>
}

type ImpactPayload = {
  directly_impacted: ImpactEntry[]
  indirectly_impacted: ImpactEntry[]
  affected_applications: ImpactEntry[]
  affected_services: ImpactEntry[]
  affected_vlans: ImpactEntry[]
  total_dependency_count: number
  max_criticality: string
  traversal_strategy?: string
  llm_powered?: boolean
  critical_paths?: CriticalPath[]
  risk_assessment?: LLMRiskAssessment
  blast_radius?: BlastRadius
  action_analysis?: ActionAnalysis
}

type CriticalPath = {
  source_id: string
  endpoint_id: string
  endpoint_label: string
  criticality: string
  hops: number
  path_description?: string
  nodes: { id: string; label: string }[]
  edges: { type: string; source: string; target: string }[]
  reasoning?: string
}

type LLMRiskAssessment = {
  severity: string
  summary: string
  factors: string[]
  mitigations: string[]
}

type BlastRadius = {
  total_impacted: number
  critical_services_at_risk: string[]
  redundancy_available: boolean
  redundancy_details: string
}

type ActionAnalysis = {
  action: string
  traversal_strategy: string
  explanation: string
}

type ImpactResponse = {
  change_id: string
  impact: ImpactPayload
}

export default function ChangeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAppStore((s) => s.user)
  const [rejectReason, setRejectReason] = useState('')
  const [showReject, setShowReject] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [titleInput, setTitleInput] = useState('')
  const [descriptionInput, setDescriptionInput] = useState('')
  const [executionPlanInput, setExecutionPlanInput] = useState('')
  const [rollbackPlanInput, setRollbackPlanInput] = useState('')
  const [maintenanceStartInput, setMaintenanceStartInput] = useState('')
  const [maintenanceEndInput, setMaintenanceEndInput] = useState('')
  const [targetNodeIds, setTargetNodeIds] = useState<string[]>([])

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

  const { data: change, isLoading } = useQuery<ChangeDetail>({
    queryKey: ['change', id],
    queryFn: () => apiClient.get(`/changes/${id}`).then((r) => r.data),
    enabled: !!id,
  })

  const { data: approvals = [] } = useQuery<Approval[]>({
    queryKey: ['approvals', id],
    queryFn: () => apiClient.get(`/changes/${id}/approvals`).then((r) => r.data),
    enabled: !!id,
  })

  const { data: auditLog = [] } = useQuery<AuditEntry[]>({
    queryKey: ['audit', id],
    queryFn: () => apiClient.get(`/changes/${id}/audit-log`).then((r) => r.data),
    enabled: !!id,
  })

  const { data: impactResponse, isFetching: impactLoading } = useQuery<ImpactResponse>({
    queryKey: ['impact', id],
    queryFn: () => apiClient.get(`/changes/${id}/impact`).then((r) => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 min — impact is cached server-side, no need to refetch
    refetchOnWindowFocus: false,
  })

  const refreshImpactMutation = useMutation({
    mutationFn: () => apiClient.get(`/changes/${id}/impact?refresh=true`).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['impact', id] }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['change', id] })
    queryClient.invalidateQueries({ queryKey: ['approvals', id] })
    queryClient.invalidateQueries({ queryKey: ['audit', id] })
    // Impact is NOT invalidated here — it's cached server-side and only
    // refreshed via the Re-analyze button or after Calculate Risk.
    queryClient.invalidateQueries({ queryKey: ['changes'] })
  }

  useEffect(() => {
    if (!change) return
    setTitleInput(change.title ?? '')
    setDescriptionInput(change.description ?? '')
    setExecutionPlanInput(change.execution_plan ?? '')
    setRollbackPlanInput(change.rollback_plan ?? '')
    setMaintenanceStartInput(change.maintenance_window_start ? toDateTimeLocal(change.maintenance_window_start) : '')
    setMaintenanceEndInput(change.maintenance_window_end ? toDateTimeLocal(change.maintenance_window_end) : '')
    const directTargets = change.impacted_components
      .filter((component) => component.impact_level === 'direct')
      .map((component) => component.graph_node_id)
    setTargetNodeIds(directTargets)
  }, [change])

  const submit = useMutation({
    mutationFn: () => apiClient.post(`/changes/${id}/submit`),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })
  const execute = useMutation({
    mutationFn: () => apiClient.post(`/changes/${id}/execute`),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })
  const complete = useMutation({
    mutationFn: () => apiClient.post(`/changes/${id}/complete`),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })
  const rollback = useMutation({
    mutationFn: () => apiClient.post(`/changes/${id}/rollback`),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })
  const reject = useMutation({
    mutationFn: (reason: string) => apiClient.post(`/changes/${id}/reject`, { reason }),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })
  const calcRisk = useMutation({
    mutationFn: () => apiClient.post('/risk/calculate', { change_id: id }),
    onMutate: () => setActionError(null),
    onSuccess: () => {
      invalidate()
      // Risk calculation runs fresh LLM analysis — refresh the cached impact
      queryClient.invalidateQueries({ queryKey: ['impact', id] })
    },
    onError: (err) => setActionError(parseApiError(err)),
  })

  const approve = useMutation({
    mutationFn: (approvalId: number) =>
      apiClient.post(`/changes/${id}/approvals/${approvalId}`, { status: 'Approved', comment: 'Approved' }),
    onMutate: () => setActionError(null),
    onSuccess: invalidate,
    onError: (err) => setActionError(parseApiError(err)),
  })

  const saveEdits = useMutation({
    mutationFn: () => {
      return apiClient.put(`/changes/${id}`, {
        title: titleInput,
        description: descriptionInput,
        execution_plan: executionPlanInput,
        rollback_plan: rollbackPlanInput,
        maintenance_window_start: maintenanceStartInput ? new Date(maintenanceStartInput).toISOString() : null,
        maintenance_window_end: maintenanceEndInput ? new Date(maintenanceEndInput).toISOString() : null,
        target_components: targetNodeIds,
      })
    },
    onMutate: () => setActionError(null),
    onSuccess: () => {
      setIsEditing(false)
      invalidate()
    },
    onError: (err) => setActionError(parseApiError(err)),
  })

  if (isLoading || !change) {
    return (
      <div className="max-w-4xl space-y-6 py-10">
        <Skeleton variant="text" />
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>
    )
  }

  const isOwner = user?.id === change.created_by
  const isAdmin = user?.role === 'Admin'
  const canEdit = (change.status === 'Draft' || change.status === 'Pending') && (isOwner || isAdmin)
  const impact = impactResponse?.impact

  return (
    <div className="max-w-4xl space-y-6 pb-20">
      {/* Header */}
      <div className="flex items-start gap-3">
        <button onClick={() => navigate('/changes')} className="mt-1 rounded-btn p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary transition-colors">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-slate-800 dark:text-white">{change.title}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 font-mono">
            #{change.id} &middot; {change.change_type}
            {change.action && <> &middot; <span className="text-brand-600 dark:text-brand-400">{change.action.replace(/_/g, ' ')}</span></>}
            {' '}&middot; {change.environment}
          </p>
        </div>
        <StatusBadge status={change.status} />
      </div>

      {/* Workflow Stepper */}
      <Card>
        <CardContent>
          <WorkflowStepper currentStatus={change.status} />
        </CardContent>
      </Card>

      {actionError && (
        <div className="rounded-btn border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-2.5 text-sm text-red-700 dark:text-red-400">
          {actionError}
        </div>
      )}

      {showReject && (
        <Card>
          <CardContent>
            <div className="space-y-3">
              <Label>Reason for Rejection</Label>
              <Textarea placeholder="Reason for rejection" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={2} />
              <div className="flex gap-2">
                <Button variant="danger" size="sm" onClick={() => { reject.mutate(rejectReason); setShowReject(false) }}>
                  Confirm Reject
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setShowReject(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {isEditing && canEdit && (
        <Card>
          <CardHeader title="Edit Change" />
          <CardContent>
            <div className="space-y-4">
              <div>
                <Label>Title</Label>
                <Input value={titleInput} onChange={(e) => setTitleInput(e.target.value)} placeholder="Title" />
              </div>
              <div>
                <Label>Description</Label>
                <Textarea value={descriptionInput} onChange={(e) => setDescriptionInput(e.target.value)} placeholder="Description" rows={2} />
              </div>
              <div>
                <Label>Execution Plan</Label>
                <Textarea value={executionPlanInput} onChange={(e) => setExecutionPlanInput(e.target.value)} placeholder="Execution plan" rows={2} />
              </div>
              <div>
                <Label>Rollback Plan</Label>
                <Textarea value={rollbackPlanInput} onChange={(e) => setRollbackPlanInput(e.target.value)} placeholder="Rollback plan" rows={2} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label>Maintenance Start</Label>
                  <input type="datetime-local" value={maintenanceStartInput} onChange={(e) => setMaintenanceStartInput(e.target.value)} className="w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus-ring" />
                </div>
                <div>
                  <Label>Maintenance End</Label>
                  <input type="datetime-local" value={maintenanceEndInput} onChange={(e) => setMaintenanceEndInput(e.target.value)} className="w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus-ring" />
                </div>
              </div>
              <div>
                <Label>Target Components</Label>
                <NodePicker
                  selected={targetNodeIds}
                  onChange={setTargetNodeIds}
                  placeholder="Search devices, rules, VLANs…"
                />
              </div>
              <Button onClick={() => saveEdits.mutate()} loading={saveEdits.isPending}>
                Save Changes
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabbed content */}
      <Tabs defaultValue="overview">
        <TabList>
          <Tab value="overview">Overview</Tab>
          <Tab value="plans">Plans</Tab>
          <Tab value="impact">Impact</Tab>
          <Tab value="approvals">Approvals & Audit</Tab>
        </TabList>

        {/* --- Overview tab --- */}
        <TabPanel value="overview">
          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader title="Details" />
              <CardContent>
                <Field label="Description" value={change.description} />
                <Field label="Maintenance Window" value={
                  change.maintenance_window_start
                    ? `${new Date(change.maintenance_window_start).toLocaleString()} – ${change.maintenance_window_end ? new Date(change.maintenance_window_end).toLocaleString() : '?'}`
                    : null
                } />
              </CardContent>
            </Card>

            <Card>
              <CardHeader title="Risk Assessment" />
              <CardContent>
                <div className="flex flex-col items-center py-2">
                  <RiskGauge score={change.risk_score} level={change.risk_level} size={130} />
                  {change.risk_score != null && (
                    <div className="mt-3 grid grid-cols-3 gap-3 w-full text-center">
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-800/50 px-2 py-1.5">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500">Score</p>
                        <p className="text-sm font-bold text-slate-700 dark:text-slate-200">{change.risk_score}/100</p>
                      </div>
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-800/50 px-2 py-1.5">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500">Level</p>
                        <p className="mt-0.5"><RiskBadge level={change.risk_level} /></p>
                      </div>
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-800/50 px-2 py-1.5">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500">Impact</p>
                        <p className="text-sm font-bold text-slate-700 dark:text-slate-200">{change.impacted_components.length}</p>
                      </div>
                    </div>
                  )}
                </div>
                {change.reject_reason && (
                  <div className="mt-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-3 py-2 text-sm text-red-700 dark:text-red-400">
                    <strong>Rejected:</strong> {change.reject_reason}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Impacted components */}
          {change.impacted_components.length > 0 && (
            <Card className="mt-6">
              <CardHeader title={`Impacted Components (${change.impacted_components.length})`} />
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {change.impacted_components.map((c, i) => (
                    <span key={i} className={`rounded-btn px-2.5 py-1 text-xs font-medium ${
                      c.impact_level === 'direct'
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                        : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                    }`}>
                      {c.component_type}: {c.graph_node_id} ({c.impact_level})
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabPanel>

        {/* --- Plans tab --- */}
        <TabPanel value="plans">
          <div className="space-y-6">
            <Card>
              <CardHeader title="Execution Plan" />
              <CardContent>
                {change.execution_plan ? (
                  <CodeBlock language="plan">{change.execution_plan}</CodeBlock>
                ) : (
                  <p className="text-sm text-slate-400">No execution plan defined.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader title="Rollback Plan" />
              <CardContent>
                {change.rollback_plan ? (
                  <CodeBlock language="plan">{change.rollback_plan}</CodeBlock>
                ) : (
                  <p className="text-sm text-slate-400">No rollback plan defined.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabPanel>

        {/* --- Impact tab --- */}
        <TabPanel value="impact">
          {(impactLoading || refreshImpactMutation.isPending) ? (
            <div className="flex items-center justify-center py-12">
              <svg className="animate-spin h-6 w-6 text-purple-500 mr-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              <span className="text-sm text-slate-500">Analyzing impact with AI...</span>
            </div>
          ) : impact ? (
            <div className="space-y-6">
              {/* LLM badge + refresh button */}
              <div className="flex items-center justify-between">
                {impact.llm_powered && (
                  <div className="flex items-center gap-2 rounded-btn border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/30 px-3 py-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-purple-100 dark:bg-purple-900 px-2.5 py-0.5 text-xs font-semibold text-purple-700 dark:text-purple-300">
                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a6 6 0 0 1 6 6c0 3-2 5-6 8-4-3-6-5-6-8a6 6 0 0 1 6-6z"/><circle cx="12" cy="8" r="2"/></svg>
                      AI-Powered
                    </span>
                    <span className="text-xs text-purple-600 dark:text-purple-400">Analysis powered by Gemini Flash LLM</span>
                  </div>
                )}
                <button
                  onClick={() => refreshImpactMutation.mutate()}
                  disabled={refreshImpactMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                  Re-analyze
                </button>
              </div>

              {/* Action analysis */}
              {impact.action_analysis && (
                <Card>
                  <CardHeader title="Action Analysis" />
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-brand-100 dark:bg-brand-900 px-2.5 py-0.5 text-xs font-semibold text-brand-700 dark:text-brand-300">
                          {impact.action_analysis.action?.replace(/_/g, ' ')}
                        </span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          Strategy: {impact.action_analysis.traversal_strategy?.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <p className="text-sm text-slate-600 dark:text-slate-300">{impact.action_analysis.explanation}</p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* LLM Risk Assessment */}
              {impact.risk_assessment && impact.risk_assessment.summary && (
                <Card>
                  <CardHeader title="Risk Assessment" />
                  <CardContent>
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${
                          impact.risk_assessment.severity === 'critical' ? 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300' :
                          impact.risk_assessment.severity === 'high' ? 'bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300' :
                          impact.risk_assessment.severity === 'medium' ? 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300' :
                          'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300'
                        }`}>
                          {impact.risk_assessment.severity}
                        </span>
                      </div>
                      <p className="text-sm text-slate-700 dark:text-slate-200">{impact.risk_assessment.summary}</p>
                      {impact.risk_assessment.factors.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Risk Factors</p>
                          <ul className="space-y-1">
                            {impact.risk_assessment.factors.map((f, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />
                                {f}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {impact.risk_assessment.mitigations.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Recommended Mitigations</p>
                          <ul className="space-y-1">
                            {impact.risk_assessment.mitigations.map((m, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                                {m}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Blast Radius */}
              {impact.blast_radius && (
                <Card>
                  <CardHeader title="Blast Radius" />
                  <CardContent>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="text-center rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
                        <p className="text-2xl font-bold text-slate-800 dark:text-white">{impact.blast_radius.total_impacted}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">Total Impacted</p>
                      </div>
                      <div className="text-center rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
                        <p className="text-2xl font-bold text-red-600 dark:text-red-400">{impact.blast_radius.critical_services_at_risk?.length ?? 0}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">Critical Services at Risk</p>
                      </div>
                      <div className="text-center rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
                        <p className={`text-2xl font-bold ${impact.blast_radius.redundancy_available ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                          {impact.blast_radius.redundancy_available ? 'Yes' : 'No'}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">Redundancy Available</p>
                      </div>
                    </div>
                    {impact.blast_radius.critical_services_at_risk?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {impact.blast_radius.critical_services_at_risk.map((svc) => (
                          <span key={svc} className="rounded-full bg-red-100 dark:bg-red-900 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:text-red-300">{svc}</span>
                        ))}
                      </div>
                    )}
                    {impact.blast_radius.redundancy_details && (
                      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{impact.blast_radius.redundancy_details}</p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Critical Paths */}
              {impact.critical_paths && impact.critical_paths.length > 0 && (
                <Card>
                  <CardHeader title={`Critical Dependency Paths (${impact.critical_paths.length})`} />
                  <CardContent>
                    <div className="space-y-3">
                      {impact.critical_paths.map((path, i) => (
                        <div key={i} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                                path.criticality === 'critical' ? 'bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300' :
                                path.criticality === 'high' ? 'bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300' :
                                path.criticality === 'medium' ? 'bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300' :
                                'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300'
                              }`}>{path.criticality}</span>
                              <span className="text-xs text-slate-500 dark:text-slate-400">{path.hops} hop{path.hops !== 1 ? 's' : ''}</span>
                            </div>
                            <span className="text-xs font-mono text-slate-400 dark:text-slate-500">{path.endpoint_label}</span>
                          </div>

                          {/* Path chain visualization */}
                          <div className="flex items-center gap-1 flex-wrap mb-2">
                            {path.nodes.map((node, ni) => (
                              <span key={ni} className="contents">
                                <span className="inline-flex items-center rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-mono text-slate-700 dark:text-slate-200">
                                  {node.id}
                                </span>
                                {ni < path.nodes.length - 1 && (
                                  <span className="text-slate-400 dark:text-slate-500 text-xs">&rarr;</span>
                                )}
                              </span>
                            ))}
                          </div>

                          {path.path_description && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">{path.path_description}</p>
                          )}
                          {path.reasoning && (
                            <p className="text-xs text-slate-600 dark:text-slate-300 italic">{path.reasoning}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              <ImpactSubgraphView impact={impact} />

              <Card>
                <CardHeader title="Impact Summary" />
                <CardContent>
                  <ImpactSummary impact={impact} />
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card>
              <CardContent>
                <p className="text-sm text-slate-400 dark:text-slate-500">No impact data available. Submit the change to trigger analysis.</p>
              </CardContent>
            </Card>
          )}
        </TabPanel>

        {/* --- Approvals & Audit tab --- */}
        <TabPanel value="approvals">
          <div className="space-y-6">
            {approvals.length > 0 && (
              <Card>
                <CardHeader title="Approvals" />
                <CardContent>
                  <div className="space-y-2">
                    {approvals.map((a) => (
                      <div key={a.id} className="flex items-center justify-between rounded-btn border border-slate-100 dark:border-slate-700 px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{a.role_required}</span>
                          <StatusBadge status={a.status} />
                        </div>
                        {a.status === 'Pending' && (
                          <Button variant="success" size="xs" onClick={() => approve.mutate(a.id)}>
                            Approve
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {auditLog.length > 0 && (
              <Card>
                <CardHeader title="Audit Log" />
                <CardContent>
                  <div className="space-y-2">
                    {auditLog.map((entry, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.04 }}
                        className="flex items-start gap-2.5 text-sm"
                      >
                        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-400 dark:bg-brand-500" />
                        <span className="text-slate-600 dark:text-slate-300 flex-1">
                          <strong className="text-slate-700 dark:text-slate-200">{entry.action}</strong>
                          {entry.details && Object.keys(entry.details).length > 0 && (
                            <span className="text-slate-400 dark:text-slate-500 font-mono text-xs"> — {JSON.stringify(entry.details)}</span>
                          )}
                        </span>
                        <span className="ml-auto shrink-0 text-xs text-slate-400 dark:text-slate-500 font-mono">
                          {new Date(entry.timestamp).toLocaleString()}
                        </span>
                      </motion.div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </TabPanel>
      </Tabs>

      {/* Floating sticky action bar */}
      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-surface-dark/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">{change.title}</span>
            <StatusBadge status={change.status} />
          </div>
          <div className="flex flex-wrap gap-2">
            {canEdit && (
              <Button variant="secondary" size="sm" onClick={() => setIsEditing((current) => !current)}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                {isEditing ? 'Cancel' : 'Edit'}
              </Button>
            )}
            {change.status === 'Draft' && isOwner && (
              <>
                <Button variant="warning" size="sm" onClick={() => calcRisk.mutate()} loading={calcRisk.isPending}>
                  <Shield className="mr-1.5 h-3.5 w-3.5" />
                  Risk
                </Button>
                <Button size="sm" onClick={() => submit.mutate()} loading={submit.isPending}>
                  <Send className="mr-1.5 h-3.5 w-3.5" />
                  Submit
                </Button>
              </>
            )}
            {change.status === 'Approved' && (isOwner || isAdmin) && (
              <Button size="sm" onClick={() => execute.mutate()} loading={execute.isPending}>
                <Play className="mr-1.5 h-3.5 w-3.5" />
                Execute
              </Button>
            )}
            {change.status === 'Executing' && (isOwner || isAdmin) && (
              <>
                <Button variant="success" size="sm" onClick={() => complete.mutate()} loading={complete.isPending}>
                  <Check className="mr-1.5 h-3.5 w-3.5" />
                  Complete
                </Button>
                <Button variant="warning" size="sm" onClick={() => rollback.mutate()} loading={rollback.isPending}>
                  <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                  Rollback
                </Button>
              </>
            )}
            {['Pending', 'Analyzing'].includes(change.status) && (isAdmin || user?.role === 'Approver') && (
              <Button variant="danger" size="sm" onClick={() => setShowReject(true)}>
                <X className="mr-1.5 h-3.5 w-3.5" />
                Reject
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="mb-2">
      <p className="text-xs font-medium text-slate-400 dark:text-slate-500">{label}</p>
      <p className="text-sm text-slate-700 dark:text-slate-200">{value || '—'}</p>
    </div>
  )
}

function ImpactSummary({ impact }: { impact: ImpactPayload }) {
  /* ── Group nodes by category ──────────────────────────────────────── */
  const groups = useMemo(() => {
    const categorize = (entries: ImpactEntry[], level: string) =>
      entries.map((e) => ({ ...e, impactLevel: level }))

    const all = [
      ...categorize(impact.directly_impacted, 'direct'),
      ...categorize(impact.indirectly_impacted, 'indirect'),
      ...categorize(impact.affected_applications, 'application'),
      ...categorize(impact.affected_services, 'service'),
    ]

    // Deduplicate by id
    const seen = new Set<string>()
    const unique = all.filter((e) => {
      if (seen.has(e.id)) return false
      seen.add(e.id)
      return true
    })

    // Build a lookup of critical-path reasoning per node id
    const reasonMap = new Map<string, { criticality: string; reasoning: string }>()
    impact.critical_paths?.forEach((path) => {
      path.nodes.forEach((n) => {
        if (!reasonMap.has(n.id) || critRank(path.criticality) > critRank(reasonMap.get(n.id)!.criticality)) {
          const reason = path.reasoning || path.path_description || ''
          if (reason) reasonMap.set(n.id, { criticality: path.criticality, reasoning: reason })
        }
      })
    })

    // Group by logical category
    type GroupedEntry = ImpactEntry & { impactLevel: string; criticality?: string; reasoning?: string }
    const buckets: Record<string, GroupedEntry[]> = {
      'Critical Services': [],
      'Applications': [],
      'Network Devices': [],
      'Interfaces & Ports': [],
      'VLANs': [],
      'Other Infrastructure': [],
    }

    unique.forEach((entry) => {
      const r = reasonMap.get(entry.id)
      const enriched: GroupedEntry = { ...entry, criticality: r?.criticality, reasoning: r?.reasoning }
      const label = entry.label?.toLowerCase() ?? ''
      if (entry.impactLevel === 'service' || label === 'service') buckets['Critical Services'].push(enriched)
      else if (entry.impactLevel === 'application' || label === 'application') buckets['Applications'].push(enriched)
      else if (label === 'device') buckets['Network Devices'].push(enriched)
      else if (label === 'interface' || label === 'port') buckets['Interfaces & Ports'].push(enriched)
      else if (label === 'vlan') buckets['VLANs'].push(enriched)
      else buckets['Other Infrastructure'].push(enriched)
    })

    return Object.entries(buckets)
      .filter(([, items]) => items.length > 0)
      .map(([name, items]) => ({
        name,
        items: items.sort((a, b) => critRank(b.criticality) - critRank(a.criticality)),
      }))
  }, [impact])

  const iconFor = (name: string) => {
    if (name === 'Critical Services') return <Zap className="h-3.5 w-3.5 text-red-500" />
    if (name === 'Applications') return <Globe className="h-3.5 w-3.5 text-blue-500" />
    if (name === 'Network Devices') return <Server className="h-3.5 w-3.5 text-purple-500" />
    if (name === 'VLANs') return <Layers className="h-3.5 w-3.5 text-cyan-500" />
    return <AlertTriangle className="h-3.5 w-3.5 text-slate-400" />
  }

  return (
    <div className="space-y-3">
      {groups.map(({ name, items }) => (
        <div key={name} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
          <div className="mb-2 flex items-center gap-2">
            {iconFor(name)}
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
              {name}
            </p>
            <span className="ml-auto rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:text-slate-400">
              {items.length}
            </span>
          </div>
          <div className="space-y-1.5">
            {items.map((entry) => (
              <div key={entry.id} className="flex items-start gap-2 rounded bg-slate-50 dark:bg-slate-800/60 px-2.5 py-1.5 text-xs">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-700 dark:text-slate-200 truncate">{entry.id}</span>
                    {entry.criticality && (
                      <span className={`inline-flex shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        entry.criticality === 'critical' ? 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300' :
                        entry.criticality === 'high' ? 'bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-300' :
                        entry.criticality === 'medium' ? 'bg-yellow-100 dark:bg-yellow-900/50 text-yellow-700 dark:text-yellow-300' :
                        'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300'
                      }`}>{entry.criticality}</span>
                    )}
                    <span className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      entry.impactLevel === 'direct' ? 'bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400' :
                      'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400'
                    }`}>{entry.impactLevel}</span>
                  </div>
                  {entry.reasoning && (
                    <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400 italic leading-snug">{entry.reasoning}</p>
                  )}
                </div>
                <span className="shrink-0 text-[10px] text-slate-400 dark:text-slate-500">{entry.label}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function critRank(c?: string): number {
  if (c === 'critical') return 4
  if (c === 'high') return 3
  if (c === 'medium') return 2
  if (c === 'low') return 1
  return 0
}

function toDateTimeLocal(isoString: string): string {
  const date = new Date(isoString)
  const offsetMinutes = date.getTimezoneOffset()
  const localDate = new Date(date.getTime() - offsetMinutes * 60_000)
  return localDate.toISOString().slice(0, 16)
}

function ImpactSubgraphView({ impact }: { impact: ImpactPayload }) {
  const theme = useAppStore((s) => s.theme)
  const isDark = theme === 'dark'

  const { nodes, edges } = useMemo(() => {
    if (!impact.critical_paths || impact.critical_paths.length === 0) return { nodes: [], edges: [] }

    // Collect unique nodes & edges from all critical paths
    const nodeMap = new Map<string, { id: string; label: string; criticality: string; isDirect: boolean }>()
    const edgeSet = new Set<string>()
    const edgeList: Edge[] = []

    const directIds = new Set(impact.directly_impacted.map((e) => e.id))

    impact.critical_paths.forEach((path) => {
      path.nodes.forEach((n) => {
        const existing = nodeMap.get(n.id)
        if (!existing || critRank(path.criticality) > critRank(existing.criticality)) {
          nodeMap.set(n.id, {
            id: n.id,
            label: n.label,
            criticality: path.criticality,
            isDirect: directIds.has(n.id),
          })
        }
      })
      path.edges.forEach((e) => {
        const key = `${e.source}-${e.type}-${e.target}`
        if (!edgeSet.has(key)) {
          edgeSet.add(key)
          const color =
            path.criticality === 'critical' ? (isDark ? '#f87171' : '#dc2626') :
            path.criticality === 'high' ? (isDark ? '#fb923c' : '#ea580c') :
            path.criticality === 'medium' ? (isDark ? '#facc15' : '#ca8a04') :
            (isDark ? '#64748b' : '#94a3b8')
          edgeList.push({
            id: key,
            source: e.source,
            target: e.target,
            type: 'smoothstep',
            label: e.type,
            labelStyle: { fontSize: 9, fill: isDark ? '#94a3b8' : '#64748b' },
            style: { stroke: color, strokeWidth: path.criticality === 'critical' ? 2 : 1 },
            markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color },
          })
        }
      })
    })

    // Build dagre layout
    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 80, marginx: 20, marginy: 20 })
    g.setDefaultEdgeLabel(() => ({}))

    const nodeWidth = 150
    const nodeHeight = 40

    nodeMap.forEach((n) => g.setNode(n.id, { width: nodeWidth, height: nodeHeight }))
    edgeList.forEach((e) => g.setEdge(e.source, e.target))

    dagre.layout(g)

    const rfNodes: Node[] = Array.from(nodeMap.values()).map((n) => {
      const pos = g.node(n.id)
      const critColor = n.isDirect
        ? { bg: isDark ? '#450a0a' : '#fee2e2', fg: isDark ? '#fca5a5' : '#991b1b', border: isDark ? '#991b1b' : '#dc2626' }
        : n.criticality === 'critical'
        ? { bg: isDark ? '#450a0a' : '#fef2f2', fg: isDark ? '#f87171' : '#b91c1c', border: isDark ? '#7f1d1d' : '#ef4444' }
        : n.criticality === 'high'
        ? { bg: isDark ? '#431407' : '#fff7ed', fg: isDark ? '#fb923c' : '#c2410c', border: isDark ? '#7c2d12' : '#f97316' }
        : n.criticality === 'medium'
        ? { bg: isDark ? '#422006' : '#fefce8', fg: isDark ? '#facc15' : '#a16207', border: isDark ? '#713f12' : '#eab308' }
        : { bg: isDark ? '#1e293b' : '#f8fafc', fg: isDark ? '#cbd5e1' : '#475569', border: isDark ? '#475569' : '#cbd5e1' }

      return {
        id: n.id,
        position: { x: (pos?.x ?? 0) - nodeWidth / 2, y: (pos?.y ?? 0) - nodeHeight / 2 },
        data: {
          label: (
            <div className="flex items-center gap-1">
              <span className="truncate">{n.id}</span>
              <span style={{ fontSize: 8, opacity: 0.6 }}>{n.label}</span>
            </div>
          ),
        },
        style: {
          background: critColor.bg,
          color: critColor.fg,
          border: `${n.isDirect ? 2 : 1}px solid ${critColor.border}`,
          borderRadius: 8,
          fontSize: 10,
          padding: '4px 8px',
          minWidth: nodeWidth,
          maxWidth: nodeWidth,
        },
      }
    })

    return { nodes: rfNodes, edges: edgeList }
  }, [impact, isDark])

  if (nodes.length === 0) return null

  // Legend
  const legendItems = [
    { label: 'Target', color: isDark ? '#991b1b' : '#dc2626' },
    { label: 'Critical', color: isDark ? '#7f1d1d' : '#ef4444' },
    { label: 'High', color: isDark ? '#7c2d12' : '#f97316' },
    { label: 'Medium', color: isDark ? '#713f12' : '#eab308' },
    { label: 'Low', color: isDark ? '#475569' : '#cbd5e1' },
  ]

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">Impact Subgraph — Critical Paths</p>
        <div className="flex items-center gap-2">
          {legendItems.map((l) => (
            <div key={l.label} className="flex items-center gap-1">
              <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: l.color }} />
              <span className="text-[10px] text-slate-400 dark:text-slate-500">{l.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="h-80 rounded border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnScroll={true}
          zoomOnPinch={true}
          panOnDrag={true}
          minZoom={0.3}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color={isDark ? '#334155' : undefined} />
        </ReactFlow>
      </div>
    </div>
  )
}
