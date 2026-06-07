"""Local MusicBrainz PostgreSQL client.

Queries the locally-imported MB dump (see scripts/import_mb_dump.py) so the
app can build artist → album → song → credit graphs without hitting the live
MusicBrainz API and its 1 req/sec rate limit. Every method degrades
gracefully — on any error or empty result the caller falls back to the API.

Slim tables produced by the importer:
    mb_artist(id, gid, name, sort_name, type_id, comment)
    mb_label(id, gid, name, type_id, comment)
    mb_acn(artist_credit, position, artist, join_phrase)
    mb_release_group(id, gid, name, artist_credit, type_id, comment)
    mb_release(id, gid, name, artist_credit, release_group, barcode, comment)
    mb_recording(id, gid, name, artist_credit, length)
    mb_medium(id, release, position)
    mb_track(id, recording, medium, position, number, name, artist_credit, length)
    mb_release_label(release, label)
"""

import logging
from typing import Any

# psycopg2 is an optional dependency — the local MB dump is a performance
# enhancement, not a hard requirement. If the driver isn't installed we
# degrade gracefully to the live MusicBrainz API instead of crashing.
try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]
    _PSYCOPG2_AVAILABLE = False

log = logging.getLogger(__name__)

# MusicBrainz type-id → readable name (abridged to the common values).
ARTIST_TYPE = {1: "Person", 2: "Group", 3: "Orchestra", 4: "Choir", 5: "Character", 6: "Other"}
LABEL_TYPE = {
    1: "Distributor", 2: "Holding", 3: "Production", 4: "Original Production",
    5: "Bootleg Production", 6: "Reissue Production", 7: "Publisher",
}
RELEASE_GROUP_TYPE = {1: "Album", 2: "Single", 3: "EP", 4: "Broadcast", 5: "Other"}


class MusicBrainzLocalClient:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open connection; return True on success.

        Uses a 5-second connect_timeout so a slow or not-yet-ready
        PostgreSQL container does not block the backend startup thread.
        Also verifies the expected tables exist (i.e. the import has run).
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
            if not self._table_exists("mb_artist"):
                log.info("Local MB DB connected but not yet imported — using live API "
                         "until scripts/import_mb_dump.py has run.")
                self._conn.close()
                self._conn = None
                return False
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

    def _table_exists(self, name: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
            return cur.fetchone()[0] is not None

    def _cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_artists(self, query: str, limit: int = 10) -> list[dict]:
        if not self._conn:
            return []
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT gid::text AS mbid, name, sort_name, type_id, comment,
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
                    "type": ARTIST_TYPE.get(r["type_id"], ""),
                    "country": "",
                    "disambiguation": r["comment"] or "",
                    "score": int((r["score"] or 0) * 100),
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local artist search failed: %s", exc)
            return []

    def search_labels(self, query: str, limit: int = 10) -> list[dict]:
        if not self._conn:
            return []
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT gid::text AS mbid, name, type_id, comment,
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
                    "type": LABEL_TYPE.get(r["type_id"], ""),
                    "country": "",
                    "disambiguation": r["comment"] or "",
                    "score": int((r["score"] or 0) * 100),
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local label search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Read paths that mirror MusicBrainzClient method shapes
    # ------------------------------------------------------------------

    def get_artist_release_groups(self, artist_mbid: str) -> list[dict] | None:
        """Release groups credited to an artist. Returns None if not found
        locally so the caller can fall back to the API."""
        if not self._conn:
            return None
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT rg.gid::text AS mbid, rg.name AS title, rg.type_id
                    FROM mb_artist a
                    JOIN mb_acn acn          ON acn.artist = a.id
                    JOIN mb_release_group rg ON rg.artist_credit = acn.artist_credit
                    WHERE a.gid = %s
                    ORDER BY rg.type_id NULLS LAST, rg.name
                    """,
                    (artist_mbid,),
                )
                rows = cur.fetchall()
            if not rows:
                return None
            return [
                {
                    "mbid": r["mbid"],
                    "title": r["title"],
                    "type": RELEASE_GROUP_TYPE.get(r["type_id"], ""),
                    "first_release_date": "",
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local release-group lookup failed: %s", exc)
            return None

    def get_release_group_releases(self, rg_mbid: str) -> list[dict] | None:
        """Releases within a release group."""
        if not self._conn:
            return None
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT r.gid::text AS mbid, r.name AS title, rg.type_id
                    FROM mb_release r
                    JOIN mb_release_group rg ON r.release_group = rg.id
                    WHERE rg.gid = %s
                    ORDER BY r.id
                    """,
                    (rg_mbid,),
                )
                rows = cur.fetchall()
            if not rows:
                return None
            return [
                {
                    "mbid": r["mbid"],
                    "title": r["title"],
                    "year": None,
                    "country": "",
                    "type": RELEASE_GROUP_TYPE.get(r["type_id"], ""),
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local release lookup failed: %s", exc)
            return None

    def get_release_tracks(self, release_mbid: str) -> list[dict] | None:
        """Tracks for a release, each with its artist credits (main + featured).

        Mirrors MusicBrainzClient.get_release_tracks: the track 'mbid' is the
        recording gid, matching how the rest of the app keys Track nodes.
        """
        if not self._conn:
            return None
        try:
            with self._cursor() as cur:
                # Resolve the release once so we can key credits by track id.
                cur.execute(
                    """
                    SELECT t.id AS track_id,
                           rec.gid::text AS rec_mbid,
                           t.name AS title,
                           t.position AS position,
                           rec.length AS duration,
                           t.artist_credit AS ac
                    FROM mb_release rel
                    JOIN mb_medium m   ON m.release = rel.id
                    JOIN mb_track t    ON t.medium = m.id
                    JOIN mb_recording rec ON t.recording = rec.id
                    WHERE rel.gid = %s
                    ORDER BY m.position, t.position
                    """,
                    (release_mbid,),
                )
                trows = cur.fetchall()
                if not trows:
                    return None

                # Fetch all credits for these tracks' artist_credits in one go.
                acs = tuple({r["ac"] for r in trows if r["ac"] is not None})
                credits_by_ac: dict[int, list[dict]] = {}
                if acs:
                    cur.execute(
                        """
                        SELECT acn.artist_credit AS ac, acn.position,
                               a.gid::text AS mbid, a.name, a.sort_name
                        FROM mb_acn acn
                        JOIN mb_artist a ON a.id = acn.artist
                        WHERE acn.artist_credit IN %s
                        ORDER BY acn.artist_credit, acn.position
                        """,
                        (acs,),
                    )
                    for c in cur.fetchall():
                        bucket = credits_by_ac.setdefault(c["ac"], [])
                        bucket.append({
                            "mbid": c["mbid"],
                            "name": c["name"],
                            "sort_name": c["sort_name"] or c["name"],
                            "role": "Featured" if bucket else "Primary",
                        })

            return [
                {
                    "mbid": r["rec_mbid"],
                    "title": r["title"],
                    "position": r["position"],
                    "duration": r["duration"],
                    "isrc": "",
                    "artist_credits": credits_by_ac.get(r["ac"], []),
                }
                for r in trows
            ]
        except Exception as exc:
            log.warning("Local track lookup failed: %s", exc)
            return None

    def get_release_labels(self, release_mbid: str) -> list[dict]:
        """Record labels attached to a release (empty list if none/local miss)."""
        if not self._conn:
            return []
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT l.gid::text AS mbid, l.name
                    FROM mb_release rel
                    JOIN mb_release_label rl ON rl.release = rel.id
                    JOIN mb_label l          ON l.id = rl.label
                    WHERE rel.gid = %s
                    """,
                    (release_mbid,),
                )
                return [{"mbid": r["mbid"], "name": r["name"]} for r in cur.fetchall()]
        except Exception as exc:
            log.warning("Local label lookup failed: %s", exc)
            return []
