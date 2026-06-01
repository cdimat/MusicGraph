"""Local MusicBrainz PostgreSQL client.

Queries the locally-imported MB dump for fast, rate-limit-free artist/label
search. Falls back to the live MusicBrainz API when the local DB is
unavailable or has no data.

Set up:
    Run  scripts/import_mb_dump.py  once to populate the database.
    The script connects to POSTGRES_URI from .env (default: localhost:5432).
"""

import logging
from typing import Any

# psycopg2 is an optional dependency — the local MB dump is a performance
# enhancement, not a hard requirement. If the driver isn't installed (e.g.
# the image hasn't been rebuilt since it was added to requirements), we
# degrade gracefully to the live MusicBrainz API instead of crashing the
# entire backend on import.
try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]
    _PSYCOPG2_AVAILABLE = False

log = logging.getLogger(__name__)


class MusicBrainzLocalClient:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Any = None

    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open connection; return True on success.

        Uses a 5-second connect_timeout so a slow or not-yet-ready
        PostgreSQL container does not block the backend startup thread.
        """
        if not _PSYCOPG2_AVAILABLE:
            log.warning(
                "psycopg2 not installed — local MB DB disabled, using live API. "
                "Rebuild the backend image to enable it: docker compose up -d --build backend"
            )
            self._conn = None
            return False
        try:
            self._conn = psycopg2.connect(self._dsn, connect_timeout=5)
            self._conn.autocommit = True
            log.info("Connected to local MB PostgreSQL database.")
            return True
        except Exception as exc:
            log.warning("Local MB DB unavailable (%s) — using live API.", exc)
            self._conn = None
            return False

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_artists(self, query: str, limit: int = 10) -> list[dict]:
        """Trigram full-text search over local artist table."""
        if not self._conn:
            return []
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT mbid::text AS mbid, name, sort_name, artist_type AS type,
                           disambiguation,
                           similarity(name, %s) AS score
                    FROM mb_artist
                    WHERE name %% %s
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (query, query, limit),
                )
                rows = cur.fetchall()
            return [
                {
                    "mbid": r["mbid"],
                    "name": r["name"],
                    "sort_name": r["sort_name"] or r["name"],
                    "type": r["type"] or "",
                    "country": "",
                    "disambiguation": r["disambiguation"] or "",
                    "score": int((r["score"] or 0) * 100),
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local artist search failed: %s", exc)
            return []

    def search_labels(self, query: str, limit: int = 10) -> list[dict]:
        """Trigram search over local label table."""
        if not self._conn:
            return []
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT mbid::text AS mbid, name, label_type, country, disambiguation,
                           similarity(name, %s) AS score
                    FROM mb_label
                    WHERE name %% %s
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (query, query, limit),
                )
                rows = cur.fetchall()
            return [
                {
                    "mbid": r["mbid"],
                    "name": r["name"],
                    "type": r["label_type"] or "",
                    "country": r["country"] or "",
                    "disambiguation": r["disambiguation"] or "",
                    "score": int((r["score"] or 0) * 100),
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local label search failed: %s", exc)
            return []
