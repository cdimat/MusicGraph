"""Ingestion pipeline — orchestrates MusicBrainz + Discogs into Neo4j.

Strategy:
  1. Look up artist in MusicBrainz to get canonical MBID + relationships.
  2. Cross-reference Discogs by name to attach discogs_id and retrieve
     rich musician credits (instruments, featuring artists).
  3. Merge everything into Neo4j using MBIDs as the primary key.

Depth 0  → artist node only
Depth 1  → artist + top release groups + band members + related artists
Depth 2  → depth-1 + tracks + per-track musician credits from Discogs
"""

import asyncio
import logging
from typing import Callable

from graph.client import GraphClient
from ingestion.discogs import DiscogsClient
from ingestion.musicbrainz import MusicBrainzClient

log = logging.getLogger(__name__)

# Maximum releases to ingest per artist (keeps first-run snappy)
MAX_RELEASE_GROUPS = 8
MAX_RELEASES_PER_GROUP = 2
MAX_TRACKS_PER_RELEASE = 20


class IngestionPipeline:
    def __init__(
        self,
        graph: GraphClient,
        mb: MusicBrainzClient,
        discogs: DiscogsClient,
    ) -> None:
        self.graph = graph
        self.mb = mb
        self.discogs = discogs

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def ingest_artist(
        self,
        mbid: str,
        depth: int = 1,
        progress_cb: Callable[[str], None] | None = None,
    ) -> None:
        """Ingest an artist by MBID up to `depth` hops."""

        def emit(msg: str) -> None:
            log.info(msg)
            if progress_cb:
                progress_cb(msg)

        emit(f"[MB] Fetching artist {mbid}")
        artist = await asyncio.to_thread(self.mb.get_artist, mbid)
        await self.graph.merge_artist(artist)

        # Cross-link with Discogs
        emit(f"[Discogs] Searching for '{artist['name']}'")
        d_artist = await asyncio.to_thread(self.discogs.search_artist, artist["name"])
        if d_artist:
            await self.graph.merge_artist_discogs(mbid, d_artist["discogs_id"])
            emit(f"[Discogs] Linked discogs_id={d_artist['discogs_id']}")

        if depth < 1:
            return

        # Band members / member-of
        for member in artist.get("members", []):
            if not member["mbid"]:
                continue
            emit(f"[MB] Merging member: {member['name']}")
            await self.graph.merge_artist(
                {
                    "mbid": member["mbid"],
                    "name": member["name"],
                    "sort_name": member["name"],
                    "type": "Person",
                    "country": "",
                    "disambiguation": "",
                    "begin_year": None,
                    "end_year": None,
                }
            )
            await self.graph.merge_membership(member["mbid"], mbid)

        for group in artist.get("member_of", []):
            if not group["mbid"]:
                continue
            emit(f"[MB] Merging group: {group['name']}")
            await self.graph.merge_artist(
                {
                    "mbid": group["mbid"],
                    "name": group["name"],
                    "sort_name": group["name"],
                    "type": "Group",
                    "country": "",
                    "disambiguation": "",
                    "begin_year": None,
                    "end_year": None,
                }
            )
            await self.graph.merge_membership(mbid, group["mbid"])

        # Related artists (collaborations, influences, etc.)
        for rel in artist.get("related_artists", [])[:10]:
            if not rel["mbid"]:
                continue
            emit(f"[MB] Merging related artist: {rel['name']}")
            await self.graph.merge_artist(
                {
                    "mbid": rel["mbid"],
                    "name": rel["name"],
                    "sort_name": rel["name"],
                    "type": "",
                    "country": "",
                    "disambiguation": "",
                    "begin_year": None,
                    "end_year": None,
                }
            )
            await self.graph.merge_collaboration(mbid, rel["mbid"], context=rel["type"])

        # Releases
        rg_list = artist.get("release_groups", [])[:MAX_RELEASE_GROUPS]
        for rg in rg_list:
            emit(f"[MB] Fetching release group: {rg['title']}")
            try:
                releases = await asyncio.to_thread(
                    self.mb.get_release_group_releases, rg["mbid"]
                )
            except Exception as exc:
                log.warning("Could not fetch release group %s: %s", rg["mbid"], exc)
                continue

            for release in releases[:MAX_RELEASES_PER_GROUP]:
                release_data = {**release, "type": rg.get("type", "")}
                await self.graph.merge_release(release_data, mbid)
                emit(f"  [Neo4j] Merged release: {release['title']}")

                if depth < 2:
                    continue

                # Tracks from MusicBrainz
                try:
                    tracks = await asyncio.to_thread(
                        self.mb.get_release_tracks, release["mbid"]
                    )
                except Exception as exc:
                    log.warning("Could not fetch tracks for %s: %s", release["mbid"], exc)
                    tracks = []

                for track in tracks[:MAX_TRACKS_PER_RELEASE]:
                    await self.graph.merge_track(track, release["mbid"])

                # Musician credits from Discogs
                emit(f"  [Discogs] Searching credits for '{release['title']}'")
                d_release = await asyncio.to_thread(
                    self.discogs.find_release,
                    release["title"],
                    artist["name"],
                    release.get("year"),
                )
                if not d_release:
                    continue

                # Update release with discogs_id
                if d_release.get("discogs_id"):
                    release_data["discogs_id"] = d_release["discogs_id"]
                    await self.graph.merge_release(release_data, mbid)

                # Merge label nodes
                for lbl in d_release.get("labels", []):
                    if lbl.get("name"):
                        await self.graph.merge_label(
                            {
                                "mbid": f"discogs:label:{lbl['discogs_id']}",
                                "name": lbl["name"],
                                "discogs_id": lbl.get("discogs_id"),
                            },
                            release["mbid"],
                        )

                # Release-level credits
                for credit in d_release.get("credits", []):
                    await self._ingest_credit(credit, release["mbid"], tracks)

                # Per-track credits
                for d_track in d_release.get("tracklist", []):
                    for credit in d_track.get("credits", []):
                        # Best-effort match by position
                        matched_track = next(
                            (
                                t
                                for t in tracks
                                if str(t.get("position", "")) == str(d_track.get("position", ""))
                            ),
                            None,
                        )
                        if matched_track:
                            await self._ingest_credit(
                                credit, release["mbid"], [matched_track]
                            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ingest_credit(
        self, credit: dict, release_mbid: str, tracks: list[dict]
    ) -> None:
        if not credit.get("name"):
            return

        # Use a synthetic MBID for Discogs-only artists
        artist_mbid = f"discogs:artist:{credit['discogs_id']}" if credit.get("discogs_id") else None
        if not artist_mbid:
            return

        await self.graph.merge_artist(
            {
                "mbid": artist_mbid,
                "name": credit["name"],
                "sort_name": credit["name"],
                "type": "Person",
                "country": "",
                "disambiguation": "",
                "begin_year": None,
                "end_year": None,
            }
        )

        role = credit.get("role", "")
        instrument = self._extract_instrument(role)

        # Link to each track in scope
        for track in tracks:
            if track.get("mbid"):
                await self.graph.merge_musician_credit(
                    artist_mbid, track["mbid"], role, instrument
                )

    @staticmethod
    def _extract_instrument(role: str) -> str:
        """Pull instrument name from Discogs role string like 'Guitar [Lead]'."""
        if not role:
            return ""
        return role.split("[")[0].strip()
