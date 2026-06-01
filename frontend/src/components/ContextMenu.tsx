import { useEffect, useRef } from 'react'
import type { NodeType } from '../types'

interface Props {
  x: number
  y: number
  nodeId: string
  nodeType: NodeType
  nodeLabel: string
  onExpand: () => void
  onFocus: () => void
  onCopyId: () => void
  onHide: () => void
  onClose: () => void
}

interface Item {
  label: string
  icon: React.ReactNode
  onClick: () => void
  danger?: boolean
  separator?: boolean
}

export function ContextMenu({
  x, y, nodeId, nodeLabel,
  onExpand, onFocus, onCopyId, onHide, onClose,
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose()
    }
    // Slight delay so the same right-click that opened it doesn't immediately close it
    const t = setTimeout(() => document.addEventListener('mousedown', handle), 50)
    return () => { clearTimeout(t); document.removeEventListener('mousedown', handle) }
  }, [onClose])

  // Clamp to viewport
  const style: React.CSSProperties = {
    position: 'fixed',
    left: Math.min(x, window.innerWidth - 192),
    top: Math.min(y, window.innerHeight - 180),
  }

  const items: Item[] = [
    {
      label: 'Expand connections',
      icon: <ExpandIcon />,
      onClick: onExpand,
    },
    {
      label: 'Focus here',
      icon: <FocusIcon />,
      onClick: onFocus,
    },
    {
      label: 'Copy MBID',
      icon: <CopyIcon />,
      onClick: () => { navigator.clipboard.writeText(nodeId).catch(() => {}) },
      separator: true,
    },
    {
      label: 'Hide node',
      icon: <HideIcon />,
      onClick: onHide,
      danger: true,
    },
  ]

  return (
    <div ref={menuRef} style={style} className="z-50 w-48 bg-gray-900 border border-white/15 rounded-xl shadow-2xl overflow-hidden py-1">
      {/* Header */}
      <p className="px-3 pt-1 pb-2 text-gray-500 text-xs font-semibold truncate border-b border-white/10 mb-1">
        {nodeLabel}
      </p>

      {items.map((item) => (
        <div key={item.label}>
          {item.separator && <div className="h-px bg-white/10 my-1" />}
          <button
            onClick={() => { item.onClick(); onClose() }}
            className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-sm transition-colors hover:bg-white/5 ${
              item.danger ? 'text-red-400' : 'text-gray-200'
            }`}
          >
            <span className="w-4 h-4 shrink-0 text-gray-500">{item.icon}</span>
            {item.label}
          </button>
        </div>
      ))}
    </div>
  )
}

// ---- small SVG icons ----

function ExpandIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <circle cx="8" cy="8" r="2.5" />
      <circle cx="2" cy="4" r="1.5" />
      <circle cx="14" cy="4" r="1.5" />
      <circle cx="2" cy="12" r="1.5" />
      <circle cx="14" cy="12" r="1.5" />
      <line x1="8" y1="5.5" x2="3" y2="5" />
      <line x1="8" y1="5.5" x2="13" y2="5" />
      <line x1="8" y1="10.5" x2="3" y2="11" />
      <line x1="8" y1="10.5" x2="13" y2="11" />
    </svg>
  )
}

function FocusIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <circle cx="8" cy="8" r="3" />
      <line x1="8" y1="1" x2="8" y2="4" />
      <line x1="8" y1="12" x2="8" y2="15" />
      <line x1="1" y1="8" x2="4" y2="8" />
      <line x1="12" y1="8" x2="15" y2="8" />
    </svg>
  )
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <rect x="5" y="5" width="8" height="9" rx="1.5" />
      <path d="M3 11V3a1 1 0 011-1h7" />
    </svg>
  )
}

function HideIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
      <path d="M2 2l12 12" />
      <path d="M6.5 3.5A7.7 7.7 0 018 3c3.5 0 6 3 6 5a7.2 7.2 0 01-1.5 2.5" />
      <path d="M4 5.5A7 7 0 002 8c0 2 2.5 5 6 5a6.5 6.5 0 003.5-1" />
    </svg>
  )
}
