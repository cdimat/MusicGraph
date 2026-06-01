"""Neo4j async client — all graph read/write operations live here."""

import math
import random
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from graph.schema import (
    COLLABORATED_WITH,
    CONSTRAINTS,
    CONTAINS,
    CREDITED_ON,
    EDGE_COLORS,
    INDEXES,
    MEMBER_OF,
    NODE_COLORS,
    NODE_SIZES,
    PLAYED_ON,
    RELEASED_BY,
)


class GraphClient:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        await self._driver.close()

    async def setup_schema(self) -> None:
        async with self._driver.session() as session:
            for stmt in CONSTRAINTS + INDEXES:
                await session.run(stmt)

    # ------------------------------------------------------------------
    # Merge helpers
    # ------------------------------------------------------------------

    async def merge_artist(self, data: dict) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (a:Artist {mbid: $mbid})
                SET a.name        = $name,
                    a.sort_name   = $sort_name,
                    a.type        = $type,
                    a.country     = $country,
                    a.begin_year  = $begin_year,
                    a.end_year    = $end_year,
                    a.disambiguation = $disambiguation
                """,
                mbid=data.get("mbid", ""),
                name=data.get("name", ""),
                sort_name=data.get("sort_name", ""),
                type=data.get("type", ""),
                country=data.get("country", ""),
                begin_year=data.get("begin_year"),
                end_year=data.get("end_year"),
                disambiguation=data.get("disambiguation", ""),
            )

    async def merge_artist_discogs(self, mbid: str, discogs_id: int) -> None:
        async with self._driver.session() as session:
            await session.run(
                "MATCH (a:Artist {mbid: $mbid}) SET a.discogs_id = $discogs_id",
                mbid=mbid,
                discogs_id=discogs_id,
            )

    async def merge_release(self, data: dict, artist_mbid: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (r:Release {mbid: $mbid})
                SET r.title      = $title,
                    r.year       = $year,
                    r.type       = $type,
                    r.country    = $country,
                    r.discogs_id = $discogs_id
                WITH r
                MATCH (a:Artist {mbid: $artist_mbid})
                MERGE (a)-[:CREDITED_ON]->(r)
                """,
                mbid=data.get("mbid", ""),
                title=data.get("title", ""),
                year=data.get("year"),
                type=data.get("type", ""),
                country=data.get("country", ""),
                discogs_id=data.get("discogs_id"),
                artist_mbid=artist_mbid,
            )

    async def merge_track(self, data: dict, release_mbid: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (t:Track {mbid: $mbid})
                SET t.title    = $title,
                    t.position = $position,
                    t.duration = $duration,
                    t.isrc     = $isrc
                WITH t
                MATCH (r:Release {mbid: $release_mbid})
                MERGE (r)-[:CONTAINS]->(t)
                """,
                mbid=data.get("mbid", ""),
                title=data.get("title", ""),
                position=data.get("position", ""),
                duration=data.get("duration"),
                isrc=data.get("isrc", ""),
                release_mbid=release_mbid,
            )

    async def merge_label(self, data: dict, release_mbid: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (l:Label {mbid: $mbid})
                SET l.name       = $name,
                    l.discogs_id = $discogs_id
                WITH l
                MATCH (r:Release {mbid: $release_mbid})
                MERGE (r)-[:RELEASED_BY]->(l)
                """,
                mbid=data.get("mbid", ""),
                name=data.get("name", ""),
                discogs_id=data.get("discogs_id"),
                release_mbid=release_mbid,
            )

    async def merge_membership(self, member_mbid: str, group_mbid: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (member:Artist {mbid: $member_mbid})
                MATCH (group:Artist {mbid: $group_mbid})
                MERGE (member)-[:MEMBER_OF]->(group)
                """,
                member_mbid=member_mbid,
                group_mbid=group_mbid,
            )

    async def merge_musician_credit(
        self, artist_mbid: str, track_mbid: str, role: str, instrument: str
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (a:Artist {mbid: $artist_mbid})
                MATCH (t:Track {mbid: $track_mbid})
                MERGE (a)-[r:PLAYED_ON]->(t)
                SET r.role = $role, r.instrument = $instrument
                """,
                artist_mbid=artist_mbid,
                track_mbid=track_mbid,
                role=role,
                instrument=instrument,
            )

    async def has_releases_for_artist(self, artist_mbid: str) -> bool:
        """True if the artist has at least one release already ingested."""
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (:Artist {mbid: $mbid})-[:CREDITED_ON]->(:Release) RETURN count(*) AS n",
                mbid=artist_mbid,
            )
            record = await result.single()
            return bool(record and record["n"] > 0)

    async def has_tracks_for_release(self, release_mbid: str) -> bool:
        """True only if the release has tracks AND at least one track has artist credits."""
        async with self._driver.session() as session:
            # Check tracks exist
            r1 = await session.run(
                "MATCH (:Release {mbid: $mbid})-[:CONTAINS]->(:Track) RETURN count(*) AS n",
                mbid=release_mbid,
            )
            rec1 = await r1.single()
            if not rec1 or rec1["n"] == 0:
                return False

            # Check at least one PLAYED_ON credit exists for those tracks
            r2 = await session.run(
                """
                MATCH (:Release {mbid: $mbid})-[:CONTAINS]->(t:Track)
                WHERE ()-[:PLAYED_ON]->(t)
                RETURN count(t) AS n
                """,
                mbid=release_mbid,
            )
            rec2 = await r2.single()
            return bool(rec2 and rec2["n"] > 0)

    async def get_release_info(self, release_mbid: str) -> dict | None:
        """Return release title/year plus the primary credited artist name."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (r:Release {mbid: $mbid})
                OPTIONAL MATCH (a:Artist)-[:CREDITED_ON]->(r)
                RETURN r.title AS title, r.year AS year, a.name AS artist_name
                LIMIT 1
                """,
                mbid=release_mbid,
            )
            record = await result.single()
            if not record:
                return None
            return {
                "title": record["title"],
                "year": record["year"],
                "artist_name": record["artist_name"] or "",
            }

    async def merge_collaboration(self, mbid_a: str, mbid_b: str, context: str = "") -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (a:Artist {mbid: $mbid_a})
                MATCH (b:Artist {mbid: $mbid_b})
                MERGE (a)-[r:COLLABORATED_WITH]->(b)
                SET r.context = $context
                """,
                mbid_a=mbid_a,
                mbid_b=mbid_b,
                context=context,
            )

    # ------------------------------------------------------------------
    # Graph query — returns Sigma-compatible node/edge payload
    # ------------------------------------------------------------------

    async def get_graph_for_artist(self, mbid: str) -> dict:
        """Return the 1-hop neighbourhood of an artist as a Sigma-ready payload."""
        async with self._driver.session() as session:
            # Check artist exists
            check = await session.run(
                "MATCH (a:Artist {mbid: $mbid}) RETURN a", mbid=mbid
            )
            center_record = await check.single()
            if not center_record:
                return {"nodes": [], "edges": []}

            center_node = center_record["a"]

            # Fetch all direct neighbours as individual rows (avoids collect() map issues)
            nbr_result = await session.run(
                """
                MATCH (center:Artist {mbid: $mbid})-[r]-(neighbor)
                RETURN r, neighbor, type(r) AS rel_type,
                       startNode(r).mbid AS src_mbid,
                       endNode(r).mbid   AS tgt_mbid
                """,
                mbid=mbid,
            )
            rows = [record async for record in nbr_result]

        nodes: dict[str, dict] = {}
        edges: dict[str, dict] = {}

        center_key = dict(center_node).get("mbid") or str(center_node.element_id)
        center_sigma = self._node_to_sigma(center_node, 0.0, 0.0)
        nodes[center_key] = center_sigma

        count = max(len(rows), 1)
        for i, row in enumerate(rows):
            neighbor = row["neighbor"]
            if neighbor is None:
                continue

            angle = (2 * math.pi * i) / count
            n = self._node_to_sigma(neighbor, angle, radius=3.0)
            nodes.setdefault(n["key"], n)

            rel_type = row["rel_type"]
            # Use explicit startNode/endNode MBIDs to avoid rel.nodes[] issues
            src_mbid = row["src_mbid"] or center_key
            tgt_mbid = row["tgt_mbid"] or n["key"]
            # Normalise so both endpoints are in our node set
            src_id = src_mbid if src_mbid in nodes else center_key
            tgt_id = tgt_mbid if tgt_mbid in nodes else n["key"]

            edge_key = f"{src_id}__{rel_type}__{tgt_id}"
            if edge_key not in edges:
                edges[edge_key] = self._build_edge(
                    edge_key, src_id, tgt_id, rel_type, row["r"]
                )

        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    async def get_neighborhood(self, node_id: str, node_label: str) -> dict:
        """Expand one node — return its direct neighbours."""
        async with self._driver.session() as session:
            check = await session.run(
                f"MATCH (n:{node_label} {{mbid: $node_id}}) RETURN n",
                node_id=node_id,
            )
            center_record = await check.single()
            if not center_record:
                return {"nodes": [], "edges": []}

            center_node = center_record["n"]

            nbr_result = await session.run(
                f"""
                MATCH (n:{node_label} {{mbid: $node_id}})-[r]-(neighbor)
                RETURN r, neighbor, type(r) AS rel_type,
                       startNode(r).mbid AS src_mbid,
                       endNode(r).mbid   AS tgt_mbid
                """,
                node_id=node_id,
            )
            rows = [record async for record in nbr_result]

        nodes: dict[str, dict] = {}
        edges: dict[str, dict] = {}

        center_key = dict(center_node).get("mbid") or str(center_node.element_id)
        nodes[center_key] = self._node_to_sigma(center_node, 0.0, 0.0)

        count = max(len(rows), 1)
        for i, row in enumerate(rows):
            neighbor = row["neighbor"]
            if neighbor is None:
                continue
            angle = (2 * math.pi * i) / count
            n = self._node_to_sigma(neighbor, angle, radius=3.0)
            nodes.setdefault(n["key"], n)

            rel_type = row["rel_type"]
            src_mbid = row["src_mbid"] or center_key
            tgt_mbid = row["tgt_mbid"] or n["key"]
            src_id = src_mbid if src_mbid in nodes else center_key
            tgt_id = tgt_mbid if tgt_mbid in nodes else n["key"]

            edge_key = f"{src_id}__{rel_type}__{tgt_id}"
            if edge_key not in edges:
                edges[edge_key] = self._build_edge(
                    edge_key, src_id, tgt_id, rel_type, row["r"]
                )

        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_edge(
        self,
        key: str,
        src: str,
        tgt: str,
        rel_type: str,
        rel: Any,
    ) -> dict:
        attrs: dict[str, Any] = {
            "relType": rel_type,
            "label": rel_type.replace("_", " ").title(),
            "color": EDGE_COLORS.get(rel_type, "#64748b"),
            "size": 1,
        }
        rel_props = dict(rel) if rel is not None else {}
        for prop in ("role", "instrument", "context"):
            if rel_props.get(prop):
                attrs[prop] = rel_props[prop]
        return {"key": key, "source": src, "target": tgt, "attributes": attrs}

    def _node_to_sigma(self, node: Any, angle: float = 0.0, radius: float = 1.0) -> dict:
        labels = list(node.labels)
        label = labels[0] if labels else "Unknown"
        props = dict(node)
        return {
            "key": props.get("mbid") or str(node.element_id),
            "attributes": {
                "label": props.get("name") or props.get("title") or "?",
                "nodeType": label,
                "color": NODE_COLORS.get(label, "#94a3b8"),
                "size": NODE_SIZES.get(label, 6),
                "x": radius * math.cos(angle),
                "y": radius * math.sin(angle),
                **{k: v for k, v in props.items() if k not in ("name", "title")},
            },
        }

