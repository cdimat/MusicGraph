"""
Neo4j node/relationship type constants and schema setup queries.

Node labels:   Artist, Release, Track, Label
Relationships: MEMBER_OF, COLLABORATED_WITH, CREDITED_ON, RELEASED_BY, PLAYED_ON, CONTAINS
"""

# --- Node label constants ---
ARTIST = "Artist"
RELEASE = "Release"
TRACK = "Track"
LABEL = "Label"

# --- Relationship type constants ---
MEMBER_OF = "MEMBER_OF"
COLLABORATED_WITH = "COLLABORATED_WITH"
CREDITED_ON = "CREDITED_ON"
RELEASED_BY = "RELEASED_BY"
PLAYED_ON = "PLAYED_ON"
CONTAINS = "CONTAINS"

# --- Schema setup ---
CONSTRAINTS = [
    "CREATE CONSTRAINT artist_mbid IF NOT EXISTS FOR (a:Artist) REQUIRE a.mbid IS UNIQUE",
    "CREATE CONSTRAINT release_mbid IF NOT EXISTS FOR (r:Release) REQUIRE r.mbid IS UNIQUE",
    "CREATE CONSTRAINT track_mbid IF NOT EXISTS FOR (t:Track) REQUIRE t.mbid IS UNIQUE",
    "CREATE CONSTRAINT label_mbid IF NOT EXISTS FOR (l:Label) REQUIRE l.mbid IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX artist_name IF NOT EXISTS FOR (a:Artist) ON (a.name)",
    "CREATE INDEX release_title IF NOT EXISTS FOR (r:Release) ON (r.title)",
]

# Sigma.js node colours per type
NODE_COLORS = {
    "Artist": "#6366f1",   # indigo
    "Release": "#10b981",  # emerald
    "Track": "#f59e0b",    # amber
    "Label": "#ef4444",    # red
}

NODE_SIZES = {
    "Artist": 12,
    "Release": 8,
    "Track": 5,
    "Label": 7,
}

EDGE_COLORS = {
    MEMBER_OF: "#8b5cf6",
    COLLABORATED_WITH: "#06b6d4",
    CREDITED_ON: "#84cc16",
    RELEASED_BY: "#f97316",
    PLAYED_ON: "#fb7185",
    CONTAINS: "#94a3b8",
}
