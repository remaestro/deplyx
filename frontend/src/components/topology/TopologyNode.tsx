/**
 * Custom ReactFlow node that renders a topology SVG icon with label,
 * criticality badge, and vendor/model metadata.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps } from 'reactflow'
import { getTopologyIcon } from './TopologyIcons'

export interface TopologyNodeData {
  label: string
  nodeType: string        // Neo4j label: Device, Application, etc.
  deviceSubType?: string  // e.g. "firewall", "router", "switch"
  criticality?: string
  vendor?: string
  model?: string
  color: string           // Accent colour for the node
  impactType?: 'direct' | 'indirect' | 'critical-path'  // Set when impact analysis is active
}

const CRITICALITY_DOT: Record<string, string> = {
  critical: '#dc2626',
  high: '#f59e0b',
  medium: '#6366f1',
  low: '#10b981',
}

function TopologyNodeInner({ data, selected }: NodeProps<TopologyNodeData>) {
  const IconComponent = getTopologyIcon(data.nodeType, data.deviceSubType)
  const critColor = data.criticality ? CRITICALITY_DOT[data.criticality.toLowerCase()] : undefined

  const impactRing =
    data.impactType === 'critical-path'
      ? 'ring-2 ring-fuchsia-500 ring-offset-1 animate-[blast-radius_1.5s_ease-in-out_infinite]'
      : data.impactType === 'direct'
        ? 'ring-2 ring-red-500 ring-offset-1 animate-[blast-radius_1.5s_ease-in-out_infinite]'
        : data.impactType === 'indirect'
          ? 'ring-2 ring-amber-500 ring-offset-1'
          : ''

  return (
    <div
      className={`
        relative flex flex-col items-center gap-1 px-3 py-2.5
        rounded-xl border-[2.5px] transition-shadow
        backdrop-blur-sm
        ${selected ? 'ring-2 ring-brand-500 ring-offset-1' : ''}
        ${impactRing}
      `}
      style={{
        borderColor: data.color,
        backgroundColor: `${data.color}14`,
        boxShadow: `0 3px 16px ${data.color}40, 0 1px 4px rgba(0,0,0,0.08)`,
        minWidth: 110,
      }}
    >
      {/* Criticality dot — top-right */}
      {critColor && (
        <span
          className="absolute -top-1.5 -right-1.5 h-3.5 w-3.5 rounded-full border-2 border-white dark:border-slate-800"
          style={{ backgroundColor: critColor }}
          title={`Criticality: ${data.criticality}`}
        />
      )}

      {/* Icon */}
      <IconComponent size={30} color={data.color} />

      {/* Label */}
      <div className="text-center leading-tight">
        <div
          className="text-[10px] font-extrabold uppercase tracking-wider"
          style={{ color: data.color }}
        >
          {data.deviceSubType || data.nodeType}
        </div>
        <div className="text-[11px] font-bold text-slate-800 dark:text-slate-100 max-w-[120px] truncate">
          {data.label}
        </div>
      </div>

      {/* Vendor / model subtitle */}
      {(data.vendor || data.model) && (
        <div className="text-[9px] text-slate-500 dark:text-slate-400 font-medium truncate max-w-[120px]">
          {[data.vendor, data.model].filter(Boolean).join(' ')}
        </div>
      )}

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-transparent !border-0 !w-3 !h-1"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-transparent !border-0 !w-3 !h-1"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!bg-transparent !border-0 !w-1 !h-3"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!bg-transparent !border-0 !w-1 !h-3"
      />
    </div>
  )
}

export const TopologyNode = memo(TopologyNodeInner)
