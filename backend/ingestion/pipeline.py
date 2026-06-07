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
        mb_local=None,
    ) -> None:
        self.graph = graph
        self.mb = mb
        self.discogs = discogs
        # Optional local MusicBrainz dump (scripts/import_mb_dump.py). When
        # present and populated, it serves the high-volume release/track reads
        # locally instead of the rate-limited live API.
        self.mb_local = mb_local

    # ------------------------------------------------------------------
    # Local-first read helpers (fall back to the live MB API)
    # ------------------------------------------------------------------

    def _local_ready(self) -> bool:
        return bool(self.mb_local and self.mb_local.available)

    async def _get_release_group_releases(self, rg_mbid: str) -> list[dict]:
        if self._local_ready():
            local = await asyncio.to_thread(
                self.mb_local.get_release_group_releases, rg_mbid
            )
            if local:
                return local
        return await asyncio.to_thread(self.mb.get_release_group_releases, rg_mbid)

    async def _get_release_tracks(self, release_mbid: str) -> list[dict]:
        if self._local_ready():
            local = await asyncio.to_thread(
                self.mb_local.get_release_tracks, release_mbid
            )
            if local:
                return local
        return await asyncio.to_thread(self.mb.get_release_tracks, release_mbid)

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
                releases = await self._get_release_group_releases(rg["mbid"])
            except Exception as exc:
                log.warning("Could not fetch release group %s: %s", rg["mbid"], exc)
                continue

            for release in releases[:MAX_RELEASES_PER_GROUP]:
                release_data = {**release, "type": rg.get("type", "")}
                await self.graph.merge_release(release_data, mbid)
                emit(f"  [Neo4j] Merged release: {release['title']}")

                if depth < 2:
                    continue

                # Tracks from MusicBrainz (local dump first, then live API)
                try:
                    tracks = await self._get_release_tracks(release["mbid"])
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

    # ------------------------------------------------------------------
    # On-demand track ingestion (called when a Release node is expanded)
    # ------------------------------------------------------------------

    async def ingest_release_tracks(
        self,
        release_mbid: str,
        progress_cb: Callable[[str], None] | None = None,
    ) -> None:
        """Fetch and store tracks for a single release, plus Discogs credits.

        Called lazily when the user expands a Release node in the graph.
        Cached API responses make repeated calls near-instant.
        """
        def emit(msg: str) -> None:
            log.info(msg)
            if progress_cb:
                progress_cb(msg)

        emit(f"[MB] Fetching tracks for release {release_mbid}")
        try:
            tracks = await self._get_release_tracks(release_mbid)
        except Exception as exc:
            log.warning("Could not fetch tracks for %s: %s", release_mbid, exc)
            return

        for track in tracks[:MAX_TRACKS_PER_RELEASE]:
            await self.graph.merge_track(track, release_mbid)

            # Store MusicBrainz artist credits (main artist + featured artists)
            # This runs without a Discogs token and gives us the core Artist→Track links
            for ac in track.get("artist_credits", []):
                if not ac.get("mbid"):
                    continue
                await self.graph.merge_artist({
                    "mbid": ac["mbid"],
                    "name": ac["name"],
                    "sort_name": ac.get("sort_name", ac["name"]),
                    "type": "Person",
                    "country": "",
                    "disambiguation": "",
                    "begin_year": None,
                    "end_year": None,
                })
                await self.graph.merge_musician_credit(
                    ac["mbid"], track["mbid"],
                    role=ac.get("role", "Primary"),
                    instrument="",
                )

        emit(f"  Stored {len(tracks)} tracks for {release_mbid}")

        # Record labels straight from the local MB dump — gives us Label nodes
        # even without a Discogs token.
        if self._local_ready():
            labels = await asyncio.to_thread(self.mb_local.get_release_labels, release_mbid)
            for lbl in labels:
                if lbl.get("name"):
                    await self.graph.merge_label(
                        {"mbid": lbl["mbid"], "name": lbl["name"], "discogs_id": None},
                        release_mbid,
                    )
            if labels:
                emit(f"  [MB-local] Merged {len(labels)} label(s)")

        # Try to enrich with Discogs musician credits
        # Look up the release title + artist from Neo4j first
        release_data = await self.graph.get_release_info(release_mbid)
        if release_data and release_data.get("title"):
            artist_name = release_data.get("artist_name", "")
            year = release_data.get("year")
            emit(f"  [Discogs] Searching credits for '{release_data['title']}'")
            d_release = await asyncio.to_thread(
                self.discogs.find_release,
                release_data["title"],
                artist_name,
                year,
            )
            if d_release:
                for lbl in d_release.get("labels", []):
                    if lbl.get("name"):
                        await self.graph.merge_label(
                            {
                                "mbid": f"discogs:label:{lbl['discogs_id']}",
                                "name": lbl["name"],
                                "discogs_id": lbl.get("discogs_id"),
                            },
                            release_mbid,
                        )
                for credit in d_release.get("credits", []):
                    await self._ingest_credit(credit, release_mbid, tracks)
                emit(f"  [Discogs] Merged {len(d_release.get('credits', []))} credits")

    @staticmethod
    def _extract_instrument(role: str) -> str:
        """Pull instrument name from Discogs role string like 'Guitar [Lead]'."""
        if not role:
            return ""
        return role.split("[")[0].strip()
