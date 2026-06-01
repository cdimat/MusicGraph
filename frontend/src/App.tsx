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


// ----------------------------------------------------------------
// Vinyl record hero illustration
// ----------------------------------------------------------------
function VinylRecord() {
  const grooves = [92, 86, 80, 74, 68, 62, 56, 50, 44, 38, 33]
  return (
    <svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%' }}>
      <defs>
        <radialGradient id="discGrad" cx="42%" cy="38%" r="65%">
          <stop offset="0%"   stopColor="#1c1107" />
          <stop offset="60%"  stopColor="#0e0b06" />
          <stop offset="100%" stopColor="#080604" />
        </radialGradient>
        <radialGradient id="labelGrad" cx="45%" cy="40%" r="60%">
          <stop offset="0%"   stopColor="#c05621" />
          <stop offset="100%" stopColor="#7c2d12" />
        </radialGradient>
        <radialGradient id="sheen" cx="35%" cy="30%" r="50%">
          <stop offset="0%"  stopColor="white" stopOpacity="0.04" />
          <stop offset="100%" stopColor="white" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Disc body */}
      <circle cx="100" cy="100" r="99" fill="#0b0806" />
      <circle cx="100" cy="100" r="97" fill="url(#discGrad)" />

      {/* Groove rings */}
      {grooves.map((r, i) => (
        <circle
          key={r}
          cx="100" cy="100" r={r}
          stroke="#2a1d0c"
          strokeWidth={i % 4 === 0 ? 0.7 : 0.35}
          opacity={i % 4 === 0 ? 0.9 : 0.55}
        />
      ))}

      {/* Surface sheen — light catching the vinyl at an angle */}
      <ellipse cx="72" cy="62" rx="28" ry="14"
        fill="white" fillOpacity="0.025"
        transform="rotate(-35 72 62)" />
      <ellipse cx="136" cy="148" rx="16" ry="7"
        fill="white" fillOpacity="0.015"
        transform="rotate(-35 136 148)" />

      {/* Centre label */}
      <circle cx="100" cy="100" r="26" fill="#7c2d12" />
      <circle cx="100" cy="100" r="24" fill="url(#labelGrad)" />
      <circle cx="100" cy="100" r="21" stroke="#9a3412" strokeWidth="0.5" />

      {/* Label text */}
      <text x="100" y="96" textAnchor="middle"
        fill="#f97316" fillOpacity="0.45"
        fontSize="3.8" fontFamily="Georgia, serif" letterSpacing="1.5">
        MUSICGRAPH
      </text>
      <text x="100" y="104" textAnchor="middle"
        fill="#c2410c" fillOpacity="0.5"
        fontSize="3" fontFamily="Georgia, serif" letterSpacing="0.8">
        ℗ 2025
      </text>

      {/* Centre spindle hole */}
      <circle cx="100" cy="100" r="3.2" fill="#070504" />
    </svg>
  )
}

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
      <header className="relative z-10 flex items-center gap-4 px-4 py-3 border-b border-white/[0.07] bg-[#070504]/90 backdrop-blur-sm">
        <button
          onClick={() => { setGraphData(null); setSelectedNode(null); setFocusedArtist(null) }}
          className="shrink-0 flex items-center gap-2 text-white font-bold text-lg hover:opacity-80 transition-opacity"
        >
          <svg className="w-6 h-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
              <span className="text-amber-600 font-medium">{focusedArtist.name}</span>
            )}
          </span>
        )}
      </header>

      {/* Main area */}
      <main className="relative flex-1 overflow-hidden">
        {/* Landing / search page */}
        {!graphData && !loading && (
          <div className="grain absolute inset-0 flex flex-col items-center justify-center px-4 overflow-hidden">
            {/* Background layers */}
            <div className="ambient-glow" />
            <div className="vignette" />

            {/* All content sits above background layers */}
            <div className="relative z-10 flex flex-col items-center">

              {/* Vinyl record hero */}
              <div className="vinyl-spin mb-10" style={{ width: 172, height: 172 }}>
                <VinylRecord />
              </div>

              {/* Eyebrow label */}
              <p className="text-amber-800 text-xs font-semibold tracking-[0.22em] uppercase mb-4 select-none">
                A Music Discovery Engine
              </p>

              {/* Headline */}
              <h1 className="text-white text-5xl font-bold text-center tracking-tight mb-4 leading-none">
                Artist Graph Explorer
              </h1>

              {/* Subline */}
              <p className="text-stone-500 text-[15px] text-center max-w-xs leading-relaxed mb-9">
                Drop in any artist. Follow the threads — albums, collaborators, credits,
                and the labels behind the music.
              </p>

              {/* Search bar */}
              <div className="w-full" style={{ maxWidth: 440 }}>
                <SearchBar onSelect={handleArtistSelect} />
              </div>

              {/* Feature chips */}
              <div className="flex items-center gap-3 mt-7 select-none">
                {['Artist Graphs', 'Track Credits', 'Record Labels', 'Genius Lyrics'].map((f, i, arr) => (
                  <span key={f} className="flex items-center gap-3">
                    <span className="text-stone-600 text-xs">{f}</span>
                    {i < arr.length - 1 && <span className="chip-dot" />}
                  </span>
                ))}
              </div>

              {/* Keyboard hint */}
              <p className="mt-5 text-stone-700 text-xs select-none">
                <kbd className="font-mono bg-stone-900 border border-stone-800 px-1.5 py-0.5 rounded text-stone-600">⌘K</kbd>
                <span className="ml-2">to search within a loaded graph</span>
              </p>

            </div>
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
                className="mt-4 text-amber-600 underline hover:no-underline"
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
