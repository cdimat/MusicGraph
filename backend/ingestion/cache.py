"""Disk-backed response cache for MusicBrainz + Discogs API calls.

Uses Python's built-in `shelve` (dbm under the hood) — zero extra dependencies,
persistent across Docker restarts, stored in /app/data/api_cache.

Performance note
----------------
The shelve handle is opened ONCE and kept open for the process lifetime,
guarded by a lock. The previous implementation called `shelve.open()` on every
get/set, which re-reads/rewrites the dbm index file on each call — catastrophic
during ingestion, which performs hundreds of cache operations. Keeping a single
handle open turns each operation into an in-process dict-like lookup plus an
occasional `sync()` to flush writes to disk.

Keys:   "mb:artist:{mbid}", "mb:rg:{mbid}", "mb:release:{mbid}", etc.
TTL:    30 days by default (music metadata rarely changes).
"""

import atexit
import logging
import os
import shelve
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("CACHE_DIR", "/app/data")
CACHE_PATH = os.path.join(CACHE_DIR, "api_cache")
DEFAULT_TTL = 60 * 60 * 24 * 30  # 30 days in seconds

# Single long-lived shelve handle + lock guarding all access.
_lock = threading.Lock()
_db: shelve.Shelf | None = None


def _get_db() -> shelve.Shelf:
    """Return the shared shelve handle, opening it once on first use."""
    global _db
    if _db is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        _db = shelve.open(CACHE_PATH, writeback=False)
        atexit.register(_close)
    return _db


def _close() -> None:
    global _db
    if _db is not None:
        try:
            _db.close()
        except Exception:
            pass
        _db = None


def get(key: str) -> Any | None:
    """Return cached value if present and not expired, else None."""
    try:
        with _lock:
            db = _get_db()
            entry = db.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > entry.get("ttl", DEFAULT_TTL):
                del db[key]
                db.sync()
                return None
            return entry["value"]
    except Exception as exc:
        log.debug("Cache read failed for %s: %s", key, exc)
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Store value in cache with a timestamp."""
    try:
        with _lock:
            db = _get_db()
            db[key] = {"value": value, "ts": time.time(), "ttl": ttl}
            db.sync()
    except Exception as exc:
        log.debug("Cache write failed for %s: %s", key, exc)


def invalidate(key: str) -> None:
    try:
        with _lock:
            db = _get_db()
            if key in db:
                del db[key]
                db.sync()
    except Exception as exc:
        log.debug("Cache invalidate failed for %s: %s", key, exc)
