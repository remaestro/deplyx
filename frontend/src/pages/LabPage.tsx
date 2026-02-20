import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play, Square, RotateCcw, Trash2, Plus, Terminal, Search, X,
  Loader2, AlertCircle, ChevronDown, ChevronRight, LayoutGrid,
  Send, HelpCircle, ChevronUp,
} from 'lucide-react'
import {
  getCatalog, getContainers, spawnContainer, removeContainer,
  startContainer, stopContainer, restartContainer, execCommand, getExecHelp,
  type CatalogItem, type LabContainer, type ExecResult,
} from '../api/lab'
import { getTopologyIcon } from '../components/topology/TopologyIcons'
import StatusLED from '../components/ui/StatusLED'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { Input } from '../components/ui/Input'

// ─── Helpers ─────────────────────────────────────────────────────────────────

const CATEGORIES = ['All', 'Firewall', 'Switch', 'Router', 'Wireless', 'Security', 'Application']

const CATEGORY_COLORS: Record<string, string> = {
  Firewall: 'text-red-400',
  Switch: 'text-blue-400',
  Router: 'text-purple-400',
  Wireless: 'text-cyan-400',
  Security: 'text-amber-400',
  Application: 'text-emerald-400',
}

const CATEGORY_BG: Record<string, string> = {
  Firewall: 'bg-red-500/10',
  Switch: 'bg-blue-500/10',
  Router: 'bg-purple-500/10',
  Wireless: 'bg-cyan-500/10',
  Security: 'bg-amber-500/10',
  Application: 'bg-emerald-500/10',
}

function containerStatus(status: string): 'active' | 'syncing' | 'error' | 'inactive' {
  if (status === 'running') return 'active'
  if (status === 'restarting') return 'syncing'
  if (status === 'paused') return 'syncing'
  if (status === 'created') return 'syncing'
  return 'inactive'
}

function statusBadgeColor(status: string): 'success' | 'warning' | 'neutral' | 'critical' {
  if (status === 'running') return 'success'
  if (status === 'restarting' || status === 'paused') return 'warning'
  return 'neutral'
}

function formatPorts(ports: Record<string, string | null>): string {
  const entries = Object.entries(ports).filter(([, v]) => v)
  if (!entries.length) return '—'
  return entries.map(([k, v]) => `${v}→${k}`).slice(0, 2).join(', ')
}

// ─── Spawn Modal ──────────────────────────────────────────────────────────────

interface SpawnModalProps {
  item: CatalogItem
  onClose: () => void
}

function SpawnModal({ item, onClose }: SpawnModalProps) {
  const [name, setName] = useState('')
  const qc = useQueryClient()

  const spawn = useMutation({
    mutationFn: () => spawnContainer({ type_id: item.type_id, name: name.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lab-containers'] })
      onClose()
    },
  })

  const IconComp = getTopologyIcon(item.icon_type)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-sm rounded-2xl border border-slate-700/60 bg-slate-900 p-6 shadow-2xl">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400 hover:text-slate-200">
          <X size={18} />
        </button>

        {/* Header */}
        <div className="mb-4 flex items-center gap-3">
          <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${CATEGORY_BG[item.category] ?? 'bg-slate-700/50'}`}>
            <IconComp size={26} color={item.color} />
          </div>
          <div>
            <p className="font-semibold text-slate-100">{item.label}</p>
            <p className="text-xs text-slate-400">{item.vendor} · {item.model}</p>
          </div>
        </div>

        <p className="mb-4 text-sm text-slate-400">{item.description}</p>

        {/* Name input */}
        <label className="mb-1 block text-xs font-medium text-slate-300">Instance name</label>
        <Input
          value={name}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
          placeholder={`e.g. ${item.type_id}-prod-01`}
          className="mb-4 w-full"
          onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && name.trim() && spawn.mutate()}
          autoFocus
        />

        {spawn.isError && (
          <p className="mb-3 flex items-center gap-1.5 text-xs text-red-400">
            <AlertCircle size={14} />
            {(spawn.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to spawn container'}
          </p>
        )}

        <div className="flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button
            className="flex-1"
            disabled={!name.trim() || spawn.isPending}
            onClick={() => spawn.mutate()}
          >
            {spawn.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            {spawn.isPending ? 'Spawning…' : 'Spawn'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ─── Terminal Drawer ──────────────────────────────────────────────────────────

interface TerminalEntry {
  id: number
  type: 'command' | 'result' | 'error' | 'info'
  text: string
  timestamp: Date
}

interface TerminalDrawerProps {
  container: LabContainer
  onClose: () => void
}

function formatOutput(result: ExecResult): string {
  // Help response
  if (result.commands) {
    const lines = [`Protocol: ${result.protocol || 'unknown'}`, '', 'Available commands:']
    for (const cmd of result.commands) {
      lines.push(`  ${cmd}`)
    }
    if (result.hint) lines.push('', result.hint)
    return lines.join('\n')
  }

  // SSH output
  if (result.output !== undefined) {
    return result.output || '(empty output)'
  }

  // API result with data
  if (result.data !== undefined) {
    if (typeof result.data === 'string') return result.data
    return JSON.stringify(result.data, null, 2)
  }

  // Error
  if (result.error) {
    return `Error: ${result.error}`
  }

  return JSON.stringify(result, null, 2)
}

function TerminalDrawer({ container, onClose }: TerminalDrawerProps) {
  const [history, setHistory] = useState<TerminalEntry[]>([])
  const [input, setInput] = useState('')
  const [cmdHistory, setCmdHistory] = useState<string[]>([])
  const [historyIdx, setHistoryIdx] = useState(-1)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const idRef = useRef(0)

  // Auto-scroll on new entries
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Load help on mount
  useEffect(() => {
    const loadHelp = async () => {
      try {
        const help = await getExecHelp(container.id)
        const id = ++idRef.current
        setHistory([{
          id,
          type: 'info',
          text: `Connected to ${container.name} (${container.ip || 'no IP'})\n` +
                `Type "help" for available commands.\n\n` +
                formatOutput(help),
          timestamp: new Date(),
        }])
      } catch {
        const id = ++idRef.current
        setHistory([{
          id,
          type: 'info',
          text: `Connected to ${container.name}. Type "help" for available commands.`,
          timestamp: new Date(),
        }])
      }
    }
    loadHelp()
  }, [container.id, container.name, container.ip])

  const exec = useMutation({
    mutationFn: (command: string) => execCommand(container.id, command),
  })

  const handleSubmit = useCallback(async () => {
    const cmd = input.trim()
    if (!cmd) return

    // Add to history
    setCmdHistory(prev => [...prev, cmd])
    setHistoryIdx(-1)
    setInput('')

    const cmdId = ++idRef.current
    setHistory(prev => [...prev, {
      id: cmdId,
      type: 'command',
      text: cmd,
      timestamp: new Date(),
    }])

    // Handle local commands
    if (cmd.toLowerCase() === 'clear') {
      setHistory([])
      return
    }

    try {
      const result = await exec.mutateAsync(cmd)
      const resultId = ++idRef.current
      const isError = !!result.error || (result.status !== undefined && result.status >= 400)
      setHistory(prev => [...prev, {
        id: resultId,
        type: isError ? 'error' : 'result',
        text: formatOutput(result),
        timestamp: new Date(),
      }])
    } catch (err: unknown) {
      const resultId = ++idRef.current
      const message = err instanceof Error ? err.message :
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Command failed'
      setHistory(prev => [...prev, {
        id: resultId,
        type: 'error',
        text: message,
        timestamp: new Date(),
      }])
    }
  }, [input, container.id, exec])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSubmit()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (cmdHistory.length > 0) {
        const newIdx = historyIdx === -1 ? cmdHistory.length - 1 : Math.max(0, historyIdx - 1)
        setHistoryIdx(newIdx)
        setInput(cmdHistory[newIdx])
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (historyIdx === -1) return
      const newIdx = historyIdx + 1
      if (newIdx >= cmdHistory.length) {
        setHistoryIdx(-1)
        setInput('')
      } else {
        setHistoryIdx(newIdx)
        setInput(cmdHistory[newIdx])
      }
    }
  }

  const typeId = container.labels['deplyx.type'] || container.type_id || ''
  const isApiDevice = ['fortinet', 'paloalto', 'checkpoint'].includes(typeId)
  const promptLabel = isApiDevice ? `${container.name}(api)` : `${container.name}`

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex flex-col w-full max-w-2xl border-l border-slate-700/60 bg-slate-950 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal size={16} className="text-emerald-400" />
          <span className="font-medium text-slate-200">{container.name}</span>
          <Badge color={statusBadgeColor(container.status)}>{container.status}</Badge>
          {container.ip && (
            <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">{container.ip}</code>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setHistory([])
            }}
            className="rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="Clear terminal"
          >
            Clear
          </button>
          <button
            onClick={async () => {
              try {
                const help = await getExecHelp(container.id)
                const id = ++idRef.current
                setHistory(prev => [...prev, {
                  id,
                  type: 'info',
                  text: formatOutput(help),
                  timestamp: new Date(),
                }])
              } catch {
                /* ignore */
              }
            }}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="Show help"
          >
            <HelpCircle size={16} />
          </button>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Terminal body */}
      <div
        ref={scrollRef}
        onClick={() => inputRef.current?.focus()}
        className="flex-1 overflow-auto p-4 font-mono text-xs leading-relaxed cursor-text"
      >
        {history.map((entry) => (
          <div key={entry.id} className="mb-2">
            {entry.type === 'command' ? (
              <div className="flex items-start gap-2">
                <span className="shrink-0 text-emerald-400">{promptLabel}#</span>
                <span className="text-slate-100">{entry.text}</span>
              </div>
            ) : entry.type === 'error' ? (
              <pre className="whitespace-pre-wrap break-all text-red-400 pl-2 border-l-2 border-red-500/30">
                {entry.text}
              </pre>
            ) : entry.type === 'info' ? (
              <pre className="whitespace-pre-wrap break-all text-blue-300 pl-2 border-l-2 border-blue-500/30">
                {entry.text}
              </pre>
            ) : (
              <pre className="whitespace-pre-wrap break-all text-emerald-300 pl-2 border-l-2 border-emerald-500/20">
                {entry.text}
              </pre>
            )}
          </div>
        ))}

        {exec.isPending && (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 size={12} className="animate-spin" />
            <span>Executing…</span>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="border-t border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 focus-within:border-emerald-500/50 focus-within:ring-1 focus-within:ring-emerald-500/30">
          <span className="shrink-0 text-xs font-medium text-emerald-400">{promptLabel}#</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command…"
            disabled={exec.isPending || container.status !== 'running'}
            className="flex-1 bg-transparent text-xs text-slate-100 placeholder-slate-600 outline-none disabled:opacity-50"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            onClick={handleSubmit}
            disabled={exec.isPending || !input.trim()}
            className="shrink-0 rounded p-1 text-slate-400 hover:text-emerald-400 disabled:opacity-30"
          >
            <Send size={14} />
          </button>
        </div>
        <div className="mt-1.5 flex items-center gap-3 text-[10px] text-slate-600">
          <span><kbd className="rounded border border-slate-700 px-1">Enter</kbd> execute</span>
          <span><kbd className="rounded border border-slate-700 px-1">&#x2191;</kbd><kbd className="rounded border border-slate-700 px-1">&#x2193;</kbd> history</span>
          <span>Type <code className="text-slate-500">help</code> for commands · <code className="text-slate-500">clear</code> to reset</span>
        </div>
      </div>
    </div>
  )
}

// ─── Container Card ───────────────────────────────────────────────────────────

interface ContainerCardProps {
  container: LabContainer
  onLogs: (c: LabContainer) => void
}

function ContainerCard({ container, onLogs }: ContainerCardProps) {
  const qc = useQueryClient()

  const start   = useMutation({ mutationFn: () => startContainer(container.id),   onSuccess: () => qc.invalidateQueries({ queryKey: ['lab-containers'] }) })
  const stop    = useMutation({ mutationFn: () => stopContainer(container.id),    onSuccess: () => qc.invalidateQueries({ queryKey: ['lab-containers'] }) })
  const restart = useMutation({ mutationFn: () => restartContainer(container.id), onSuccess: () => qc.invalidateQueries({ queryKey: ['lab-containers'] }) })
  const remove  = useMutation({ mutationFn: () => removeContainer(container.id),  onSuccess: () => qc.invalidateQueries({ queryKey: ['lab-containers'] }) })

  const isRunning = container.status === 'running'
  const isBusy    = start.isPending || stop.isPending || restart.isPending || remove.isPending

  // Derive icon from labels or type_id prefix
  const typeId  = container.labels['deplyx.type'] || container.type_id || 'generic'
  const iconType = container.labels['deplyx.icon_type'] || typeId
  const category = container.labels['deplyx.category'] || container.category || 'Application'
  const IconComp = getTopologyIcon(iconType)
  const color    = container.labels['deplyx.color'] || '#64748b'

  return (
    <div className="group relative rounded-xl border border-slate-700/50 bg-slate-800/50 p-4 transition hover:border-slate-600/70 hover:bg-slate-800">
      {/* Status LED top-right */}
      <StatusLED status={containerStatus(container.status)} size="sm" className="absolute right-3 top-3" />

      {/* Icon + name */}
      <div className="mb-3 flex items-center gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${CATEGORY_BG[category] ?? 'bg-slate-700/50'}`}>
          <IconComp size={22} color={color} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-100">{container.name}</p>
          <p className={`text-xs font-medium ${CATEGORY_COLORS[category] ?? 'text-slate-400'}`}>{category}</p>
        </div>
      </div>

      {/* Meta */}
      <div className="mb-3 space-y-1 text-xs text-slate-400">
        <div className="flex items-center justify-between gap-2">
          <span>Status</span>
          <Badge color={statusBadgeColor(container.status)}>{container.status}</Badge>
        </div>
        {container.ip && (
          <div className="flex items-center justify-between gap-2">
            <span>IP</span>
            <code className="rounded bg-slate-700 px-1.5 py-0.5 text-slate-300">{container.ip}</code>
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <span>Ports</span>
          <span className="text-slate-300">{formatPorts(container.ports)}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5">
        {isRunning ? (
          <button
            onClick={() => stop.mutate()}
            disabled={isBusy}
            title="Stop"
            className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700 text-slate-300 hover:bg-red-600/80 hover:text-white disabled:opacity-40"
          >
            {stop.isPending ? <Loader2 size={13} className="animate-spin" /> : <Square size={13} />}
          </button>
        ) : (
          <button
            onClick={() => start.mutate()}
            disabled={isBusy}
            title="Start"
            className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700 text-slate-300 hover:bg-emerald-600/80 hover:text-white disabled:opacity-40"
          >
            {start.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          </button>
        )}
        <button
          onClick={() => restart.mutate()}
          disabled={isBusy}
          title="Restart"
          className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700 text-slate-300 hover:bg-amber-600/80 hover:text-white disabled:opacity-40"
        >
          {restart.isPending ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
        </button>
        <button
          onClick={() => onLogs(container)}
          title="Logs"
          className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700 text-slate-300 hover:bg-blue-600/80 hover:text-white"
        >
          <Terminal size={13} />
        </button>
        <button
          onClick={() => remove.mutate()}
          disabled={isBusy || isRunning}
          title={isRunning ? 'Stop before removing' : 'Remove'}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-md bg-slate-700 text-slate-300 hover:bg-red-700/80 hover:text-white disabled:opacity-30"
        >
          {remove.isPending ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  )
}

// ─── Catalog Item Row ────────────────────────────────────────────────────────

interface CatalogRowProps {
  item: CatalogItem
  onAdd: (item: CatalogItem) => void
}

function CatalogRow({ item, onAdd }: CatalogRowProps) {
  const IconComp = getTopologyIcon(item.icon_type)

  return (
    <div className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-700/40 group">
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${CATEGORY_BG[item.category] ?? 'bg-slate-700/50'}`}>
        <IconComp size={18} color={item.color} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-200">{item.label}</p>
        <p className="truncate text-xs text-slate-500">{item.vendor} · {item.model}</p>
      </div>
      <button
        onClick={() => onAdd(item)}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-700 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-blue-600 hover:text-white transition-all"
        title={`Add ${item.label}`}
      >
        <Plus size={13} />
      </button>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function LabPage() {
  const [activeCategory, setActiveCategory] = useState('All')
  const [search, setSearch]               = useState('')
  const [spawnItem, setSpawnItem]         = useState<CatalogItem | null>(null)
  const [termContainer, setTermContainer] = useState<LabContainer | null>(null)
  const [expandedCats, setExpandedCats]   = useState<Record<string, boolean>>({})

  const { data: catalog = [], isLoading: catalogLoading } = useQuery({
    queryKey: ['lab-catalog'],
    queryFn: getCatalog,
    staleTime: Infinity,
  })

  const { data: containers = [], isLoading: containersLoading } = useQuery({
    queryKey: ['lab-containers'],
    queryFn: getContainers,
    refetchInterval: 5000,
  })

  // Filter catalog
  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return catalog.filter((item) => {
      const matchCat = activeCategory === 'All' || item.category === activeCategory
      const matchSearch = !q || item.label.toLowerCase().includes(q) || item.vendor.toLowerCase().includes(q) || item.model.toLowerCase().includes(q)
      return matchCat && matchSearch
    })
  }, [catalog, activeCategory, search])

  // Group for "All" view
  const grouped = useMemo(() => {
    const g: Record<string, CatalogItem[]> = {}
    for (const item of filtered) {
      (g[item.category] ??= []).push(item)
    }
    return g
  }, [filtered])

  const runningCount = containers.filter((c) => c.status === 'running').length

  const toggleCat = (cat: string) =>
    setExpandedCats((prev) => ({ ...prev, [cat]: !(prev[cat] ?? true) }))

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* ── Left: Component Palette ── */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-900/60">
        {/* Header */}
        <div className="border-b border-slate-800 px-4 py-4">
          <h2 className="mb-3 text-base font-semibold text-slate-100">Component Catalog</h2>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search devices…"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 py-1.5 pl-8 pr-3 text-sm text-slate-200 placeholder-slate-500 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50"
            />
          </div>
        </div>

        {/* Category tabs */}
        <div className="flex flex-wrap gap-1 border-b border-slate-800 px-3 py-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                activeCategory === cat
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-slate-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Item list */}
        <div className="flex-1 overflow-y-auto py-2 px-2">
          {catalogLoading ? (
            <div className="flex justify-center py-8 text-slate-500">
              <Loader2 className="animate-spin" size={20} />
            </div>
          ) : activeCategory === 'All' ? (
            Object.entries(grouped).map(([cat, items]) => {
              const expanded = expandedCats[cat] ?? true
              return (
                <div key={cat} className="mb-1">
                  <button
                    onClick={() => toggleCat(cat)}
                    className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-200"
                  >
                    {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    <span className={CATEGORY_COLORS[cat] ?? ''}>{cat}</span>
                  </button>
                  {expanded && items.map((item) => (
                    <CatalogRow key={item.type_id} item={item} onAdd={setSpawnItem} />
                  ))}
                </div>
              )
            })
          ) : (
            filtered.map((item) => (
              <CatalogRow key={item.type_id} item={item} onAdd={setSpawnItem} />
            ))
          )}
          {!catalogLoading && filtered.length === 0 && (
            <p className="py-6 text-center text-xs text-slate-500">No devices match your search.</p>
          )}
        </div>
      </aside>

      {/* ── Right: Active Lab ── */}
      <main className="flex flex-1 flex-col min-w-0 overflow-hidden">
        {/* Header bar */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-3">
          <div className="flex items-center gap-4">
            <div>
              <h1 className="text-xl font-bold text-slate-100">Active Lab</h1>
              <p className="text-xs text-slate-400">
                {containersLoading ? 'Loading…' : `${containers.length} containers · ${runningCount} running`}
              </p>
            </div>
            <div className="ml-4 flex items-center gap-1 rounded-xl border border-slate-700/60 bg-slate-800/60 p-1">
              <span className="flex items-center gap-1.5 rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-100">
                <LayoutGrid size={13} /> Containers
              </span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span className="flex items-center gap-1.5"><StatusLED status="active" /> Running</span>
            <span className="flex items-center gap-1.5"><StatusLED status="inactive" /> Stopped</span>
            <span className="flex items-center gap-1.5"><StatusLED status="syncing" /> Transitioning</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {containersLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-40 animate-pulse rounded-xl bg-slate-800/50" />
              ))}
            </div>
          ) : containers.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-slate-500">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-slate-800">
                <Plus size={36} className="text-slate-600" />
              </div>
              <div className="text-center">
                <p className="text-lg font-medium text-slate-300">Lab is empty</p>
                <p className="mt-1 text-sm">Pick a device from the catalog and click <strong>+</strong> to spawn it.</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {containers.map((c) => (
                <ContainerCard key={c.id} container={c} onLogs={setTermContainer} />
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Spawn modal */}
      {spawnItem && <SpawnModal item={spawnItem} onClose={() => setSpawnItem(null)} />}

      {/* Terminal drawer (overlay) */}
      {termContainer && <TerminalDrawer container={termContainer} onClose={() => setTermContainer(null)} />}
    </div>
  )
}
