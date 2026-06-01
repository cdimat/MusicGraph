"""MusicBrainz API client wrapping musicbrainzngs.

All responses are cached to disk (see ingestion/cache.py) so re-ingestion
after a Docker restart is near-instant — no API round-trips for data already
fetched.

Rate limit: 1 req/sec unauthenticated.
"""

import time
from typing import Any

import musicbrainzngs

from ingestion import cache


class MusicBrainzClient:
    def __init__(self, app: str) -> None:
        app_name, app_version = (app.split("/", 1) + ["1.0"])[:2]
        musicbrainzngs.set_useragent(app_name, app_version)
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------
    # Artist
    # ------------------------------------------------------------------

    def search_artists(self, query: str, limit: int = 10) -> list[dict]:
        """Search is NOT cached — we always want fresh search results."""
        self._throttle()
        result = musicbrainzngs.search_artists(artist=query, limit=limit)
        return [
            {
                "mbid": a["id"],
                "name": a["name"],
                "sort_name": a.get("sort-name", a["name"]),
                "type": a.get("type", ""),
                "country": a.get("country", ""),
                "disambiguation": a.get("disambiguation", ""),
                "score": int(a.get("ext:score", 0)),
            }
            for a in result.get("artist-list", [])
        ]

    def get_artist(self, mbid: str) -> dict:
        cache_key = f"mb:artist:{mbid}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        self._throttle()
        result = musicbrainzngs.get_artist_by_id(
            mbid,
            includes=["artist-rels", "release-groups", "url-rels", "aliases"],
        )
        a = result["artist"]
        artist: dict[str, Any] = {
            "mbid": a["id"],
            "name": a["name"],
            "sort_name": a.get("sort-name", a["name"]),
            "type": a.get("type", ""),
            "country": a.get("country", ""),
            "disambiguation": a.get("disambiguation", ""),
            "begin_year": self._parse_year(a.get("life-span", {}).get("begin")),
            "end_year": self._parse_year(a.get("life-span", {}).get("end")),
            "release_groups": [],
            "members": [],
            "member_of": [],
            "related_artists": [],
        }

        for rg in a.get("release-group-list", []):
            artist["release_groups"].append(
                {
                    "mbid": rg["id"],
                    "title": rg["title"],
                    "type": rg.get("type", ""),
                    "first_release_date": rg.get("first-release-date", ""),
                }
            )

        for rel in a.get("artist-relation-list", []):
            target = rel.get("artist", {})
            rel_type = rel.get("type", "")
            entry = {
                "mbid": target.get("id", ""),
                "name": target.get("name", ""),
                "type": rel_type,
                "direction": rel.get("direction", ""),
            }
            if rel_type in ("member of band", "member"):
                if rel.get("direction") == "backward":
                    artist["members"].append(entry)
                else:
                    artist["member_of"].append(entry)
            else:
                artist["related_artists"].append(entry)

        cache.set(cache_key, artist)
        return artist

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def get_release_group_releases(self, rg_mbid: str) -> list[dict]:
        cache_key = f"mb:rg:{rg_mbid}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        self._throttle()
        result = musicbrainzngs.get_release_group_by_id(
            rg_mbid, includes=["artists", "releases"]
        )
        releases = []
        for r in result.get("release-group", {}).get("release-list", []):
            releases.append(
                {
                    "mbid": r["id"],
                    "title": r["title"],
                    "year": self._parse_year(r.get("date")),
                    "country": r.get("country", ""),
                    "type": result["release-group"].get("type", ""),
                }
            )

        cache.set(cache_key, releases)
        return releases

    def get_release_tracks(self, release_mbid: str) -> list[dict]:
        cache_key = f"mb:tracks:{release_mbid}"
        cached = cache.get(cache_key)
        # Invalidate old cache entries that predate the artist_credits field
        if cached and cached and "artist_credits" in (cached[0] if cached else {}):
            return cached

        self._throttle()
        result = musicbrainzngs.get_release_by_id(
            release_mbid,
            includes=["recordings", "isrcs", "artist-credits"],
        )

        tracks = []
        medium_list = result.get("release", {}).get("medium-list", [])
        # Defensively handle both list and dict-wrapped forms from the API
        if isinstance(medium_list, dict):
            medium_list = medium_list.get("medium", [])

        for medium in medium_list:
            if not isinstance(medium, dict):
                continue
            track_list = medium.get("track-list", [])
            if isinstance(track_list, dict):
                track_list = track_list.get("track", [])

            for track in track_list:
                if not isinstance(track, dict):
                    continue
                rec = track.get("recording", {})
                # recording is sometimes just the ID string
                if isinstance(rec, str):
                    rec = {"id": rec}
                if not isinstance(rec, dict):
                    rec = {}

                # ISRCs come back as plain strings ["US-UM7-11-00043"],
                # not as dicts — guard against both forms
                isrc = ""
                isrc_list = rec.get("isrc-list", [])
                if isrc_list:
                    first = isrc_list[0]
                    isrc = first if isinstance(first, str) else first.get("id", "")

                # Extract artist credits (main + featured) from the recording.
                # artist-credit entries are dicts like:
                #   {"artist": {"id": "...", "name": "..."}, "joinphrase": " feat. "}
                # Plain strings (join phrases) are filtered out.
                artist_credits = []
                for ac in rec.get("artist-credit", []):
                    if not isinstance(ac, dict):
                        continue
                    a = ac.get("artist", {})
                    if not isinstance(a, dict) or not a.get("id"):
                        continue
                    artist_credits.append({
                        "mbid": a["id"],
                        "name": a.get("name", ""),
                        "sort_name": a.get("sort-name", a.get("name", "")),
                        # joinphrase on the *previous* credit indicates this one is featured
                        "role": "Featured" if artist_credits else "Primary",
                    })

                tracks.append(
                    {
                        "mbid": rec.get("id", track.get("id", "")),
                        "title": track.get("title", rec.get("title", "")),
                        "position": track.get("position", ""),
                        "duration": rec.get("length"),
                        "isrc": isrc,
                        "artist_credits": artist_credits,
                    }
                )

        cache.set(cache_key, tracks)
        return tracks

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_year(date_str: str | None) -> int | None:
        if not date_str:
            return None
        try:
            return int(str(date_str)[:4])
        except (ValueError, TypeError):
            return None
