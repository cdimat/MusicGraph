import { useEffect, useRef } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import Sigma from 'sigma'
import type { GraphData, NodeAttributes, NodeType } from '../types'
import { NODE_COLORS } from '../types'

const NODE_SIZES: Record<NodeType, number> = {
  Artist:  22,
  Release: 14,
  Track:   9,
  Label:   12,
}

interface Props {
  data: GraphData
  selectedNode: string | null
  hiddenNodes: Set<string>
  onNodeClick: (nodeId: string, nodeType: NodeType) => void
  onNodeRightClick: (nodeId: string, nodeType: NodeType, nodeLabel: string, x: number, y: number) => void
}

/**
 * Dark-theme hover renderer — replaces sigma's default white box.
 * Draws a dark pill behind the node label so text is always readable.
 */
function darkHoverRenderer(
  context: CanvasRenderingContext2D,
  data: { x: number; y: number; size: number; label?: string },
  settings: { labelSize: number; labelFont: string; labelWeight: string },
) {
  if (!data.label) return

  const { labelSize: size, labelFont: font, labelWeight: weight } = settings
  context.font = `${weight} ${size}px ${font}`
  const textW = context.measureText(data.label).width

  const pad  = 5
  const rx   = data.x + data.size + pad       // pill left edge
  const ry   = data.y - size / 2 - pad        // pill top edge
  const rw   = textW + pad * 2                // pill width
  const rh   = size  + pad * 2               // pill height
  const r    = 5                              // corner radius

  // Dark background pill
  context.fillStyle = 'rgba(2, 6, 23, 0.92)'
  context.strokeStyle = 'rgba(255,255,255,0.12)'
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(rx + r, ry)
  context.lineTo(rx + rw - r, ry)
  context.arcTo(rx + rw, ry,      rx + rw, ry + r,      r)
  context.lineTo(rx + rw, ry + rh - r)
  context.arcTo(rx + rw, ry + rh, rx + rw - r, ry + rh, r)
  context.lineTo(rx + r, ry + rh)
  context.arcTo(rx,      ry + rh, rx,      ry + rh - r, r)
  context.lineTo(rx, ry + r)
  context.arcTo(rx,      ry,      rx + r,  ry,           r)
  context.closePath()
  context.fill()
  context.stroke()

  // Label text
  context.fillStyle = '#f8fafc'
  context.fillText(data.label, rx + pad, data.y + size / 4)
}

/**
 * Find a starting position for a new node near an already-placed neighbour,
 * so freshly-added nodes don't all spawn at the origin and fly across the
 * canvas during the layout pass. Returns null when no neighbour is placed yet.
 */
function seedPosition(
  key: string,
  edges: GraphData['edges'],
  graph: Graph,
): { x: number; y: number } | null {
  for (const e of edges) {
    const other = e.source === key ? e.target : e.target === key ? e.source : null
    if (other && graph.hasNode(other)) {
      const a = graph.getNodeAttributes(other)
      return { x: a.x + (Math.random() - 0.5) * 2, y: a.y + (Math.random() - 0.5) * 2 }
    }
  }
  return null
}

export function GraphExplorer({ data, selectedNode, hiddenNodes, onNodeClick, onNodeRightClick }: Props) {
  const wrapperRef  = useRef<HTMLDivElement>(null)
  const sigmaRef    = useRef<Sigma | null>(null)
  const graphRef    = useRef<Graph | null>(null)
  const selectedRef = useRef<string | null>(selectedNode)
  const hiddenRef   = useRef<Set<string>>(hiddenNodes)

  // Keep latest callbacks in refs so the one-time renderer setup never
  // needs re-subscription when a parent re-render changes their identity.
  const onNodeClickRef      = useRef(onNodeClick)
  const onNodeRightClickRef = useRef(onNodeRightClick)
  onNodeClickRef.current      = onNodeClick
  onNodeRightClickRef.current = onNodeRightClick

  // ----------------------------------------------------------------
  // Create the graph + Sigma renderer ONCE on mount.
  //
  // Data changes are applied incrementally (see the effect below) — we
  // never kill and rebuild the WebGL context on every expand. That full
  // teardown + 120-iteration relayout was the main source of interactive
  // lag and the jarring full-graph reshuffle on each click.
  // ----------------------------------------------------------------
  useEffect(() => {
    const wrapper = wrapperRef.current
    if (!wrapper) return

    const graph = new Graph({ multi: false, type: 'directed' })
    graphRef.current = graph

    const renderer = new Sigma(graph, wrapper, {
      allowInvalidContainer: true,
      renderEdgeLabels: false,
      defaultEdgeColor: '#475569',
      defaultNodeColor: '#6366f1',
      labelColor:  { color: '#f1f5f9' },
      labelSize:   15,
      labelWeight: 'bold',
      labelRenderedSizeThreshold: 4,
      zIndex: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      hoverRenderer: darkHoverRenderer as any,
      nodeReducer: (node, attrs) => {
        if (hiddenRef.current.has(node)) return { ...attrs, hidden: true }
        const isSelected = node === selectedRef.current
        return {
          ...attrs,
          highlighted: isSelected,
          size:   isSelected ? attrs.size * 1.5 : attrs.size,
          zIndex: isSelected ? 2 : 0,
          color:  selectedRef.current && !isSelected
            ? attrs.color + '80'
            : attrs.color,
        }
      },
      edgeReducer: (_edge, attrs) => ({
        ...attrs,
        size:  selectedRef.current ? 1 : 2,
        color: selectedRef.current ? '#1e293b' : attrs.color,
      }),
    })
    sigmaRef.current = renderer

    // ----------------------------------------------------------------
    // Drag — sigma's downNode for hit-detection, then capture native
    // mousemove in the capture phase so sigma's camera doesn't pan.
    // ----------------------------------------------------------------
    let dragNode: string | null = null
    let didDrag = false

    renderer.on('downNode', ({ node }) => {
      dragNode = node
      didDrag  = false
      wrapper.style.cursor = 'grabbing'
    })

    const onMouseMove = (e: MouseEvent) => {
      if (!dragNode) return
      didDrag = true
      e.stopPropagation()
      const rect = wrapper.getBoundingClientRect()
      const pos  = renderer.viewportToGraph({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      })
      graph.setNodeAttribute(dragNode, 'x', pos.x)
      graph.setNodeAttribute(dragNode, 'y', pos.y)
    }

    const onMouseUp = () => {
      dragNode = null
      wrapper.style.cursor = 'default'
    }

    wrapper.addEventListener('mousemove', onMouseMove, true)
    window.addEventListener('mouseup', onMouseUp)

    renderer.on('clickNode', ({ node }) => {
      if (didDrag) { didDrag = false; return }
      const attrs = graph.getNodeAttributes(node)
      onNodeClickRef.current(node, attrs.nodeType as NodeType)
    })

    const onContextMenu = (e: MouseEvent) => e.preventDefault()
    wrapper.addEventListener('contextmenu', onContextMenu)

    renderer.on('rightClickNode', ({ node, event }) => {
      const attrs = graph.getNodeAttributes(node)
      const native = event.original as MouseEvent
      onNodeRightClickRef.current(
        node,
        attrs.nodeType as NodeType,
        attrs.label as string,
        native.clientX,
        native.clientY,
      )
    })

    renderer.on('enterNode', () => {
      if (!dragNode) wrapper.style.cursor = 'grab'
    })
    renderer.on('leaveNode', () => {
      if (!dragNode) wrapper.style.cursor = 'default'
    })

    return () => {
      wrapper.removeEventListener('mousemove', onMouseMove, true)
      wrapper.removeEventListener('contextmenu', onContextMenu)
      window.removeEventListener('mouseup', onMouseUp)
      renderer.kill()
      sigmaRef.current = null
      graphRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----------------------------------------------------------------
  // Incrementally sync `data` into the existing graph.
  //
  // Only new nodes/edges are added (seeded near an existing neighbour so
  // they don't appear at the origin), and nodes no longer present are
  // dropped. A short layout pass runs only when the structure changed —
  // so re-selecting an already-loaded node costs nothing.
  // ----------------------------------------------------------------
  useEffect(() => {
    const graph    = graphRef.current
    const renderer = sigmaRef.current
    if (!graph || !renderer) return

    const wasEmpty     = graph.order === 0
    const desiredNodes = new Set(data.nodes.map((n) => n.key))

    // Drop nodes (and their edges) that are no longer present — e.g. after
    // resetting to a brand-new artist graph.
    const toRemove: string[] = []
    graph.forEachNode((key) => { if (!desiredNodes.has(key)) toRemove.push(key) })
    toRemove.forEach((key) => graph.dropNode(key))

    // Add new nodes, seeding each near an already-positioned neighbour.
    let addedNodes = 0
    data.nodes.forEach((n) => {
      if (graph.hasNode(n.key)) return
      const { type: mbType, ...rest } = n.attributes as NodeAttributes & { type?: string }
      const seed = seedPosition(n.key, data.edges, graph)
      graph.addNode(n.key, {
        ...rest,
        mbType,
        type: 'circle',
        x: seed ? seed.x : (typeof n.attributes.x === 'number' ? n.attributes.x : (Math.random() - 0.5) * 10),
        y: seed ? seed.y : (typeof n.attributes.y === 'number' ? n.attributes.y : (Math.random() - 0.5) * 10),
        size:  NODE_SIZES[n.attributes.nodeType as NodeType] ?? 8,
        color: NODE_COLORS[n.attributes.nodeType as NodeType] ?? '#94a3b8',
      })
      addedNodes++
    })

    // Add new edges (skip any whose endpoints aren't both present).
    data.edges.forEach((e) => {
      if (graph.hasEdge(e.key)) return
      if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) return
      try {
        graph.addDirectedEdgeWithKey(e.key, e.source, e.target, {
          ...e.attributes,
          color: e.attributes.color ?? '#475569',
          size: 2,
        })
      } catch { /* skip duplicate */ }
    })

    const structureChanged = addedNodes > 0 || toRemove.length > 0

    // Relayout only when the structure changed. Use a full relax for the
    // first build (everything starts from random positions) and a brief
    // pass for incremental additions (existing nodes are already settled,
    // so few iterations are needed to place the new ones).
    if (structureChanged) {
      try {
        forceAtlas2.assign(graph, {
          iterations: wasEmpty ? 120 : 40,
          settings: { gravity: 1, scalingRatio: 6, slowDown: 5 },
        })
      } catch (e) {
        console.warn('FA2 skipped:', e)
      }
    }

    renderer.refresh()
    if (wasEmpty) setTimeout(() => fitGraph(), 80)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  // ----------------------------------------------------------------
  // Sync selected node highlight without full rebuild
  // ----------------------------------------------------------------
  useEffect(() => {
    selectedRef.current = selectedNode
    const renderer = sigmaRef.current
    if (!renderer) return
    renderer.refresh()

    const graph = graphRef.current
    if (selectedNode && graph?.hasNode(selectedNode)) {
      const { x, y } = graph.getNodeAttributes(selectedNode)
      renderer.getCamera().animate({ x, y, ratio: 0.5 }, { duration: 400 })
    }
  }, [selectedNode])

  // ----------------------------------------------------------------
  // Sync hidden nodes without full rebuild
  // ----------------------------------------------------------------
  useEffect(() => {
    hiddenRef.current = hiddenNodes
    sigmaRef.current?.refresh()
  }, [hiddenNodes])

  // ----------------------------------------------------------------
  // Camera controls
  // ----------------------------------------------------------------
  function zoomIn()  { sigmaRef.current?.getCamera().animatedZoom({ duration: 250 }) }
  function zoomOut() { sigmaRef.current?.getCamera().animatedUnzoom({ duration: 250 }) }

  function cleanLayout() {
    const graph = graphRef.current
    const renderer = sigmaRef.current
    if (!graph || !renderer) return
    try {
      forceAtlas2.assign(graph, {
        iterations: 200,
        settings: { gravity: 1.2, scalingRatio: 8, slowDown: 8 },
      })
    } catch { /* skip if graph is empty */ }
    renderer.refresh()
    setTimeout(() => fitGraph(), 120)
  }

  function fitGraph() {
    const graph    = graphRef.current
    const renderer = sigmaRef.current
    if (!graph || !renderer) return
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    graph.forEachNode((_, a) => {
      if (a.x < minX) minX = a.x;  if (a.x > maxX) maxX = a.x
      if (a.y < minY) minY = a.y;  if (a.y > maxY) maxY = a.y
    })
    if (!isFinite(minX)) { renderer.getCamera().animatedReset({ duration: 300 }); return }
    const pad  = 1.5
    const cx   = (minX + maxX) / 2
    const cy   = (minY + maxY) / 2
    const { width, height } = renderer.getDimensions()
    const ratio = Math.max((maxX - minX + pad) / width, (maxY - minY + pad) / height) * 1.2
    renderer.getCamera().animate({ x: cx, y: cy, ratio }, { duration: 400 })
  }

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      {/* Sigma canvas */}
      <div ref={wrapperRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Zoom / fit / layout controls — bottom right */}
      <div className="absolute bottom-5 right-5 flex flex-col gap-1.5 z-10">
        {([
          { label: '+',  title: 'Zoom in',      fn: zoomIn      },
          { label: '−',  title: 'Zoom out',     fn: zoomOut     },
          { label: '⊙',  title: 'Fit graph',    fn: fitGraph    },
          { label: '⟳',  title: 'Clean layout', fn: cleanLayout },
        ] as const).map(({ label, title, fn }) => (
          <button
            key={label}
            onClick={fn}
            title={title}
            className="w-9 h-9 bg-gray-900/90 border border-white/10 rounded-lg text-white text-lg font-semibold flex items-center justify-center hover:bg-gray-700 active:scale-95 transition-all shadow-lg select-none"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Legend — bottom left */}
      <div className="absolute bottom-5 left-5 bg-gray-900/80 border border-white/10 rounded-xl px-3 py-2.5 backdrop-blur-sm z-10 select-none">
        <p className="text-gray-500 text-xs font-semibold uppercase tracking-wider mb-2">Legend</p>
        {(
          [
            ['Artist / Band',   '#6366f1'],
            ['Album / Release', '#10b981'],
            ['Track',           '#f59e0b'],
            ['Label',           '#ef4444'],
          ] as [string, string][]
        ).map(([label, color]) => (
          <div key={label} className="flex items-center gap-2 text-gray-300 text-xs mb-1 last:mb-0">
            <span className="w-3 h-3 rounded-full shrink-0" style={{ background: color }} />
            {label}
          </div>
        ))}
      </div>

      {/* Usage hints — fade out once a node is selected */}
      {!selectedNode && (
        <div className="absolute top-4 right-4 text-gray-600 text-xs text-right pointer-events-none select-none leading-relaxed">
          <p>Click artist to expand · Right-click any node for options</p>
          <p>Drag node to reposition · ⟳ to re-run layout</p>
          <p>Scroll to zoom · Drag canvas to pan · ⌘K to search</p>
        </div>
      )}
    </div>
  )
}
