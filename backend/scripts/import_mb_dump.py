#!/usr/bin/env python3
"""Import the MusicBrainz full-database export into a local PostgreSQL DB.

Source (public, anonymous, CC0):
    https://data.metabrainz.org/pub/musicbrainz/data/fullexport/

This streams `mbdump.tar.bz2` (the core data archive) and imports the slice
of tables this app needs to build artist → album → song → credit graphs
WITHOUT hitting the live MusicBrainz API:

    artist, label, artist_credit_name, release_group, release,
    recording, medium, track, release_label

Strategy
--------
The dump files are headerless, tab-separated PostgreSQL COPY text. For each
table we:
  1. COPY the raw file into an all-TEXT staging table (fast, bulk).
  2. Project the handful of columns we care about into a slim, indexed
     table (mb_artist, mb_release, mb_track, …).
  3. DROP the staging table immediately, so peak disk stays near one table.

Usage
-----
    python scripts/import_mb_dump.py [--dsn DSN] [--file PATH] [--only T,T]

    --dsn   PostgreSQL DSN
            (default: $POSTGRES_URI or
             postgresql://postgres:musicgraph@localhost:5432/musicbrainz)
    --file  Path to an already-downloaded mbdump.tar.bz2 (skip download).
    --only  Comma-separated table list to import (default: all).

Footprint: download ≈3–4 GB compressed; import ≈30–60 min; peak disk for the
staging of the largest table (track/recording) is sizeable — budget ~40 GB
free for a comfortable full import.
"""

import argparse
import os
import sys
import tarfile
import urllib.request
from typing import IO

import psycopg2

MB_BASE = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport"
LATEST_URL = f"{MB_BASE}/LATEST"


# ---------------------------------------------------------------------------
# Per-table import spec.
#
#   staging  : the FULL ordered column list of the MB dump file (so COPY lines
#              up positionally). All imported as TEXT.
#   slim     : DDL for the trimmed table the app actually queries.
#   project  : INSERT … SELECT that casts the columns we keep.
#   indexes  : built after projection.
#
# Column orders verified against MusicBrainz CreateTables.sql.
# ---------------------------------------------------------------------------

ARTIST_COLS = [
    "id", "gid", "name", "sort_name", "begin_date_year", "begin_date_month",
    "begin_date_day", "end_date_year", "end_date_month", "end_date_day",
    "type", "area", "gender", "comment", "edits_pending", "last_updated",
    "ended", "begin_area", "end_area",
]
ARTIST_CREDIT_NAME_COLS = ["artist_credit", "position", "artist", "name", "join_phrase"]
RELEASE_GROUP_COLS = [
    "id", "gid", "name", "artist_credit", "type", "comment",
    "edits_pending", "last_updated",
]
RELEASE_COLS = [
    "id", "gid", "name", "artist_credit", "release_group", "status",
    "packaging", "language", "script", "barcode", "comment",
    "edits_pending", "quality", "last_updated",
]
RECORDING_COLS = [
    "id", "gid", "name", "artist_credit", "length", "comment",
    "edits_pending", "last_updated", "video",
]
MEDIUM_COLS = [
    "id", "release", "position", "format", "name", "edits_pending",
    "last_updated", "track_count", "gid",
]
TRACK_COLS = [
    "id", "gid", "recording", "medium", "position", "number", "name",
    "artist_credit", "length", "edits_pending", "last_updated", "is_data_track",
]
LABEL_COLS = [
    "id", "gid", "name", "begin_date_year", "begin_date_month", "begin_date_day",
    "end_date_year", "end_date_month", "end_date_day", "label_code", "type",
    "area", "comment", "edits_pending", "last_updated", "ended",
]
RELEASE_LABEL_COLS = ["id", "release", "label", "catalog_number", "last_updated"]


TABLES: dict[str, dict] = {
    "mbdump/artist": {
        "staging": ARTIST_COLS,
        "slim": """
            CREATE TABLE mb_artist (
                id       INTEGER PRIMARY KEY,
                gid      UUID NOT NULL,
                name     TEXT NOT NULL,
                sort_name TEXT,
                type_id  INTEGER,
                comment  TEXT
            )""",
        "project": """
            INSERT INTO mb_artist (id, gid, name, sort_name, type_id, comment)
            SELECT id::int, gid::uuid, name, sort_name, type::int, comment
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_artist_gid ON mb_artist (gid)",
            "CREATE INDEX mb_artist_name_trgm ON mb_artist USING gin (name gin_trgm_ops)",
        ],
    },
    "mbdump/label": {
        "staging": LABEL_COLS,
        "slim": """
            CREATE TABLE mb_label (
                id      INTEGER PRIMARY KEY,
                gid     UUID NOT NULL,
                name    TEXT NOT NULL,
                type_id INTEGER,
                comment TEXT
            )""",
        "project": """
            INSERT INTO mb_label (id, gid, name, type_id, comment)
            SELECT id::int, gid::uuid, name, type::int, comment
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_label_gid ON mb_label (gid)",
            "CREATE INDEX mb_label_name_trgm ON mb_label USING gin (name gin_trgm_ops)",
        ],
    },
    "mbdump/artist_credit_name": {
        "staging": ARTIST_CREDIT_NAME_COLS,
        "slim": """
            CREATE TABLE mb_acn (
                artist_credit INTEGER NOT NULL,
                position      INTEGER NOT NULL,
                artist        INTEGER NOT NULL,
                join_phrase   TEXT
            )""",
        "project": """
            INSERT INTO mb_acn (artist_credit, position, artist, join_phrase)
            SELECT artist_credit::int, position::int, artist::int, join_phrase
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_acn_credit ON mb_acn (artist_credit)",
            "CREATE INDEX mb_acn_artist ON mb_acn (artist)",
        ],
    },
    "mbdump/release_group": {
        "staging": RELEASE_GROUP_COLS,
        "slim": """
            CREATE TABLE mb_release_group (
                id            INTEGER PRIMARY KEY,
                gid           UUID NOT NULL,
                name          TEXT NOT NULL,
                artist_credit INTEGER,
                type_id       INTEGER,
                comment       TEXT
            )""",
        "project": """
            INSERT INTO mb_release_group (id, gid, name, artist_credit, type_id, comment)
            SELECT id::int, gid::uuid, name, artist_credit::int, type::int, comment
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_rg_gid ON mb_release_group (gid)",
            "CREATE INDEX mb_rg_credit ON mb_release_group (artist_credit)",
        ],
    },
    "mbdump/release": {
        "staging": RELEASE_COLS,
        "slim": """
            CREATE TABLE mb_release (
                id            INTEGER PRIMARY KEY,
                gid           UUID NOT NULL,
                name          TEXT NOT NULL,
                artist_credit INTEGER,
                release_group INTEGER,
                barcode       TEXT,
                comment       TEXT
            )""",
        "project": """
            INSERT INTO mb_release (id, gid, name, artist_credit, release_group, barcode, comment)
            SELECT id::int, gid::uuid, name, artist_credit::int, release_group::int, barcode, comment
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_release_gid ON mb_release (gid)",
            "CREATE INDEX mb_release_rg ON mb_release (release_group)",
            "CREATE INDEX mb_release_credit ON mb_release (artist_credit)",
        ],
    },
    "mbdump/recording": {
        "staging": RECORDING_COLS,
        "slim": """
            CREATE TABLE mb_recording (
                id            INTEGER PRIMARY KEY,
                gid           UUID NOT NULL,
                name          TEXT NOT NULL,
                artist_credit INTEGER,
                length        INTEGER
            )""",
        "project": """
            INSERT INTO mb_recording (id, gid, name, artist_credit, length)
            SELECT id::int, gid::uuid, name, artist_credit::int, length::int
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_recording_gid ON mb_recording (gid)",
        ],
    },
    "mbdump/medium": {
        "staging": MEDIUM_COLS,
        "slim": """
            CREATE TABLE mb_medium (
                id       INTEGER PRIMARY KEY,
                release  INTEGER NOT NULL,
                position INTEGER
            )""",
        "project": """
            INSERT INTO mb_medium (id, release, position)
            SELECT id::int, release::int, position::int
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_medium_release ON mb_medium (release)",
        ],
    },
    "mbdump/track": {
        "staging": TRACK_COLS,
        "slim": """
            CREATE TABLE mb_track (
                id            INTEGER PRIMARY KEY,
                recording     INTEGER NOT NULL,
                medium        INTEGER NOT NULL,
                position      INTEGER,
                number        TEXT,
                name          TEXT,
                artist_credit INTEGER,
                length        INTEGER
            )""",
        "project": """
            INSERT INTO mb_track (id, recording, medium, position, number, name, artist_credit, length)
            SELECT id::int, recording::int, medium::int, position::int, number, name, artist_credit::int, length::int
            FROM stg_import""",
        "indexes": [
            "CREATE INDEX mb_track_medium ON mb_track (medium)",
            "CREATE INDEX mb_track_recording ON mb_track (recording)",
        ],
    },
    "mbdump/release_label": {
        "staging": RELEASE_LABEL_COLS,
        "slim": """
            CREATE TABLE mb_release_label (
                release INTEGER NOT NULL,
                label   INTEGER
            )""",
        "project": """
            INSERT INTO mb_release_label (release, label)
            SELECT release::int, label::int
            FROM stg_import
            WHERE label IS NOT NULL""",
        "indexes": [
            "CREATE INDEX mb_rl_release ON mb_release_label (release)",
            "CREATE INDEX mb_rl_label ON mb_release_label (label)",
        ],
    },
}


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _latest_dump_url() -> str:
    print("Resolving latest MusicBrainz export…")
    with urllib.request.urlopen(LATEST_URL, timeout=30) as r:
        date = r.read().decode().strip()
    url = f"{MB_BASE}/{date}/mbdump.tar.bz2"
    print(f"  Latest export: {date}")
    return url


def _open_source(path_or_url: str) -> IO[bytes]:
    if os.path.isfile(path_or_url):
        print(f"Reading local archive: {path_or_url}")
        return open(path_or_url, "rb")
    print(f"Streaming archive: {path_or_url}")
    return urllib.request.urlopen(path_or_url, timeout=60)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _import_member(conn, member: str, spec: dict, fileobj: IO[bytes]) -> None:
    short = member.split("/")[-1]
    print(f"  [{short}] COPY → staging…", flush=True)

    staging_ddl = ", ".join(f"{c} TEXT" for c in spec["staging"])
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS stg_import")
        cur.execute(f"CREATE UNLOGGED TABLE stg_import ({staging_ddl})")
        # MB dumps are standard PostgreSQL COPY text (tab-separated, \N = NULL).
        cur.copy_expert("COPY stg_import FROM STDIN", fileobj)

        print(f"  [{short}] projecting → slim table…", flush=True)
        slim_name = spec["slim"].split("(")[0].split()[-1]
        cur.execute(f"DROP TABLE IF EXISTS {slim_name} CASCADE")
        cur.execute(spec["slim"])
        cur.execute(spec["project"])

        for idx in spec["indexes"]:
            cur.execute(idx)

        cur.execute("DROP TABLE stg_import")
        cur.execute(f"SELECT count(*) FROM {slim_name}")
        n = cur.fetchone()[0]
    conn.commit()
    print(f"  [{short}] ✓ {n:,} rows in {slim_name}")


def run(dsn: str, source: str, only: set[str] | None) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    conn.commit()

    wanted = {
        name: spec
        for name, spec in TABLES.items()
        if only is None or name.split("/")[-1] in only
    }
    done: set[str] = set()

    print("Opening archive…")
    with _open_source(source) as raw:
        with tarfile.open(fileobj=raw, mode="r|bz2") as tf:
            for member in tf:
                if member.name in wanted and member.name not in done:
                    fobj = tf.extractfile(member)
                    if fobj:
                        _import_member(conn, member.name, wanted[member.name], fobj)
                        done.add(member.name)
                if len(done) == len(wanted):
                    break

    conn.close()
    missing = set(wanted) - done
    if missing:
        print(f"WARNING: not found in archive: {sorted(missing)}", file=sys.stderr)
    print("\nDone. Local MusicBrainz database is ready.")


def main() -> None:
    default_dsn = os.getenv(
        "POSTGRES_URI",
        "postgresql://postgres:musicgraph@localhost:5432/musicbrainz",
    )
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dsn", default=default_dsn, help="PostgreSQL DSN")
    p.add_argument("--file", default=None, help="Path to local mbdump.tar.bz2")
    p.add_argument("--only", default=None, help="Comma-separated table names")
    args = p.parse_args()

    only = {t.strip() for t in args.only.split(",")} if args.only else None
    source = args.file if args.file else _latest_dump_url()
    run(args.dsn, source, only)


if __name__ == "__main__":
    main()
