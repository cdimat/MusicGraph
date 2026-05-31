import type { GraphData, GraphNode, NodeType } from '../types'
import { NODE_COLORS } from '../types'

interface Props {
  nodeId: string
  graph: GraphData
  onExpand: (nodeId: string, nodeType: string) => void
  onClose: () => void
}

function Badge({ type }: { type: NodeType }) {
  return (
    <span
      className="inline-block px-2 py-0.5 rounded-full text-xs font-semibold text-white"
      style={{ background: NODE_COLORS[type] }}
    >
      {type}
    </span>
  )
}

export function NodeDetail({ nodeId, graph, onExpand, onClose }: Props) {
  const node = graph.nodes.find((n) => n.key === nodeId)
  if (!node) return null

  const { attributes: a } = node
  const nodeType = a.nodeType as NodeType

  // Find all edges connected to this node
  const connectedEdges = graph.edges.filter(
    (e) => e.source === nodeId || e.target === nodeId,
  )

  const connectedNodes: GraphNode[] = []
  const seen = new Set<string>()
  for (const e of connectedEdges) {
    const otherId = e.source === nodeId ? e.target : e.source
    if (!seen.has(otherId)) {
      seen.add(otherId)
      const other = graph.nodes.find((n) => n.key === otherId)
      if (other) connectedNodes.push(other)
    }
  }

  return (
    <aside className="absolute top-0 right-0 h-full w-80 bg-gray-950/95 border-l border-white/10 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-white/10">
        <div className="flex-1 min-w-0">
          <Badge type={nodeType} />
          <h2 className="text-white font-bold text-lg mt-1 truncate">{a.label}</h2>
          {a.disambiguation && (
            <p className="text-gray-400 text-sm truncate">{a.disambiguation}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="ml-2 text-gray-500 hover:text-white transition-colors shrink-0 mt-1"
          aria-label="Close"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Meta */}
      <div className="p-4 border-b border-white/10 space-y-2 text-sm">
        {a.country && <Row label="Country" value={a.country} />}
        {a.year && <Row label="Year" value={String(a.year)} />}
        {a.type && <Row label="Type" value={a.type} />}
        {a.mbid && (
          <Row
            label="MBID"
            value={
              <a
                href={`https://musicbrainz.org/${nodeType.toLowerCase()}/${a.mbid}`}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:text-indigo-300 font-mono text-xs truncate block"
              >
                {a.mbid}
              </a>
            }
          />
        )}
        {a.discogs_id && (
          <Row
            label="Discogs"
            value={
              <a
                href={`https://www.discogs.com/${nodeType.toLowerCase()}/${a.discogs_id}`}
                target="_blank"
                rel="noreferrer"
                className="text-emerald-400 hover:text-emerald-300 font-mono text-xs"
              >
                {a.discogs_id}
              </a>
            }
          />
        )}
      </div>

      {/* Connections */}
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-gray-400 text-xs font-semibold uppercase tracking-widest mb-3">
          {connectedNodes.length} Connections
        </p>
        <ul className="space-y-1">
          {connectedNodes.map((n) => {
            const edge = connectedEdges.find(
              (e) => e.source === n.key || e.target === n.key,
            )
            return (
              <li key={n.key}>
                <button
                  onClick={() => onExpand(n.key, n.attributes.nodeType)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/5 transition-colors flex items-center gap-2"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: NODE_COLORS[n.attributes.nodeType as NodeType] }}
                  />
                  <span className="flex-1 min-w-0">
                    <span className="text-white text-sm truncate block">{n.attributes.label}</span>
                    {edge && (
                      <span className="text-gray-500 text-xs">
                        {edge.attributes.label ?? edge.attributes.relType}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>

      {/* Expand button (for Artist nodes) */}
      {nodeType === 'Artist' && (
        <div className="p-4 border-t border-white/10">
          <button
            onClick={() => onExpand(nodeId, nodeType)}
            className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-semibold transition-colors"
          >
            Expand Artist Graph
          </button>
        </div>
      )}
    </aside>
  )
}

function Row({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-gray-500 w-20 shrink-0">{label}</span>
      <span className="text-gray-200 flex-1 min-w-0">{value}</span>
    </div>
  )
}
