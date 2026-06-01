"""FastAPI route handlers."""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api")

# In-memory job store (good enough for a local dev tool)
_jobs: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------------
# Artist search
# ------------------------------------------------------------------

@router.get("/artists/search")
async def search_artists(
    request: Request,
    q: str = Query(..., min_length=2, description="Artist name query"),
    limit: int = Query(10, le=25),
):
    """Search MusicBrainz for artists matching `q`."""
    mb = request.app.state.mb
    try:
        results = await asyncio.to_thread(mb.search_artists, q, limit)
        return results
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------------
# Graph endpoints
# ------------------------------------------------------------------

@router.get("/graph/artist/{mbid}")
async def get_artist_graph(mbid: str, request: Request):
    """Return (or build) the graph centred on an artist MBID.

    If the artist is not yet in Neo4j, a depth-1 ingestion is triggered
    synchronously before returning — first call may take 10–30 s.
    """
    graph = request.app.state.graph
    pipeline = request.app.state.pipeline

    data = await graph.get_graph_for_artist(mbid)
    if not data["nodes"]:
        try:
            await pipeline.ingest_artist(mbid, depth=1)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Ingestion failed: {exc}")
        data = await graph.get_graph_for_artist(mbid)

    return data


class ExpandRequest(BaseModel):
    node_id: str
    node_type: str  # Artist | Release | Track | Label


@router.post("/graph/expand")
async def expand_node(body: ExpandRequest, request: Request):
    """Expand a node's immediate neighbourhood.

    - Artist: triggers depth-1 ingestion if not yet in graph.
    - Release: lazily fetches tracks + Discogs credits if not yet stored.
    """
    graph = request.app.state.graph
    pipeline = request.app.state.pipeline

    if body.node_type == "Artist":
        # Ingest if not yet fully ingested (node exists but has no releases)
        has_releases = await graph.has_releases_for_artist(body.node_id)
        if not has_releases:
            try:
                await pipeline.ingest_artist(body.node_id, depth=1)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Ingestion failed: {exc}")
        data = await graph.get_neighborhood(body.node_id, body.node_type)

    elif body.node_type == "Release":
        # Lazily ingest tracks the first time a Release is expanded
        has_tracks = await graph.has_tracks_for_release(body.node_id)
        if not has_tracks:
            try:
                await pipeline.ingest_release_tracks(body.node_id)
            except Exception as exc:
                # Non-fatal — return whatever we have
                pass
        data = await graph.get_neighborhood(body.node_id, body.node_type)

    else:
        data = await graph.get_neighborhood(body.node_id, body.node_type)

    return data


# ------------------------------------------------------------------
# Background ingestion with job tracking
# ------------------------------------------------------------------

class IngestRequest(BaseModel):
    mbid: str
    depth: int = 1  # 0=artist only, 1=+releases+members, 2=+tracks+Discogs credits


@router.post("/ingest")
async def trigger_ingestion(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Queue a background ingestion job. Returns a job_id for status polling."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "log": [], "mbid": body.mbid}

    pipeline = request.app.state.pipeline

    def _progress(msg: str) -> None:
        _jobs[job_id]["log"].append(msg)

    async def _run() -> None:
        _jobs[job_id]["status"] = "running"
        try:
            await pipeline.ingest_artist(body.mbid, depth=body.depth, progress_cb=_progress)
            _jobs[job_id]["status"] = "complete"
        except Exception as exc:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(exc)

    background_tasks.add_task(_run)
    return {"job_id": job_id, "status": "pending"}


@router.get("/ingest/status/{job_id}")
async def ingestion_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
