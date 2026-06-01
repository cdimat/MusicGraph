"""Disk-backed response cache for MusicBrainz + Discogs API calls.

Uses Python's built-in `shelve` (dbm under the hood) — zero extra dependencies,
persistent across Docker restarts, stored in /app/data/api_cache.

Keys:   "mb:artist:{mbid}", "mb:rg:{mbid}", "mb:release:{mbid}", etc.
TTL:    30 days by default (music metadata rarely changes).
"""

import logging
import os
import shelve
import time
from typing import Any

log = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("CACHE_DIR", "/app/data")
CACHE_PATH = os.path.join(CACHE_DIR, "api_cache")
DEFAULT_TTL = 60 * 60 * 24 * 30  # 30 days in seconds


def _ensure_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def get(key: str) -> Any | None:
    """Return cached value if present and not expired, else None."""
    _ensure_dir()
    try:
        with shelve.open(CACHE_PATH) as db:
            entry = db.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > DEFAULT_TTL:
                del db[key]
                return None
            return entry["value"]
    except Exception as exc:
        log.debug("Cache read failed for %s: %s", key, exc)
        return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Store value in cache with a timestamp."""
    _ensure_dir()
    try:
        with shelve.open(CACHE_PATH) as db:
            db[key] = {"value": value, "ts": time.time(), "ttl": ttl}
    except Exception as exc:
        log.debug("Cache write failed for %s: %s", key, exc)


def invalidate(key: str) -> None:
    _ensure_dir()
    try:
        with shelve.open(CACHE_PATH) as db:
            if key in db:
                del db[key]
    except Exception as exc:
        log.debug("Cache invalidate failed for %s: %s", key, exc)
