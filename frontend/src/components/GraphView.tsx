import ReactFlow, { Background, Controls, MiniMap, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'

const initialNodes: Node[] = [
  { id: '1', position: { x: 80, y: 120 }, data: { label: 'Firewall' }, type: 'default' },
  { id: '2', position: { x: 320, y: 120 }, data: { label: 'Application' }, type: 'default' },
]

const initialEdges: Edge[] = [{ id: 'e1-2', source: '1', target: '2' }]

export default function GraphView() {
  return (
    <div className="h-full w-full rounded-lg border border-slate-200">
      <ReactFlow nodes={initialNodes} edges={initialEdges} fitView>
        <MiniMap />
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  )
}
