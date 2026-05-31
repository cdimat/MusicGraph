"""Discogs API client.

Provides musician-level credits (instruments, featuring artists) not available
from MusicBrainz. Rate limit: 60 req/min unauthenticated, 240/min with token.
"""

import time
from difflib import SequenceMatcher
from typing import Any

import discogs_client as dc


class DiscogsClient:
    def __init__(self, token: str) -> None:
        self._client = dc.Client("MusicGraph/1.0", user_token=token or None)
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        min_interval = 1.0  # 60 req/min
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------
    # Artist search / lookup
    # ------------------------------------------------------------------

    def search_artist(self, name: str) -> dict | None:
        self._throttle()
        try:
            results = self._client.search(name, type="artist")
            for item in results.page(1):
                if self._name_match(item.name, name) > 0.85:
                    return {"discogs_id": item.id, "name": item.name}
        except Exception:
            pass
        return None

    def get_artist_releases(self, discogs_id: int, max_releases: int = 20) -> list[dict]:
        self._throttle()
        try:
            artist = self._client.artist(discogs_id)
            releases = []
            for r in artist.releases.page(1)[:max_releases]:
                self._throttle()
                releases.append(
                    {
                        "discogs_id": r.id,
                        "title": getattr(r, "title", ""),
                        "year": getattr(r, "year", None),
                        "type": getattr(r, "type", ""),
                    }
                )
            return releases
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Release credits — the primary value of Discogs
    # ------------------------------------------------------------------

    def get_release_credits(self, discogs_id: int) -> dict:
        """Return all musician credits for a release.

        Returns:
            {
              "title": str,
              "year": int,
              "labels": [{"name": str, "discogs_id": int}],
              "credits": [{"name": str, "discogs_id": int, "role": str, "tracks": str}],
            }
        """
        self._throttle()
        try:
            release = self._client.release(discogs_id)
            credits_: list[dict] = []
            for artist in getattr(release, "extraartists", []) or []:
                credits_.append(
                    {
                        "name": getattr(artist, "name", ""),
                        "discogs_id": getattr(artist, "id", None),
                        "role": getattr(artist, "role", ""),
                        "tracks": getattr(artist, "tracks", ""),
                    }
                )

            labels = []
            for lbl in getattr(release, "labels", []) or []:
                labels.append(
                    {"name": getattr(lbl, "name", ""), "discogs_id": getattr(lbl, "id", None)}
                )

            tracklist = []
            for track in getattr(release, "tracklist", []) or []:
                track_credits = []
                for artist in getattr(track, "extraartists", []) or []:
                    track_credits.append(
                        {
                            "name": getattr(artist, "name", ""),
                            "discogs_id": getattr(artist, "id", None),
                            "role": getattr(artist, "role", ""),
                        }
                    )
                tracklist.append(
                    {
                        "position": getattr(track, "position", ""),
                        "title": getattr(track, "title", ""),
                        "credits": track_credits,
                    }
                )

            return {
                "discogs_id": discogs_id,
                "title": getattr(release, "title", ""),
                "year": getattr(release, "year", None),
                "labels": labels,
                "credits": credits_,
                "tracklist": tracklist,
            }
        except Exception:
            return {}

    def find_release(self, title: str, artist_name: str, year: int | None) -> dict | None:
        """Search Discogs for a release by title + artist, return credits if found."""
        self._throttle()
        try:
            query = f"{title} {artist_name}"
            results = self._client.search(query, type="release")
            for item in results.page(1):
                if self._name_match(getattr(item, "title", ""), title) > 0.8:
                    return self.get_release_credits(item.id)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _name_match(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
