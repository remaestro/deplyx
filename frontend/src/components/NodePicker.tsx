import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { apiClient } from '../api/client'
import { getTopologyIcon } from './topology/TopologyIcons'

type SearchResult = {
  id: string
  label: string
  props: Record<string, unknown>
}

type NodePickerProps = {
  selected: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
}

const NODE_TYPE_COLORS: Record<string, string> = {
  Device: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  Interface: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  VLAN: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  Rule: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  Application: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  Service: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  Port: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  IP: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  Datacenter: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  Cable: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
}

export default function NodePicker({ selected, onChange, placeholder = 'Search nodes…' }: NodePickerProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: results = [] } = useQuery<SearchResult[]>({
    queryKey: ['graph-search', query],
    queryFn: () => apiClient.get(`/graph/search?q=${encodeURIComponent(query)}&limit=20`).then((r) => r.data),
    enabled: query.length >= 1,
    staleTime: 10_000,
  })

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggle = useCallback(
    (id: string) => {
      if (selected.includes(id)) {
        onChange(selected.filter((s) => s !== id))
      } else {
        onChange([...selected, id])
      }
    },
    [selected, onChange],
  )

  const remove = useCallback(
    (id: string) => onChange(selected.filter((s) => s !== id)),
    [selected, onChange],
  )

  // Determine display name from search results or raw ID
  const displayFor = (id: string) => {
    const hit = results.find((r) => r.id === id)
    if (hit) {
      const name = (hit.props?.label || hit.props?.hostname || hit.props?.name || hit.id) as string
      return { name, type: hit.label }
    }
    return { name: id, type: '' }
  }

  const filtered = results.filter((r) => !selected.includes(r.id))

  return (
    <div ref={wrapperRef} className="relative">
      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selected.map((id) => {
            const { name, type } = displayFor(id)
            const IconComp = type ? getTopologyIcon(type.toLowerCase()) : null
            return (
              <span
                key={id}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${NODE_TYPE_COLORS[type] || 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'}`}
              >
                {IconComp && <IconComp className="h-3 w-3 opacity-70" />}
                <span className="max-w-[140px] truncate">{name}</span>
                <button
                  type="button"
                  onClick={() => remove(id)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )
          })}
        </div>
      )}

      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className="w-full rounded-input border border-slate-300 dark:border-slate-600 bg-white dark:bg-surface-dark-secondary pl-8 pr-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:border-brand-500 dark:focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:focus:ring-brand-400 transition-colors"
        />
      </div>

      {/* Dropdown */}
      {open && query.length >= 1 && (
        <div data-testid="node-picker-results" className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-surface-dark-secondary shadow-lg">
          {filtered.length === 0 && (
            <div className="px-3 py-2.5 text-sm text-slate-400 dark:text-slate-500">
              {results.length > 0 ? 'All matches already selected' : 'No nodes found'}
            </div>
          )}
          {filtered.map((r) => {
            const name = (r.props?.label || r.props?.hostname || r.props?.name || r.id) as string
            const device_type = (r.props?.device_type || r.label) as string
            const IconComp = getTopologyIcon(device_type.toLowerCase())
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => {
                  toggle(r.id)
                  setQuery('')
                  inputRef.current?.focus()
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-surface-dark-tertiary transition-colors"
              >
                <IconComp className="h-5 w-5 text-slate-500 dark:text-slate-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-slate-700 dark:text-slate-200 truncate">{name}</div>
                  <div className="text-xs text-slate-400 dark:text-slate-500 font-mono truncate">{r.id}</div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${NODE_TYPE_COLORS[r.label] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400'}`}>
                  {r.label}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
