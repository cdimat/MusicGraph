"""MusicBrainz API client wrapping musicbrainzngs.

Rate limit: 1 req/sec unauthenticated. All methods include the required sleep.
"""

import asyncio
import time
from typing import Any

import musicbrainzngs


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

        return artist

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def get_release_group_releases(self, rg_mbid: str) -> list[dict]:
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
        return releases

    def get_release_tracks(self, release_mbid: str) -> list[dict]:
        self._throttle()
        result = musicbrainzngs.get_release_by_id(
            release_mbid, includes=["recordings", "recording-rels", "isrcs", "artist-credits"]
        )
        tracks = []
        for medium in result.get("release", {}).get("medium-list", []):
            for track in medium.get("track-list", []):
                rec = track.get("recording", {})
                isrc = ""
                if rec.get("isrc-list"):
                    isrc = rec["isrc-list"][0].get("id", "")
                tracks.append(
                    {
                        "mbid": rec.get("id", track.get("id", "")),
                        "title": track.get("title", rec.get("title", "")),
                        "position": track.get("position", ""),
                        "duration": rec.get("length"),
                        "isrc": isrc,
                    }
                )
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
