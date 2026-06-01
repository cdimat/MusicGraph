import type { GraphData, GraphEdge, GraphNode, NodeType } from '../types'
import { NODE_COLORS } from '../types'

interface Props {
  nodeId: string
  graph: GraphData
  onExpand: (nodeId: string, nodeType: string) => void
  onClose: () => void
}

function Badge({ type }: { type: NodeType }) {
  const labels: Record<NodeType, string> = {
    Artist:  'Artist',
    Release: 'Album / Release',
    Track:   'Track',
    Label:   'Label',
  }
  return (
    <span
      className="inline-block px-2 py-0.5 rounded-full text-xs font-semibold text-white"
      style={{ background: NODE_COLORS[type] }}
    >
      {labels[type] ?? type}
    </span>
  )
}

const RELATIONSHIP_LABELS: Record<string, string> = {
  CREDITED_ON:       'Released on',
  MEMBER_OF:         'Member of',
  COLLABORATED_WITH: 'Collaborated with',
  PLAYED_ON:         'Played on',
  CONTAINS:          'Contains',
  RELEASED_BY:       'Released by',
}

// ----------------------------------------------------------------
// Credits section — shown for Track nodes
// ----------------------------------------------------------------
function TrackCredits({
  nodeId,
  connectedNodes,
  connectedEdges,
  onExpand,
}: {
  nodeId: string
  connectedNodes: GraphNode[]
  connectedEdges: GraphEdge[]
  onExpand: (id: string, type: string) => void
}) {
  const creditArtists = connectedNodes.filter((n) => n.attributes.nodeType === 'Artist')
  if (creditArtists.length === 0)
    return <p className="text-gray-500 text-sm">No credits loaded yet. Expand the track to fetch them.</p>

  return (
    <div className="mb-4">
      <p className="text-gray-500 text-xs font-semibold uppercase tracking-widest mb-2">
        Credits ({creditArtists.length})
      </p>
      <ul className="space-y-1">
        {creditArtists.map((n) => {
          const edge = connectedEdges.find(
            (e) =>
              (e.source === nodeId && e.target === n.key) ||
              (e.target === nodeId && e.source === n.key),
          )
          const role = edge?.attributes.role
          const instrument = edge?.attributes.instrument
          const creditLine = role || instrument
            ? [instrument, role].filter(Boolean).join(' — ')
            : null
          return (
            <li key={n.key}>
              <button
                onClick={() => onExpand(n.key, n.attributes.nodeType)}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/5 transition-colors flex items-center gap-2"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: NODE_COLORS.Artist }}
                />
                <span className="flex-1 min-w-0">
                  <span className="text-white text-sm truncate block">{n.attributes.label}</span>
                  {creditLine && (
                    <span className="text-amber-400/80 text-xs">{creditLine}</span>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ----------------------------------------------------------------
// Generic connections list (non-Track nodes)
// ----------------------------------------------------------------
function ConnectionGroup({
  type,
  nodes,
  nodeId,
  connectedEdges,
  onExpand,
}: {
  type: string
  nodes: GraphNode[]
  nodeId: string
  connectedEdges: GraphEdge[]
  onExpand: (id: string, type: string) => void
}) {
  const groupLabel = type === 'Label' ? 'Record Labels' : `${type}s`
  return (
    <div className="mb-4">
      <p className="text-gray-500 text-xs font-semibold uppercase tracking-widest mb-2">
        {groupLabel} ({nodes.length})
      </p>
      <ul className="space-y-1">
        {nodes.map((n) => {
          const edge = connectedEdges.find(
            (e) =>
              (e.source === nodeId && e.target === n.key) ||
              (e.target === nodeId && e.source === n.key),
          )
          const relLabel = edge
            ? RELATIONSHIP_LABELS[edge.attributes.relType] ?? edge.attributes.relType
            : ''
          const subLine = edge?.attributes.context || relLabel || null
          return (
            <li key={n.key}>
              <button
                onClick={() => onExpand(n.key, n.attributes.nodeType)}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/5 transition-colors flex items-center gap-2"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: NODE_COLORS[n.attributes.nodeType as NodeType] ?? '#94a3b8' }}
                />
                <span className="flex-1 min-w-0">
                  <span className="text-white text-sm truncate block">{n.attributes.label}</span>
                  {subLine && (
                    <span className="text-gray-500 text-xs">{subLine}</span>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function NodeDetail({ nodeId, graph, onExpand, onClose }: Props) {
  const node = graph.nodes.find((n) => n.key === nodeId)
  if (!node) return null

  const { attributes: a } = node
  const nodeType = a.nodeType as NodeType

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

  // Context hint shown under the node name
  const contextHints: Partial<Record<NodeType, string>> = {
    Release: 'Click to load tracks & label',
    Track:   'Click a credit to explore their graph',
    Artist:  connectedNodes.length === 0 ? 'Click to expand their discography' : undefined,
    Label:   'Click to see releases on this label',
  }
  const hint = contextHints[nodeType]

  // For non-Track nodes, group connections by type (excluding Artists on a Track — those go in Credits)
  const grouped = connectedNodes.reduce<Record<string, GraphNode[]>>((acc, n) => {
    const t = n.attributes.nodeType
    acc[t] = acc[t] ?? []
    acc[t].push(n)
    return acc
  }, {})

  // Preferred display order for connection groups
  const TYPE_ORDER = ['Artist', 'Release', 'Track', 'Label']
  const sortedTypes = Object.keys(grouped).sort(
    (a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b),
  )

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
          {hint && (
            <p className="text-indigo-400/70 text-xs mt-1 leading-snug">{hint}</p>
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
        {a.year     && <Row label="Year"    value={String(a.year)} />}
        {a.country  && <Row label="Country" value={a.country} />}
        {(a as { instrument?: string }).instrument && (
          <Row label="Role" value={(a as { instrument?: string }).instrument!} />
        )}
        {a.mbid && !a.mbid.startsWith('discogs:') && (
          <Row
            label="MusicBrainz"
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
        {nodeType === 'Track' ? (
          <TrackCredits
            nodeId={nodeId}
            connectedNodes={connectedNodes}
            connectedEdges={connectedEdges}
            onExpand={onExpand}
          />
        ) : connectedNodes.length === 0 ? (
          <p className="text-gray-500 text-sm">No connections loaded yet.</p>
        ) : (
          sortedTypes.map((type) => (
            <ConnectionGroup
              key={type}
              type={type}
              nodes={grouped[type]}
              nodeId={nodeId}
              connectedEdges={connectedEdges}
              onExpand={onExpand}
            />
          ))
        )}
      </div>
    </aside>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-gray-500 w-24 shrink-0">{label}</span>
      <span className="text-gray-200 flex-1 min-w-0">{value}</span>
    </div>
  )
}
