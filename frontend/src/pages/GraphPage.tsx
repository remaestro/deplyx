import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, X as XIcon, Layers, Zap, Search, Flame, Maximize2, ArrowRightLeft, ArrowDownUp, Network } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { apiClient } from '../api/client'
import { useAppStore } from '../store/useAppStore'
import { EmptyState, Skeleton } from '../components/ui'
import { TopologyNode, type TopologyNodeData } from '../components/topology/TopologyNode'

type LayoutDirection = 'LR' | 'TB'

const CUSTOM_NODE_TYPES = { topology: TopologyNode } as const

type GraphNode = { id: string; label: string; type: string; properties: Record<string, unknown> }
type GraphEdge = { source: string; target: string; type: string }
type Topology = { nodes: GraphNode[]; edges: GraphEdge[] }
type ChangeOption = { id: string; title: string; status: string }

type ImpactEntry = { id: string; label: string; properties: Record<string, unknown> }
type CriticalPathEdge = { source: string; target: string; type: string }
type CriticalPath = {
  source_id: string
  endpoint_id: string
  criticality: string
  nodes: { id: string; label: string }[]
  edges: CriticalPathEdge[]
  path_description?: string
  reasoning?: string
}
type ImpactPayload = {
  directly_impacted: ImpactEntry[]
  indirectly_impacted: ImpactEntry[]
  critical_paths?: CriticalPath[]
}
type ImpactResponse = { change_id: string; impact: ImpactPayload }

const TYPE_COLORS: Record<string, string> = {
  Device: '#6366f1',
  Interface: '#06b6d4',
  VLAN: '#8b5cf6',
  IP: '#64748b',
  Rule: '#ef4444',
  Application: '#f59e0b',
  Service: '#10b981',
  Datacenter: '#3b82f6',
}

const CRITICALITY_COLORS: Record<string, string> = {
  critical: '#dc2626',
  high: '#f59e0b',
  medium: '#6366f1',
  low: '#10b981',
}

/* Node dimensions for dagre layout calculation */
const NODE_WIDTH = 140
const NODE_HEIGHT = 90

/**
 * Build a dagre graph from the topology edges and assign positions.
 * Layout direction is Left-to-Right (LR) so the network tiers
 * (Datacenter → Router → Firewall → Switch → Server → App) spread
 * horizontally, making blast-radius paths easy to follow.
 *
 * Falls back to a grid layout for orphan nodes with no edges.
 */
function layoutNodes(
  gNodes: GraphNode[],
  gEdges: GraphEdge[],
  heatmapMode: boolean,
  layoutDir: LayoutDirection = 'LR',
): Node<TopologyNodeData>[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: layoutDir, nodesep: 60, ranksep: 180, marginx: 40, marginy: 40 })

  const nodeMap = new Map<string, GraphNode>()
  for (const gn of gNodes) {
    nodeMap.set(gn.id, gn)
    g.setNode(gn.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }

  // Only add edges where both endpoints are visible
  for (const e of gEdges) {
    if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
      g.setEdge(e.source, e.target)
    }
  }

  dagre.layout(g)

  const nodes: Node<TopologyNodeData>[] = []
  for (const gn of gNodes) {
    const pos = g.node(gn.id)
    const color = heatmapMode
      ? heatmapColor(gn)
      : (TYPE_COLORS[gn.type] ?? '#94a3b8')
    nodes.push({
      id: gn.id,
      type: 'topology',
      position: {
        x: (pos?.x ?? 0) - NODE_WIDTH / 2,
        y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        label: gn.label || gn.id,
        nodeType: gn.type,
        deviceSubType:
          typeof gn.properties?.type === 'string' ? gn.properties.type : undefined,
        criticality:
          typeof gn.properties?.criticality === 'string'
            ? gn.properties.criticality
            : undefined,
        vendor:
          typeof gn.properties?.vendor === 'string' ? gn.properties.vendor : undefined,
        model:
          typeof gn.properties?.model === 'string' ? gn.properties.model : undefined,
        color,
      },
    })
  }
  return nodes
}

/* Edge colour per relationship type so connections are distinguishable */
const EDGE_TYPE_COLORS: Record<string, string> = {
  CONNECTS_TO:   '#6366f1',   // indigo
  HAS_INTERFACE: '#0891b2',   // cyan-600
  HAS_VLAN:      '#7c3aed',   // violet-600
  HAS_RULE:      '#dc2626',   // red-600
  RUNS:          '#059669',   // emerald-600
  ROUTES_TO:     '#2563eb',   // blue-600
}

function toEdges(gEdges: GraphEdge[], isDark: boolean, _hoverLabels: boolean): Edge[] {
  const fallbackColor = isDark ? '#94a3b8' : '#334155'
  return gEdges.map((e, i) => {
    const eType = e.type ?? ''
    const color = EDGE_TYPE_COLORS[eType] ?? fallbackColor
    return {
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      label: eType.replace(/_/g, ' ') || undefined,
      type: 'smoothstep',
      animated: eType === 'CONNECTS_TO',
      style: { stroke: color, strokeWidth: 2.5, opacity: 0.85 },
      labelStyle: { fontSize: 9, fill: color, fontWeight: 700 },
      labelBgStyle: {
        fill: isDark ? '#0f172a' : '#ffffff',
        fillOpacity: 0.92,
      },
      labelBgPadding: [5, 3] as [number, number],
      labelBgBorderRadius: 4,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color },
      data: { edgeType: eType },
    }
  })
}

/* Heatmap mode: map criticality to warm gradient colors */
const HEATMAP_COLORS: Record<string, string> = {
  critical: '#dc2626',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
}
function heatmapColor(node: GraphNode): string {
  const c = node.properties?.criticality
  if (typeof c === 'string') return HEATMAP_COLORS[c.toLowerCase()] ?? '#94a3b8'
  return '#94a3b8'
}

/* --- Floating glass panel wrapper --- */
function GlassPanel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-lg border border-slate-200/60 dark:border-slate-700/60 bg-white/90 dark:bg-slate-900/80 backdrop-blur-md shadow-lg ${className}`}
    >
      {children}
    </div>
  )
}

export default function GraphPage() {
  return (
    <ReactFlowProvider>
      <GraphPageInner />
    </ReactFlowProvider>
  )
}

function GraphPageInner() {
  const {
    selectedNodeId,
    setSelectedNodeId,
    selectedImpactChangeId,
    setSelectedImpactChangeId,
    theme,
  } = useAppStore()
  const isDark = theme === 'dark'
  const [center, setCenter] = useState('')
  const [depth, setDepth] = useState(3)
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())
  const [heatmapMode, setHeatmapMode] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [layoutDir, setLayoutDir] = useState<LayoutDirection>('LR')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null)
  const reactFlowInstance = useReactFlow()

  const params = new URLSearchParams()
  if (center) params.set('center', center)
  params.set('depth', String(depth))

  const { data: topology, isLoading, refetch } = useQuery<Topology>({
    queryKey: ['topology', center, depth],
    queryFn: () => apiClient.get(`/graph/topology?${params}`).then((r) => r.data),
  })

  const { data: changes = [] } = useQuery<ChangeOption[]>({
    queryKey: ['graph-impact-changes'],
    queryFn: () => apiClient.get('/changes').then((r) => r.data),
  })

  const { data: impactResponse, isFetching: impactLoading } = useQuery<ImpactResponse>({
    queryKey: ['graph-impact', selectedImpactChangeId],
    queryFn: () => apiClient.get(`/changes/${selectedImpactChangeId}/impact`).then((r) => r.data),
    enabled: !!selectedImpactChangeId,
    retry: false,
  })

  /* Clear stale impact selection when the referenced change no longer exists */
  useEffect(() => {
    if (
      selectedImpactChangeId &&
      changes.length > 0 &&
      !changes.some((c) => c.id === selectedImpactChangeId)
    ) {
      setSelectedImpactChangeId('')
    }
  }, [changes, selectedImpactChangeId, setSelectedImpactChangeId])

  // All node types present for layer toggle
  const nodeTypes = useMemo(() => {
    const types = new Set<string>()
    for (const n of topology?.nodes ?? []) {
      if (n.type) types.add(n.type)
    }
    return Array.from(types).sort()
  }, [topology])

  const toggleType = (type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const initialNodes = useMemo(
    () => {
      const filtered = (topology?.nodes ?? []).filter((n) => !hiddenTypes.has(n.type))
      return layoutNodes(filtered, topology?.edges ?? [], heatmapMode, layoutDir)
    },
    [topology, hiddenTypes, heatmapMode, layoutDir],
  )
  const initialEdges = useMemo(
    () => toEdges(topology?.edges ?? [], isDark, true),
    [topology, isDark],
  )

  const directImpactIds = useMemo(
    () => new Set((impactResponse?.impact.directly_impacted ?? []).map((item) => item.id)),
    [impactResponse],
  )
  const indirectImpactIds = useMemo(
    () => new Set((impactResponse?.impact.indirectly_impacted ?? []).map((item) => item.id)),
    [impactResponse],
  )
  // Nodes and edge-keys on LLM critical paths
  const criticalPathNodeIds = useMemo(() => {
    const ids = new Set<string>()
    for (const cp of impactResponse?.impact.critical_paths ?? []) {
      for (const n of cp.nodes) ids.add(n.id)
    }
    return ids
  }, [impactResponse])

  const criticalPathEdgeKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const cp of impactResponse?.impact.critical_paths ?? []) {
      for (const e of cp.edges) {
        keys.add(`${e.source}→${e.target}`)
        keys.add(`${e.target}→${e.source}`) // undirected match
      }
    }
    return keys
  }, [impactResponse])

  const anyImpactIds = useMemo(() => {
    const ids = new Set<string>()
    for (const id of directImpactIds) ids.add(id)
    for (const id of indirectImpactIds) ids.add(id)
    for (const id of criticalPathNodeIds) ids.add(id)
    return ids
  }, [directImpactIds, indirectImpactIds, criticalPathNodeIds])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // Sync when topology changes
  useEffect(() => {
    const impactEnabled = selectedImpactChangeId.length > 0
    const highlightedNodes = initialNodes.map((node) => {
      if (!impactEnabled) {
        return {
          ...node,
          data: { ...node.data, impactType: undefined },
          style: { opacity: 1 },
        }
      }

      if (criticalPathNodeIds.has(node.id)) {
        return {
          ...node,
          data: { ...node.data, impactType: 'critical-path' as const },
          style: { opacity: 1 },
        }
      }

      if (directImpactIds.has(node.id)) {
        return {
          ...node,
          data: { ...node.data, impactType: 'direct' as const },
          style: { opacity: 1 },
        }
      }

      if (indirectImpactIds.has(node.id)) {
        return {
          ...node,
          data: { ...node.data, impactType: 'indirect' as const },
          style: { opacity: 1 },
        }
      }

      return {
        ...node,
        data: { ...node.data, impactType: undefined },
        style: { opacity: 0.2 },
      }
    })

    const dimColor = isDark ? '#334155' : '#cbd5e1'
    const highlightedEdges = initialEdges.map((edge) => {
      if (!impactEnabled) {
        // Keep per-type colour from initialEdges — just ensure opacity is full
        const edgeType = edge.data?.edgeType as string | undefined
        const color = (edgeType && EDGE_TYPE_COLORS[edgeType]) ?? (isDark ? '#94a3b8' : '#334155')
        return {
          ...edge,
          style: { stroke: color, strokeWidth: 2.5, opacity: 0.85 },
          markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color },
          animated: edgeType === 'CONNECTS_TO',
        }
      }

      // Critical-path edges (LLM-identified) — thick fuchsia pulsing
      const edgeKey = `${edge.source}→${edge.target}`
      const edgeKeyRev = `${edge.target}→${edge.source}`
      if (criticalPathEdgeKeys.has(edgeKey) || criticalPathEdgeKeys.has(edgeKeyRev)) {
        return {
          ...edge,
          style: { stroke: '#d946ef', strokeWidth: 3, opacity: 1 },
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#d946ef' },
          animated: true,
          label: edge.data?.edgeType ?? edge.label,
          labelStyle: { fontSize: 9, fill: '#d946ef', fontWeight: 700 },
        }
      }

      const sourceInImpact = anyImpactIds.has(edge.source)
      const targetInImpact = anyImpactIds.has(edge.target)
      if (sourceInImpact && targetInImpact) {
        const directEdge = directImpactIds.has(edge.source) || directImpactIds.has(edge.target)
        const color = directEdge ? '#dc2626' : '#d97706'
        return {
          ...edge,
          style: { stroke: color, opacity: 0.9 },
          markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color },
          animated: directEdge,
        }
      }

      return {
        ...edge,
        style: { stroke: dimColor, opacity: 0.15 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: dimColor },
        animated: false,
      }
    })

    setNodes(highlightedNodes)
    setEdges(highlightedEdges)
  }, [
    anyImpactIds,
    criticalPathNodeIds,
    criticalPathEdgeKeys,
    directImpactIds,
    indirectImpactIds,
    initialEdges,
    initialNodes,
    selectedImpactChangeId,
    setEdges,
    setNodes,
    isDark,
  ])

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNodeId(node.id)
      setCenter(node.id)
      setContextMenu(null)
    },
    [setSelectedNodeId],
  )

  const onNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault()
      setContextMenu({ x: event.clientX, y: event.clientY, nodeId: node.id })
    },
    [],
  )

  const onPaneClick = useCallback(() => {
    setContextMenu(null)
  }, [])

  const zoomToNode = useCallback(
    (nodeId: string) => {
      const node = nodes.find((n) => n.id === nodeId)
      if (node) {
        reactFlowInstance.fitView({ nodes: [node], duration: 600, padding: 0.5 })
        setSelectedNodeId(nodeId)
      }
    },
    [nodes, reactFlowInstance, setSelectedNodeId],
  )

  /* Search-filtered node suggestions */
  const searchResults = useMemo(() => {
    if (!searchTerm.trim()) return []
    const q = searchTerm.toLowerCase()
    return (topology?.nodes ?? [])
      .filter((n) => n.id.toLowerCase().includes(q) || n.label.toLowerCase().includes(q))
      .slice(0, 8)
  }, [topology, searchTerm])

  const clearImpactAndFocus = useCallback(() => {
    setSelectedImpactChangeId('')
    setSelectedNodeId(null)
    setCenter('')
  }, [setSelectedImpactChangeId, setSelectedNodeId])

  /* Fit the entire graph into view */
  const fitAll = useCallback(() => {
    reactFlowInstance.fitView({ duration: 400, padding: 0.15 })
  }, [reactFlowInstance])

  /* Toggle layout direction */
  const toggleLayout = useCallback(() => {
    setLayoutDir((d) => (d === 'LR' ? 'TB' : 'LR'))
  }, [])

  /* Keyboard shortcuts (F = fitView, L = toggle layout) */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Skip if user is typing in an input/select/textarea
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault()
        fitAll()
      }
      if (e.key === 'l' || e.key === 'L') {
        e.preventDefault()
        toggleLayout()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [fitAll, toggleLayout])

  /* Auto-fit when layout direction changes */
  useEffect(() => {
    // Small delay to let ReactFlow process the new positions
    const timer = setTimeout(() => fitAll(), 100)
    return () => clearTimeout(timer)
  }, [layoutDir, fitAll])

  const selectedNode = topology?.nodes.find((n) => n.id === selectedNodeId)

  return (
    <div className="flex h-[calc(100vh-120px)] gap-3">
      {/* Graph canvas */}
      <div className="relative flex-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
        {/* Toolbar — top-left */}
        <GlassPanel className="absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2 px-3 py-2">
          {/* Search with zoom-to-node */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400" />
            <input
              placeholder="Search nodes…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 pl-6 pr-2 py-1 text-xs text-slate-700 dark:text-slate-200 w-36 focus-ring placeholder:text-slate-400 dark:placeholder:text-slate-500"
            />
            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 mt-1 w-52 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg z-20 max-h-48 overflow-y-auto">
                {searchResults.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => {
                      zoomToNode(n.id)
                      setSearchTerm('')
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                  >
                    <span className="font-medium">{n.label || n.id}</span>
                    <span className="ml-1.5 text-[10px] text-slate-400">{n.type}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <select
            value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
          >
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>Depth {d}</option>
            ))}
          </select>
          <button
            onClick={() => setHeatmapMode((v) => !v)}
            className={`rounded-btn border p-1.5 transition-colors ${
              heatmapMode
                ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/30 text-amber-600'
                : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
            }`}
            title="Heatmap mode"
          >
            <Flame className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => refetch()} className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 p-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors" title="Refresh">
            <RefreshCw className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" />
          </button>

          {/* Divider */}
          <div className="h-5 w-px bg-slate-300 dark:bg-slate-600" />

          {/* Fit entire graph */}
          <button
            onClick={fitAll}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-brand-50 dark:hover:bg-brand-900/20 hover:text-brand-600 dark:hover:text-brand-400 hover:border-brand-300 dark:hover:border-brand-700 transition-colors flex items-center gap-1"
            title="Fit all nodes in view (F)"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            Fit All
          </button>

          {/* Layout direction toggle */}
          <button
            onClick={toggleLayout}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors flex items-center gap-1"
            title={`Switch to ${layoutDir === 'LR' ? 'top-down' : 'left-right'} layout (L)`}
          >
            {layoutDir === 'LR' ? <ArrowDownUp className="h-3.5 w-3.5" /> : <ArrowRightLeft className="h-3.5 w-3.5" />}
            {layoutDir === 'LR' ? 'Top–Down' : 'Left–Right'}
          </button>

          {/* Node/edge count badge */}
          <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500 tabular-nums">
            {nodes.length} nodes · {edges.length} edges
          </span>
        </GlassPanel>

        {/* Impact selector — top-center */}
        <GlassPanel className="absolute left-1/2 -translate-x-1/2 top-3 z-10 flex items-center gap-2 px-3 py-2">
          <Zap className="h-3.5 w-3.5 text-amber-500" />
          <select
            value={selectedImpactChangeId}
            onChange={(e) => setSelectedImpactChangeId(e.target.value)}
            className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-xs text-slate-700 dark:text-slate-200 max-w-56"
          >
            <option value="">No impact highlight</option>
            {changes.map((change) => (
              <option key={change.id} value={change.id}>
                {change.title} ({change.status})
              </option>
            ))}
          </select>
          {selectedImpactChangeId && (
            <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400">
              {impactLoading ? 'Loading…' : `Direct: ${directImpactIds.size} · Indirect: ${indirectImpactIds.size}${criticalPathNodeIds.size > 0 ? ` · Critical paths: ${impactResponse?.impact.critical_paths?.length ?? 0}` : ''}`}
            </span>
          )}
          {(selectedImpactChangeId || center || selectedNodeId) && (
            <button
              onClick={clearImpactAndFocus}
              className="rounded-btn border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-2 py-1 text-[10px] text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              Clear impact + focus
            </button>
          )}
        </GlassPanel>

        {/* Layer toggles — top-right */}
        {nodeTypes.length > 0 && (
          <GlassPanel className="absolute right-3 top-3 z-10 px-3 py-2 max-w-[180px]">
            <div className="flex items-center gap-1.5 mb-2">
              <Layers className="h-3 w-3 text-slate-500 dark:text-slate-400" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Layers</span>
            </div>
            <div className="space-y-1">
              {nodeTypes.map((type) => (
                <label key={type} className="flex items-center gap-2 cursor-pointer text-[11px] text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-white transition-colors">
                  <input
                    type="checkbox"
                    checked={!hiddenTypes.has(type)}
                    onChange={() => toggleType(type)}
                    className="rounded border-slate-300 dark:border-slate-600 text-brand-600 focus:ring-brand-500 h-3 w-3"
                  />
                  <span className="inline-block h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: TYPE_COLORS[type] ?? '#94a3b8' }} />
                  {type}
                </label>
              ))}
            </div>
          </GlassPanel>
        )}

        {/* Impact legend — bottom-left */}
        {selectedImpactChangeId && !impactLoading && (
          <GlassPanel className="absolute left-3 bottom-3 z-10 px-3 py-2 text-[10px] text-slate-600 dark:text-slate-300 space-y-1.5">
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-fuchsia-500 bg-fuchsia-500/20" />
              <span>Critical path (AI)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-red-500 bg-red-500/20" />
              <span>Direct impact</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm border-2 border-amber-500 bg-amber-500/20" />
              <span>Indirect impact</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-300 dark:bg-slate-600 opacity-40" />
              <span>Not impacted</span>
            </div>
          </GlassPanel>
        )}

        {/* Criticality legend — bottom-right */}
        <GlassPanel className="absolute right-3 bottom-3 z-10 px-3 py-2 text-[10px] text-slate-600 dark:text-slate-300">
          <div className="font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">Criticality</div>
          {Object.entries(CRITICALITY_COLORS).map(([level, color]) => (
            <div key={level} className="flex items-center gap-1.5 mt-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
              <span className="capitalize">{level}</span>
            </div>
          ))}
        </GlassPanel>

        {/* Canvas */}
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Skeleton variant="card" />
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={Layers}
              title="No topology data"
              description='No discovered topology yet. Sync connectors to populate this view.'
            />
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={CUSTOM_NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeContextMenu={onNodeContextMenu}
            onPaneClick={onPaneClick}
            fitView
          >
            <MiniMap
              nodeColor={(n) => (n.data as TopologyNodeData)?.color ?? '#94a3b8'}
              nodeStrokeWidth={2}
              maskColor={isDark ? 'rgba(15,23,42,0.6)' : 'rgba(241,245,249,0.6)'}
              style={{
                backgroundColor: isDark ? '#1e293b' : '#f8fafc',
                borderRadius: 8,
                border: isDark ? '1px solid #334155' : '1px solid #cbd5e1',
                width: 180,
                height: 130,
              }}
              zoomable
              pannable
            />
            <Controls
              style={{
                borderRadius: 8,
                overflow: 'hidden',
              }}
            />
            <Background color={isDark ? '#334155' : '#e2e8f0'} gap={20} size={1.5} />
          </ReactFlow>
        )}

        {/* Right-click context menu */}
        {contextMenu && (
          <div
            style={{ top: contextMenu.y, left: contextMenu.x }}
            className="fixed z-50 min-w-[140px] rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl py-1"
          >
            <button
              onClick={() => {
                setCenter(contextMenu.nodeId)
                setContextMenu(null)
              }}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              Focus on this node
            </button>
            <button
              onClick={() => {
                zoomToNode(contextMenu.nodeId)
                setContextMenu(null)
              }}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              Zoom to node
            </button>
            <button
              onClick={() => {
                setSelectedNodeId(contextMenu.nodeId)
                setContextMenu(null)
              }}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              View details
            </button>
            <hr className="my-1 border-slate-200 dark:border-slate-700" />
            <button
              onClick={() => setContextMenu(null)}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Blast radius animation CSS */}
        <style>{`
          @keyframes blast-radius {
            0% { box-shadow: 0 0 0 0 rgba(220,38,38,0.4); }
            50% { box-shadow: 0 0 0 12px rgba(220,38,38,0); }
            100% { box-shadow: 0 0 0 0 rgba(220,38,38,0); }
          }
        `}</style>
      </div>

      {/* Detail panel */}
      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 288, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="shrink-0 overflow-hidden"
          >
            <div className="h-full w-72 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-3 w-3 rounded-full shadow-sm"
                    style={{
                      backgroundColor:
                        (typeof selectedNode.properties.criticality === 'string' &&
                          CRITICALITY_COLORS[selectedNode.properties.criticality.toLowerCase()]) ||
                        TYPE_COLORS[selectedNode.type] ||
                        '#94a3b8',
                    }}
                  />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                    {selectedNode.type}
                  </span>
                </div>
                <button
                  onClick={() => { setSelectedNodeId(null); setCenter('') }}
                  className="rounded-btn p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                >
                  <XIcon className="h-3.5 w-3.5" />
                </button>
              </div>

              <h3 className="mb-4 text-sm font-semibold text-slate-800 dark:text-slate-100">
                {selectedNode.label || selectedNode.id}
              </h3>

              <dl className="space-y-2.5 text-xs">
                {Object.entries(selectedNode.properties).map(([k, v]) => (
                  <div key={k}>
                    <dt className="font-medium text-slate-400 dark:text-slate-500 uppercase text-[10px] tracking-wider">{k}</dt>
                    <dd className="text-slate-700 dark:text-slate-200 mt-0.5 font-mono text-[11px]">{String(v)}</dd>
                  </div>
                ))}
              </dl>

              <button
                onClick={() => { setSelectedNodeId(null); setCenter('') }}
                className="mt-5 w-full rounded-btn border border-slate-200 dark:border-slate-600 py-1.5 text-xs text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-surface-dark-tertiary transition-colors"
              >
                Clear selection
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
