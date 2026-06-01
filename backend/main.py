"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from graph.client import GraphClient
from ingestion.discogs import DiscogsClient
from ingestion.genius import GeniusClient
from ingestion.mb_local import MusicBrainzLocalClient
from ingestion.musicbrainz import MusicBrainzClient
from ingestion.pipeline import IngestionPipeline

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    log.info("Connecting to Neo4j at %s", settings.neo4j_uri)
    graph = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    await graph.setup_schema()

    mb = MusicBrainzClient(settings.musicbrainz_app)
    discogs = DiscogsClient(settings.discogs_token)
    pipeline = IngestionPipeline(graph, mb, discogs)

    genius: GeniusClient | None = None
    if settings.genius_token:
        genius = GeniusClient(settings.genius_token)
        log.info("Genius API client ready.")
    else:
        log.info("GENIUS_TOKEN not set — Genius integration disabled.")

    mb_local = MusicBrainzLocalClient(settings.postgres_uri) if settings.postgres_uri else None
    if mb_local:
        # Run blocking psycopg2 connect off the event loop so a slow
        # PostgreSQL startup never hangs the whole backend.
        connected = await asyncio.to_thread(mb_local.connect)
        if not connected:
            mb_local = None

    app.state.graph    = graph
    app.state.mb       = mb
    app.state.mb_local = mb_local
    app.state.discogs  = discogs
    app.state.pipeline = pipeline
    app.state.genius   = genius

    log.info("MusicGraph backend ready.")
    yield

    # --- Shutdown ---
    await graph.close()
    if mb_local:
        mb_local.close()
    log.info("Neo4j connection closed.")


app = FastAPI(
    title="MusicGraph API",
    description="Artist graph explorer backed by MusicBrainz + Discogs → Neo4j",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes — pass `request` explicitly so handlers can read app.state
from api.routes import router  # noqa: E402


# Re-wrap each route so `request` is always injected as a keyword argument.
# (FastAPI resolves `request: Request` automatically when it appears in the
# function signature — we just need to make sure it's declared there.)
@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(router)


# Middleware to inject `request` into route kwargs automatically
# (FastAPI does this natively when routes declare `request: Request`)
# All our route handlers already accept `request=None`; FastAPI will
# inject the actual Request object at call time.
