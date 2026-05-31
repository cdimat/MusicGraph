import { useEffect, useRef, useState } from 'react'
import { searchArtists } from '../api/client'
import type { ArtistSearchResult } from '../types'

interface Props {
  onSelect: (artist: ArtistSearchResult) => void
}

export function SearchBar({ onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ArtistSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (query.length < 2) {
      setResults([])
      setOpen(false)
      return
    }
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await searchArtists(query, 8)
        setResults(r)
        setOpen(true)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 350)
  }, [query])

  function handleSelect(artist: ArtistSearchResult) {
    setQuery(artist.name)
    setOpen(false)
    onSelect(artist)
  }

  return (
    <div className="relative w-full max-w-xl">
      <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus-within:border-indigo-500 transition-colors">
        <svg className="w-5 h-5 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
        </svg>
        <input
          type="text"
          placeholder="Search artists, bands, musicians…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          className="flex-1 bg-transparent outline-none text-white placeholder-gray-500 text-lg"
          autoFocus
        />
        {loading && (
          <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin shrink-0" />
        )}
      </div>

      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-2 w-full bg-gray-900 border border-white/10 rounded-xl overflow-hidden shadow-2xl">
          {results.map((a) => (
            <li key={a.mbid}>
              <button
                onMouseDown={() => handleSelect(a)}
                className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center gap-3"
              >
                <span className={`shrink-0 w-2 h-2 rounded-full ${
                  a.type === 'Group' ? 'bg-emerald-400' : 'bg-indigo-400'
                }`} />
                <span className="flex-1 min-w-0">
                  <span className="text-white font-medium truncate block">{a.name}</span>
                  {(a.disambiguation || a.country) && (
                    <span className="text-gray-500 text-sm truncate block">
                      {[a.disambiguation, a.country].filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-gray-600 uppercase tracking-wide">
                  {a.type || 'Artist'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
