import { useEffect, useRef } from 'react'
import Graph from 'graphology'
import Sigma from 'sigma'
import FA2Layout from 'graphology-layout-forceatlas2/worker'
import type { GraphData, NodeType } from '../types'
import { NODE_COLORS, NODE_SIZES } from '../types'

interface Props {
  data: GraphData
  selectedNode: string | null
  onNodeClick: (nodeId: string, nodeType: NodeType) => void
}

export function GraphExplorer({ data, selectedNode, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sigmaRef = useRef<Sigma | null>(null)
  const layoutRef = useRef<InstanceType<typeof FA2Layout> | null>(null)
  const graphRef = useRef<Graph | null>(null)

  // Build / rebuild graph when data changes
  useEffect(() => {
    if (!containerRef.current) return

    // Cleanup previous instance
    layoutRef.current?.kill()
    sigmaRef.current?.kill()

    const graph = new Graph({ multi: false, type: 'mixed' })
    graphRef.current = graph

    // Add nodes with random initial positions (FA2 will settle them)
    data.nodes.forEach((n) => {
      if (!graph.hasNode(n.key)) {
        graph.addNode(n.key, {
          ...n.attributes,
          x: n.attributes.x ?? (Math.random() - 0.5) * 10,
          y: n.attributes.y ?? (Math.random() - 0.5) * 10,
          size: NODE_SIZES[n.attributes.nodeType as NodeType] ?? 6,
          color: NODE_COLORS[n.attributes.nodeType as NodeType] ?? '#94a3b8',
        })
      }
    })

    // Add edges (skip if either endpoint is missing)
    data.edges.forEach((e) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.key)) {
        try {
          graph.addEdgeWithKey(e.key, e.source, e.target, {
            ...e.attributes,
            color: e.attributes.color ?? '#334155',
            size: 1,
          })
        } catch {
          // Duplicate edge — safe to skip
        }
      }
    })

    // Create Sigma renderer
    const renderer = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: false,
      defaultEdgeColor: '#334155',
      defaultNodeColor: '#6366f1',
      labelColor: { color: '#e2e8f0' },
      labelSize: 12,
      labelWeight: '500',
      edgeLabelColor: { color: '#64748b' },
      nodeReducer: (node, attrs) => ({
        ...attrs,
        highlighted: node === selectedNode,
        zIndex: node === selectedNode ? 1 : 0,
      }),
    })
    sigmaRef.current = renderer

    // ForceAtlas2 layout — run for 3 s then freeze
    const layout = new FA2Layout(graph, {
      settings: {
        gravity: 1,
        scalingRatio: 4,
        slowDown: 5,
        barnesHutOptimize: graph.order > 200,
      },
    })
    layoutRef.current = layout
    layout.start()
    const timer = setTimeout(() => layout.stop(), 3000)

    // Events
    renderer.on('clickNode', ({ node }) => {
      const attrs = graph.getNodeAttributes(node)
      onNodeClick(node, attrs.nodeType as NodeType)
    })

    // Hover effects
    renderer.on('enterNode', ({ node }) => {
      graph.setNodeAttribute(node, 'highlighted', true)
      containerRef.current!.style.cursor = 'pointer'
    })
    renderer.on('leaveNode', ({ node }) => {
      if (node !== selectedNode) graph.setNodeAttribute(node, 'highlighted', false)
      containerRef.current!.style.cursor = 'default'
    })

    return () => {
      clearTimeout(timer)
      layout.kill()
      renderer.kill()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  // Highlight selected node without rebuilding
  useEffect(() => {
    const graph = graphRef.current
    const renderer = sigmaRef.current
    if (!graph || !renderer) return
    graph.forEachNode((node) => {
      graph.setNodeAttribute(node, 'highlighted', node === selectedNode)
    })
    renderer.refresh()

    if (selectedNode && graph.hasNode(selectedNode)) {
      const { x, y } = graph.getNodeAttributes(selectedNode)
      renderer.getCamera().animate({ x, y, ratio: 0.4 }, { duration: 400 })
    }
  }, [selectedNode])

  return <div ref={containerRef} className="w-full h-full" />
}
