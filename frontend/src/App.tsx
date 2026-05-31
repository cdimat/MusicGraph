import { useCallback, useState } from 'react'
import {
  expandNode,
  getArtistGraph,
  mergeGraphData,
} from './api/client'
import { GraphExplorer } from './components/GraphExplorer'
import { LoadingOverlay } from './components/LoadingOverlay'
import { NodeDetail } from './components/NodeDetail'
import { SearchBar } from './components/SearchBar'
import type { ArtistSearchResult, GraphData, NodeType } from './types'

// Legend entry
function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-gray-400">
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
      {label}
    </span>
  )
}

export function App() {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [focusedArtist, setFocusedArtist] = useState<ArtistSearchResult | null>(null)

  // ----------------------------------------------------------------
  // Artist selected from search
  // ----------------------------------------------------------------
  async function handleArtistSelect(artist: ArtistSearchResult) {
    setError(null)
    setLoading(true)
    setLoadingMsg(`Building graph for ${artist.name}…`)
    setFocusedArtist(artist)
    setSelectedNode(null)
    try {
      const data = await getArtistGraph(artist.mbid)
      setGraphData(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load graph')
      setGraphData(null)
    } finally {
      setLoading(false)
    }
  }

  // ----------------------------------------------------------------
  // Node clicked in graph
  // ----------------------------------------------------------------
  const handleNodeClick = useCallback((nodeId: string, _nodeType: NodeType) => {
    setSelectedNode(nodeId)
  }, [])

  // ----------------------------------------------------------------
  // Expand a node (from NodeDetail sidebar or double-click)
  // ----------------------------------------------------------------
  const handleExpand = useCallback(
    async (nodeId: string, nodeType: string) => {
      if (!graphData) return
      setLoading(true)
      setLoadingMsg(`Expanding ${nodeType} connections…`)
      try {
        const expansion = await expandNode(nodeId, nodeType)
        setGraphData((prev) => mergeGraphData(prev!, expansion))
        setSelectedNode(nodeId)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Expand failed')
      } finally {
        setLoading(false)
      }
    },
    [graphData],
  )

  // ----------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------
  return (
    <div className="relative w-full h-full flex flex-col">
      {/* Top bar */}
      <header className="relative z-10 flex items-center gap-4 px-4 py-3 border-b border-white/10 bg-gray-950/80 backdrop-blur-sm">
        {/* Logo */}
        <button
          onClick={() => { setGraphData(null); setSelectedNode(null); setFocusedArtist(null) }}
          className="shrink-0 flex items-center gap-2 text-white font-bold text-lg hover:opacity-80 transition-opacity"
        >
          <svg className="w-6 h-6 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <circle cx="12" cy="12" r="3" strokeWidth={2} />
            <circle cx="4"  cy="6"  r="2" strokeWidth={2} />
            <circle cx="20" cy="6"  r="2" strokeWidth={2} />
            <circle cx="4"  cy="18" r="2" strokeWidth={2} />
            <circle cx="20" cy="18" r="2" strokeWidth={2} />
            <line x1="12" y1="9"  x2="4"  y2="7"  strokeWidth={1.5} />
            <line x1="12" y1="9"  x2="20" y2="7"  strokeWidth={1.5} />
            <line x1="12" y1="15" x2="4"  y2="17" strokeWidth={1.5} />
            <line x1="12" y1="15" x2="20" y2="17" strokeWidth={1.5} />
          </svg>
          <span className="hidden sm:inline">MusicGraph</span>
        </button>

        {/* Search */}
        <div className="flex-1 max-w-xl">
          <SearchBar onSelect={handleArtistSelect} />
        </div>

        {/* Stats */}
        {graphData && (
          <span className="hidden md:flex items-center gap-3 text-xs text-gray-500">
            <span>{graphData.nodes.length} nodes</span>
            <span>{graphData.edges.length} edges</span>
            {focusedArtist && (
              <span className="text-indigo-400 font-medium">{focusedArtist.name}</span>
            )}
          </span>
        )}
      </header>

      {/* Main area */}
      <main className="relative flex-1 overflow-hidden">
        {!graphData && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 px-4">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-white mb-2">Artist Graph Explorer</h1>
              <p className="text-gray-400 text-lg max-w-md">
                Search any artist or band to explore their connections — collaborators,
                band members, releases, and musician credits from MusicBrainz + Discogs.
              </p>
            </div>

            <SearchBar onSelect={handleArtistSelect} />

            <div className="flex flex-wrap justify-center gap-4 mt-4">
              <LegendDot color="#6366f1" label="Artist / Band" />
              <LegendDot color="#10b981" label="Release" />
              <LegendDot color="#f59e0b" label="Track" />
              <LegendDot color="#ef4444" label="Label" />
            </div>
          </div>
        )}

        {graphData && (
          <GraphExplorer
            data={graphData}
            selectedNode={selectedNode}
            onNodeClick={handleNodeClick}
          />
        )}

        {selectedNode && graphData && (
          <NodeDetail
            nodeId={selectedNode}
            graph={graphData}
            onExpand={handleExpand}
            onClose={() => setSelectedNode(null)}
          />
        )}

        {loading && <LoadingOverlay message={loadingMsg} />}

        {error && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-red-900/80 border border-red-500/50 text-red-200 px-4 py-2 rounded-lg text-sm max-w-sm text-center">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
