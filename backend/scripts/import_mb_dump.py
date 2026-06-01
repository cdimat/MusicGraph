#!/usr/bin/env python3
"""Import MusicBrainz full-database dump into a local PostgreSQL database.

Downloads only the `artist` and `label` tables from the latest MB export
by streaming the tarball and extracting only the files needed — the full
archive is NOT written to disk.

Usage:
    python scripts/import_mb_dump.py [--dsn DSN] [--file PATH]

Options:
    --dsn   PostgreSQL connection string
            (default: value of POSTGRES_URI env var, or
             postgresql://postgres:musicgraph@localhost:5432/musicbrainz)
    --file  Path to a locally downloaded mbdump.tar.bz2 to use instead of
            downloading. Useful when the network is slow or for re-imports.

The script is idempotent — re-running it re-imports and overwrites the tables.

Approximate download: ~3–4 GB compressed (the full mbdump.tar.bz2).
Import time: 10–20 minutes depending on hardware.
"""

import argparse
import io
import os
import sys
import tarfile
import urllib.request
from typing import IO

import psycopg2

MB_DUMP_BASE = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport"
LATEST_URL   = f"{MB_DUMP_BASE}/LATEST"

# MusicBrainz artist_type integer → readable name
ARTIST_TYPE = {
    "1": "Person",
    "2": "Group",
    "3": "Orchestra",
    "4": "Choir",
    "5": "Character",
    "6": "Other",
}

# MB label_type integers → readable name (abridged)
LABEL_TYPE = {
    "1": "Distributor",
    "2": "Holding",
    "3": "Production",
    "4": "Original Production",
    "5": "Bootleg Production",
    "6": "Reissue Production",
    "7": "Publisher",
}

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS mb_artist;
CREATE TABLE mb_artist (
    mbid          UUID        PRIMARY KEY,
    name          TEXT        NOT NULL,
    sort_name     TEXT        NOT NULL,
    artist_type   TEXT,
    disambiguation TEXT
);
CREATE INDEX mb_artist_name_trgm ON mb_artist USING gin (name gin_trgm_ops);
CREATE INDEX mb_artist_name_lower ON mb_artist (lower(name));

DROP TABLE IF EXISTS mb_label;
CREATE TABLE mb_label (
    mbid          UUID        PRIMARY KEY,
    name          TEXT        NOT NULL,
    label_type    TEXT,
    country       TEXT,
    disambiguation TEXT
);
CREATE INDEX mb_label_name_trgm ON mb_label USING gin (name gin_trgm_ops);
"""


# ------------------------------------------------------------------
# Column positions in the MB TSV dump (0-indexed)
# Source: https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/CreateTables.sql
# ------------------------------------------------------------------

# artist: id gid name sort_name begin_date_year … type area gender comment …
ARTIST_COL = {"gid": 1, "name": 2, "sort_name": 3, "type": 10, "comment": 13}

# label: id gid name label_code begin_date_year … type area comment …
LABEL_COL = {"gid": 1, "name": 2, "type": 10, "comment": 12}


def _latest_dump_url() -> str:
    print("Fetching latest dump date from MusicBrainz…")
    with urllib.request.urlopen(LATEST_URL, timeout=30) as r:
        date = r.read().decode().strip()
    url = f"{MB_DUMP_BASE}/{date}/mbdump.tar.bz2"
    print(f"Latest dump: {date}  →  {url}")
    return url


def _open_source(path_or_url: str) -> IO[bytes]:
    """Return a file-like object for the archive (local file or HTTP stream)."""
    if os.path.isfile(path_or_url):
        print(f"Using local file: {path_or_url}")
        return open(path_or_url, "rb")
    print(f"Streaming from: {path_or_url}")
    return urllib.request.urlopen(path_or_url, timeout=60)  # type: ignore[return-value]


def _null(v: str) -> str | None:
    return None if v == r"\N" else v


def _import_artists(cur: psycopg2.extensions.cursor, fileobj: IO[bytes]) -> int:
    """Parse the MB artist TSV and bulk-insert into mb_artist."""
    print("  Importing artists…", flush=True)
    buf: list[tuple] = []
    count = 0

    for raw in io.TextIOWrapper(fileobj, encoding="utf-8", errors="replace"):
        cols = raw.rstrip("\n").split("\t")
        if len(cols) < 14:
            continue
        gid  = _null(cols[ARTIST_COL["gid"]])
        name = _null(cols[ARTIST_COL["name"]])
        if not gid or not name:
            continue
        buf.append((
            gid,
            name,
            _null(cols[ARTIST_COL["sort_name"]]) or name,
            ARTIST_TYPE.get(cols[ARTIST_COL["type"]], None),
            _null(cols[ARTIST_COL["comment"]]),
        ))
        if len(buf) >= 5_000:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO mb_artist (mbid,name,sort_name,artist_type,disambiguation) VALUES %s ON CONFLICT DO NOTHING",
                buf,
            )
            count += len(buf)
            buf.clear()
            if count % 100_000 == 0:
                print(f"    {count:,} artists…", flush=True)

    if buf:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO mb_artist (mbid,name,sort_name,artist_type,disambiguation) VALUES %s ON CONFLICT DO NOTHING",
            buf,
        )
        count += len(buf)

    print(f"  ✓ {count:,} artists imported.")
    return count


def _import_labels(cur: psycopg2.extensions.cursor, fileobj: IO[bytes]) -> int:
    """Parse the MB label TSV and bulk-insert into mb_label."""
    print("  Importing labels…", flush=True)
    buf: list[tuple] = []
    count = 0

    for raw in io.TextIOWrapper(fileobj, encoding="utf-8", errors="replace"):
        cols = raw.rstrip("\n").split("\t")
        if len(cols) < 13:
            continue
        gid  = _null(cols[LABEL_COL["gid"]])
        name = _null(cols[LABEL_COL["name"]])
        if not gid or not name:
            continue
        buf.append((
            gid,
            name,
            LABEL_TYPE.get(cols[LABEL_COL["type"]], None),
            None,  # country requires area join — omitted
            _null(cols[LABEL_COL["comment"]]),
        ))
        if len(buf) >= 5_000:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO mb_label (mbid,name,label_type,country,disambiguation) VALUES %s ON CONFLICT DO NOTHING",
                buf,
            )
            count += len(buf)
            buf.clear()

    if buf:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO mb_label (mbid,name,label_type,country,disambiguation) VALUES %s ON CONFLICT DO NOTHING",
            buf,
        )
        count += len(buf)

    print(f"  ✓ {count:,} labels imported.")
    return count


def run(dsn: str, source: str) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    print("Creating schema…")
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()

    targets = {"mbdump/artist": _import_artists, "mbdump/label": _import_labels}
    done: set[str] = set()

    print("Opening archive (this may take a moment for large files)…")
    with _open_source(source) as raw:
        with tarfile.open(fileobj=raw, mode="r|bz2") as tf:
            for member in tf:
                if member.name in targets and member.name not in done:
                    fobj = tf.extractfile(member)
                    if fobj:
                        with conn.cursor() as cur:
                            targets[member.name](cur, fobj)
                        conn.commit()
                        done.add(member.name)
                if len(done) == len(targets):
                    break

    conn.close()

    missing = set(targets) - done
    if missing:
        print(f"WARNING: these tables were not found in the archive: {missing}", file=sys.stderr)
    else:
        print("\nImport complete. Local MusicBrainz database is ready.")


def main() -> None:
    default_dsn = os.getenv(
        "POSTGRES_URI",
        "postgresql://postgres:musicgraph@localhost:5432/musicbrainz",
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn",  default=default_dsn, help="PostgreSQL DSN")
    parser.add_argument("--file", default=None, help="Path to local mbdump.tar.bz2")
    args = parser.parse_args()

    source = args.file if args.file else _latest_dump_url()
    run(args.dsn, source)


if __name__ == "__main__":
    main()
