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

    async def merge_collaboration(self, mbid_a: str, mbid_b: str, context: str = "") -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (a:Artist {mbid: $mbid_a})
                MATCH (b:Artist {mbid: $mbid_b})
                MERGE (a)-[r:COLLABORATED_WITH]-(b)
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
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (center:Artist {mbid: $mbid})
                OPTIONAL MATCH (center)-[r1]-(neighbor)
                OPTIONAL MATCH (neighbor)-[r2]-(second)
                  WHERE second <> center AND (second:Artist OR second:Label)
                WITH center,
                     collect(DISTINCT {rel: r1, node: neighbor}) AS tier1,
                     collect(DISTINCT {rel: r2, node: second}) AS tier2
                RETURN center, tier1, tier2
                """,
                mbid=mbid,
            )
            record = await result.single()
            if not record:
                return {"nodes": [], "edges": []}
            return self._build_graph_payload(record["center"], record["tier1"], record["tier2"])

    async def get_neighborhood(self, node_id: str, node_label: str) -> dict:
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH (n:{node_label} {{mbid: $node_id}})-[r]-(neighbor)
                RETURN n, collect(DISTINCT {{rel: r, node: neighbor}}) AS neighbors
                """,
                node_id=node_id,
            )
            record = await result.single()
            if not record:
                return {"nodes": [], "edges": []}
            return self._build_graph_payload(record["n"], record["neighbors"], [])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _build_graph_payload(
        self, center_node: Any, tier1: list, tier2: list
    ) -> dict:
        nodes: dict[str, dict] = {}
        edges: dict[str, dict] = {}

        center_sigma = self._node_to_sigma(center_node, 0, 0)
        nodes[center_sigma["key"]] = center_sigma

        t1_count = len(tier1)
        for i, entry in enumerate(tier1):
            if entry["node"] is None:
                continue
            angle = (2 * math.pi * i) / max(t1_count, 1)
            n = self._node_to_sigma(entry["node"], angle, radius=3)
            nodes.setdefault(n["key"], n)

            rel = entry["rel"]
            if rel is not None:
                src_id = nodes[center_sigma["key"]]["key"]
                tgt_id = n["key"]
                rel_type = rel.type
                edge_key = f"{src_id}__{rel_type}__{tgt_id}"
                if edge_key not in edges:
                    edges[edge_key] = {
                        "key": edge_key,
                        "source": src_id,
                        "target": tgt_id,
                        "attributes": {
                            "relType": rel_type,
                            "label": rel_type.replace("_", " ").title(),
                            "color": EDGE_COLORS.get(rel_type, "#64748b"),
                            "size": 1,
                            **{k: v for k, v in dict(rel).items()},
                        },
                    }

        t2_count = len(tier2)
        for i, entry in enumerate(tier2):
            if entry["node"] is None:
                continue
            angle = (2 * math.pi * i) / max(t2_count, 1)
            n = self._node_to_sigma(entry["node"], angle, radius=6)
            nodes.setdefault(n["key"], n)

            rel = entry["rel"]
            if rel is not None:
                start_id = dict(rel.nodes[0]).get("mbid") or str(rel.nodes[0].element_id)
                end_id = dict(rel.nodes[1]).get("mbid") or str(rel.nodes[1].element_id)
                rel_type = rel.type
                edge_key = f"{start_id}__{rel_type}__{end_id}"
                if edge_key not in edges and start_id in nodes and end_id in nodes:
                    edges[edge_key] = {
                        "key": edge_key,
                        "source": start_id,
                        "target": end_id,
                        "attributes": {
                            "relType": rel_type,
                            "label": rel_type.replace("_", " ").title(),
                            "color": EDGE_COLORS.get(rel_type, "#64748b"),
                            "size": 1,
                        },
                    }

        return {"nodes": list(nodes.values()), "edges": list(edges.values())}
