"""Genius API client — lyrics metadata and song credits.

Fetches song descriptions, writer/producer credits, and Genius URLs
for Track nodes. All responses are cached to disk.

Rate limit: generous for read requests with a valid token.
"""

import time
from typing import Any

import httpx

from ingestion import cache


class GeniusClient:
    _BASE = "https://api.genius.com"

    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "MusicGraph/1.0",
            },
            timeout=10,
        )
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.3:
            time.sleep(0.3 - elapsed)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------

    def search_song(self, title: str, artist_name: str) -> dict | None:
        """Find the best-matching Genius song for a title + artist.

        Returns a lightweight hit dict or None if not found.
        """
        cache_key = f"genius:search:{title.lower()}:{artist_name.lower()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached or None  # None stored as False to distinguish miss vs no-result

        self._throttle()
        try:
            resp = self._client.get(
                f"{self._BASE}/search",
                params={"q": f"{title} {artist_name}"},
            )
            resp.raise_for_status()
        except Exception:
            return None

        hits = resp.json().get("response", {}).get("hits", [])
        result = self._best_hit(hits, artist_name)
        cache.set(cache_key, result if result else False)
        return result

    def get_song_details(self, genius_id: int) -> dict | None:
        """Fetch full song metadata including credits and description."""
        cache_key = f"genius:song:{genius_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached or None

        self._throttle()
        try:
            resp = self._client.get(
                f"{self._BASE}/songs/{genius_id}",
                params={"text_format": "plain"},
            )
            resp.raise_for_status()
        except Exception:
            return None

        song: dict[str, Any] = resp.json().get("response", {}).get("song", {})
        if not song:
            cache.set(cache_key, False)
            return None

        data: dict[str, Any] = {
            "id": genius_id,
            "title": song.get("title", ""),
            "url": song.get("url", ""),
            "description": (song.get("description") or {}).get("plain", ""),
            "release_date": song.get("release_date_with_abbreviated_month_for_display", ""),
            "writers": [a["name"] for a in song.get("writer_artists", []) if a.get("name")],
            "producers": [a["name"] for a in song.get("producer_artists", []) if a.get("name")],
            "credits": [],
        }

        for group in song.get("custom_performances", []):
            role = group.get("label", "")
            for artist in group.get("artists", []):
                name = artist.get("name", "")
                if name:
                    data["credits"].append({"name": name, "role": role})

        cache.set(cache_key, data)
        return data

    # ------------------------------------------------------------------

    @staticmethod
    def _best_hit(hits: list[dict], artist_name: str) -> dict | None:
        """Return the hit whose primary artist best matches artist_name."""
        artist_lower = artist_name.lower()
        for hit in hits:
            result = hit.get("result", {})
            primary = result.get("primary_artist", {}).get("name", "")
            if artist_lower in primary.lower() or primary.lower() in artist_lower:
                return _slim_hit(result)
        # Fall back to first hit
        if hits:
            return _slim_hit(hits[0]["result"])
        return None


def _slim_hit(result: dict) -> dict:
    return {
        "id": result.get("id"),
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "artist": result.get("primary_artist", {}).get("name", ""),
        "thumbnail": result.get("song_art_image_thumbnail_url", ""),
    }
