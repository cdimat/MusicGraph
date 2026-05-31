export type NodeType = 'Artist' | 'Release' | 'Track' | 'Label'

export interface NodeAttributes {
  label: string
  nodeType: NodeType
  x: number
  y: number
  size: number
  color: string
  // domain fields
  mbid?: string
  discogs_id?: number
  year?: number
  country?: string
  type?: string
  disambiguation?: string
  role?: string
  instrument?: string
}

export interface EdgeAttributes {
  relType: string
  label?: string
  color?: string
  size?: number
  role?: string
  instrument?: string
  context?: string
}

export interface GraphNode {
  key: string
  attributes: NodeAttributes
}

export interface GraphEdge {
  key: string
  source: string
  target: string
  attributes: EdgeAttributes
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ArtistSearchResult {
  mbid: string
  name: string
  sort_name: string
  type: string
  country: string
  disambiguation: string
  score: number
}

export interface IngestJob {
  job_id: string
  status: 'pending' | 'running' | 'complete' | 'error'
  log: string[]
  mbid: string
  error?: string
}

export const NODE_COLORS: Record<NodeType, string> = {
  Artist: '#6366f1',
  Release: '#10b981',
  Track: '#f59e0b',
  Label: '#ef4444',
}

export const NODE_SIZES: Record<NodeType, number> = {
  Artist: 12,
  Release: 8,
  Track: 5,
  Label: 7,
}
