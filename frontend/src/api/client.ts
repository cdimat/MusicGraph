import type { ArtistSearchResult, GraphData, IngestJob } from '../types'

const BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

export function searchArtists(q: string, limit = 10): Promise<ArtistSearchResult[]> {
  return request(`/api/artists/search?q=${encodeURIComponent(q)}&limit=${limit}`)
}

export function getArtistGraph(mbid: string): Promise<GraphData> {
  return request(`/api/graph/artist/${encodeURIComponent(mbid)}`)
}

export function expandNode(nodeId: string, nodeType: string): Promise<GraphData> {
  return request('/api/graph/expand', {
    method: 'POST',
    body: JSON.stringify({ node_id: nodeId, node_type: nodeType }),
  })
}

export function triggerIngest(mbid: string, depth = 1): Promise<{ job_id: string; status: string }> {
  return request('/api/ingest', {
    method: 'POST',
    body: JSON.stringify({ mbid, depth }),
  })
}

export function getIngestStatus(jobId: string): Promise<IngestJob> {
  return request(`/api/ingest/status/${jobId}`)
}

/** Merge new nodes/edges into an existing graph without duplicating keys. */
export function mergeGraphData(existing: GraphData, incoming: GraphData): GraphData {
  const nodeKeys = new Set(existing.nodes.map((n) => n.key))
  const edgeKeys = new Set(existing.edges.map((e) => e.key))

  return {
    nodes: [
      ...existing.nodes,
      ...incoming.nodes.filter((n) => !nodeKeys.has(n.key)),
    ],
    edges: [
      ...existing.edges,
      ...incoming.edges.filter((e) => !edgeKeys.has(e.key)),
    ],
  }
}
