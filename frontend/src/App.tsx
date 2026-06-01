import { useCallback, useEffect, useRef, useState } from 'react'
import {
  expandNode,
  getArtistGraph,
  mergeGraphData,
} from './api/client'
import { CommandPalette } from './components/CommandPalette'
import { ContextMenu } from './components/ContextMenu'
import { GraphExplorer } from './components/GraphExplorer'
import { LoadingOverlay } from './components/LoadingOverlay'
import { NodeDetail } from './components/NodeDetail'
import { SearchBar } from './components/SearchBar'
import type { ArtistSearchResult, GraphData, NodeType } from './types'


const EXPAND_LABEL: Partial<Record<NodeType, string>> = {
  Release: 'Loading tracks & credits…',
  Track:   'Loading featured artists…',
  Artist:  'Expanding artist connections…',
  Label:   'Loading label releases…',
}

interface ContextMenuState {
  x: number
  y: number
  nodeId: string
  nodeType: NodeType
  nodeLabel: string
}

export function App() {
  const [graphData, setGraphData]     = useState<GraphData | null>(null)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [loading, setLoading]         = useState(false)
  const [loadingMsg, setLoadingMsg]   = useState('')
  const [error, setError]             = useState<string | null>(null)
  const [focusedArtist, setFocusedArtist] = useState<ArtistSearchResult | null>(null)
  const [showPalette, setShowPalette] = useState(false)
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [hiddenNodes, setHiddenNodes] = useState<Set<string>>(new Set())

  // Keep a ref so handleNodeClick never captures a stale handleExpand
  const expandRef = useRef<(id: string, type: string) => Promise<void>>()

  // ----------------------------------------------------------------
  // Cmd+K — open/close command palette
  // ----------------------------------------------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setShowPalette((v) => !v)
      }
      if (e.key === 'Escape') {
        setShowPalette(false)
        setContextMenu(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // ----------------------------------------------------------------
  // Artist selected from search bar
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
  // Expand a node — merges new nodes/edges into the existing graph
  // ----------------------------------------------------------------
  const handleExpand = useCallback(
    async (nodeId: string, nodeType: string) => {
      setLoading(true)
      setLoadingMsg(EXPAND_LABEL[nodeType as NodeType] ?? `Expanding ${nodeType}…`)
      try {
        const expansion = await expandNode(nodeId, nodeType)
        setGraphData((prev) => prev ? mergeGraphData(prev, expansion) : expansion)
        setSelectedNode(nodeId)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Expand failed')
      } finally {
        setLoading(false)
      }
    },
    [],
  )
  expandRef.current = handleExpand

  // ----------------------------------------------------------------
  // Node clicked in the graph
  // ----------------------------------------------------------------
  const handleNodeClick = useCallback((nodeId: string, nodeType: NodeType) => {
    setSelectedNode(nodeId)
    setContextMenu(null)
    expandRef.current?.(nodeId, nodeType)
  }, [])

  // ----------------------------------------------------------------
  // Node right-clicked — show context menu
  // ----------------------------------------------------------------
  const handleNodeRightClick = useCallback(
    (nodeId: string, nodeType: NodeType, nodeLabel: string, x: number, y: number) => {
      setContextMenu({ x, y, nodeId, nodeType, nodeLabel })
    },
    [],
  )

  // ----------------------------------------------------------------
  // Render
  // ----------------------------------------------------------------
  return (
    <div className="relative w-full h-full flex flex-col">
      {/* Top bar */}
      <header className="relative z-10 flex items-center gap-4 px-4 py-3 border-b border-white/10 bg-gray-950/80 backdrop-blur-sm">
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

        <div className="flex-1 max-w-xl">
          <SearchBar onSelect={handleArtistSelect} />
        </div>

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
        {/* Landing / search page */}
        {!graphData && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 px-4">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-white mb-2">Artist Graph Explorer</h1>
              <p className="text-gray-400 text-lg max-w-md">
                Search any artist or band. Click nodes to traverse the full chain:
                Artist → Album → Song → Credits → Artist.
              </p>
            </div>
            <SearchBar onSelect={handleArtistSelect} />
          </div>
        )}

        {/* Graph canvas */}
        {graphData && graphData.nodes.length > 0 && (
          <GraphExplorer
            data={graphData}
            selectedNode={selectedNode}
            hiddenNodes={hiddenNodes}
            onNodeClick={handleNodeClick}
            onNodeRightClick={handleNodeRightClick}
          />
        )}

        {graphData && graphData.nodes.length === 0 && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <p className="text-gray-400 text-lg">No graph data found.</p>
              <button
                onClick={() => setGraphData(null)}
                className="mt-4 text-indigo-400 underline hover:no-underline"
              >
                Back to search
              </button>
            </div>
          </div>
        )}

        {/* Node detail sidebar */}
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
            <button onClick={() => setError(null)} className="ml-2 underline hover:no-underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Context menu */}
        {contextMenu && (
          <ContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            nodeId={contextMenu.nodeId}
            nodeType={contextMenu.nodeType}
            nodeLabel={contextMenu.nodeLabel}
            onExpand={() => {
              handleNodeClick(contextMenu.nodeId, contextMenu.nodeType)
            }}
            onFocus={() => setSelectedNode(contextMenu.nodeId)}
            onCopyId={() => {}}
            onHide={() => setHiddenNodes((prev) => new Set([...prev, contextMenu.nodeId]))}
            onClose={() => setContextMenu(null)}
          />
        )}
      </main>

      {/* Cmd+K command palette */}
      {showPalette && (
        <CommandPalette
          graph={graphData}
          onSelect={(nodeId, nodeType) => {
            setSelectedNode(nodeId)
            expandRef.current?.(nodeId, nodeType)
          }}
          onClose={() => setShowPalette(false)}
        />
      )}
    </div>
  )
}
