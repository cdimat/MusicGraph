import { useEffect, useRef, useState } from 'react'
import type { GraphData, NodeType } from '../types'
import { NODE_COLORS } from '../types'

interface Props {
  graph: GraphData | null
  onSelect: (nodeId: string, nodeType: NodeType) => void
  onClose: () => void
}

const TYPE_ORDER: NodeType[] = ['Artist', 'Release', 'Track', 'Label']

export function CommandPalette({ graph, onSelect, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const nodes = graph?.nodes ?? []
  const filtered = query.trim()
    ? nodes
        .filter((n) => n.attributes.label.toLowerCase().includes(query.toLowerCase()))
        .sort((a, b) => {
          const ai = TYPE_ORDER.indexOf(a.attributes.nodeType)
          const bi = TYPE_ORDER.indexOf(b.attributes.nodeType)
          return ai - bi
        })
        .slice(0, 20)
    : nodes
        .slice()
        .sort((a, b) => TYPE_ORDER.indexOf(a.attributes.nodeType) - TYPE_ORDER.indexOf(b.attributes.nodeType))
        .slice(0, 10)

  // Reset active index when results change
  useEffect(() => setActiveIdx(0), [query])

  function confirm(idx: number) {
    const n = filtered[idx]
    if (n) {
      onSelect(n.key, n.attributes.nodeType)
      onClose()
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      confirm(activeIdx)
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const item = list.children[activeIdx] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/40 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-lg bg-gray-900 border border-white/20 rounded-xl shadow-2xl overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-white/10">
          <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Search loaded nodes…"
            className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none text-sm"
          />
          <kbd className="text-gray-600 text-xs font-mono bg-gray-800 px-1.5 py-0.5 rounded border border-white/10">esc</kbd>
        </div>

        {/* Results */}
        <ul ref={listRef} className="max-h-72 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <li className="px-4 py-3 text-gray-500 text-sm">No nodes match &ldquo;{query}&rdquo;</li>
          ) : (
            filtered.map((n, i) => (
              <li key={n.key}>
                <button
                  onMouseEnter={() => setActiveIdx(i)}
                  onClick={() => confirm(i)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 transition-colors text-left ${
                    i === activeIdx ? 'bg-white/8' : 'hover:bg-white/5'
                  }`}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: NODE_COLORS[n.attributes.nodeType] ?? '#94a3b8' }}
                  />
                  <span className="flex-1 min-w-0 text-white text-sm truncate">{n.attributes.label}</span>
                  {n.attributes.year && (
                    <span className="text-gray-600 text-xs shrink-0 mr-2">{n.attributes.year}</span>
                  )}
                  <span className="text-gray-500 text-xs shrink-0 w-14 text-right">{n.attributes.nodeType}</span>
                </button>
              </li>
            ))
          )}
        </ul>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-white/10 flex items-center justify-between text-gray-600 text-xs">
          <span>{nodes.length} nodes in graph</span>
          <span className="flex items-center gap-2">
            <kbd className="font-mono bg-gray-800 px-1 py-0.5 rounded border border-white/10">↑↓</kbd> navigate
            <kbd className="font-mono bg-gray-800 px-1 py-0.5 rounded border border-white/10">↵</kbd> select
          </span>
        </div>
      </div>
    </div>
  )
}
