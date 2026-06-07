# Bulk Data Sources

MusicGraph can run its core graph (artist → album → song → credits → label)
entirely from a **local database** built from public bulk downloads, instead
of the rate-limited live APIs. This document lists the sources, their current
access status (verified June 2026), and how to load them.

---

## 1. MusicBrainz Full Export — primary source ✅ used

The backbone of the local database. Fully open, anonymous, no auth.

- **URL:** https://data.metabrainz.org/pub/musicbrainz/data/fullexport/
  (mirror of `ftp.musicbrainz.org/pub/musicbrainz/data/fullexport/`)
- **License:** CC0 / CC-BY-NC-SA for parts; core data is freely redistributable
- **Cadence:** twice weekly
- **Archive used:** `mbdump.tar.bz2` (~3–4 GB compressed) — the core data tables
- **Latest at time of writing:** `20260606-002104`

### What we import

`scripts/import_mb_dump.py` streams the archive and loads the slice the app
uses into PostgreSQL as slim, trigram-indexed tables:

| MB table             | Local table         | Used for                          |
|----------------------|---------------------|-----------------------------------|
| `artist`             | `mb_artist`         | artist search (fuzzy)             |
| `label`              | `mb_label`          | label search + release labels     |
| `artist_credit_name` | `mb_acn`            | song/album → artist credits       |
| `release_group`      | `mb_release_group`  | an artist's albums                |
| `release`            | `mb_release`        | the releases within an album      |
| `recording`          | `mb_recording`      | song (Track node) identity        |
| `medium` / `track`   | `mb_medium`/`mb_track` | the songs on a release         |
| `release_label`      | `mb_release_label`  | which label released a release    |

This replaces the live MusicBrainz calls for **artist search**, **release
listings**, **track listings + credits**, and **record labels** — i.e. the
high-volume, rate-limited paths. (Artist↔artist *relationships* — band members
and collaborations — still come from the live API, a single light call per
artist; importing the `l_artist_artist` relationship tables is a future step.)

### How to load it

```bash
# 1. Postgres must be up (it's part of docker compose)
docker compose up -d postgres

# 2. Run the importer from the backend container (psycopg2 lives there)
docker compose exec backend python scripts/import_mb_dump.py

#    …or stream straight from the network on the host:
#    POSTGRES_URI=postgresql://postgres:musicgraph@localhost:5432/musicbrainz \
#      python backend/scripts/import_mb_dump.py

# Import a subset while testing:
docker compose exec backend python scripts/import_mb_dump.py --only artist,label

# Use an already-downloaded archive instead of streaming:
docker compose exec backend python scripts/import_mb_dump.py --file /data/mbdump.tar.bz2
```

- **Time:** ~30–60 min for a full import (depends on disk/CPU).
- **Disk:** budget ~40 GB free — each table is `COPY`-loaded into an all-text
  staging table, projected to a slim table, then the staging is dropped, so
  peak usage stays near the single largest table rather than the whole dump.

Once imported, the backend auto-detects the tables on startup
(`/api/system/status` reports `mb_local: true`) and serves reads locally,
**falling back to the live API** for anything the local DB can't answer.

---

## 2. Cover Art Archive — album artwork 🔜 easy add

No API key, no bulk download needed — direct per-release URLs:

- `https://coverartarchive.org/release/{release_mbid}/front-250`

Because Release nodes are keyed by MusicBrainz release MBID, artwork can be
fetched on demand without any extra dataset. Good next enhancement for
rendering album thumbnails on Release nodes.

---

## 3. Discogs Monthly Dumps — credits ⚠️ now auth-gated

Discogs publishes monthly XML dumps (Artist, Label, Master, Release) under CC0.
As of 2025 the S3 bucket **no longer allows anonymous access** — requests must
be AWS-signed (returns `403 AccessDenied` otherwise).

- **Entry point:** https://data.discogs.com/
- **Bucket:** `s3://discogs-data-dumps/data/<year>/` (requester must be an
  authenticated AWS principal)
- **Files:** `discogs_YYYYMMDD_{artists,labels,masters,releases}.xml.gz` + `_CHECKSUM.txt`

### How to fetch despite the gate

```bash
# Requires AWS credentials (any account; the data itself is free/CC0)
aws s3 ls s3://discogs-data-dumps/data/2025/
aws s3 cp s3://discogs-data-dumps/data/2025/discogs_20250601_releases.xml.gz .
```

Mirrors also exist on Kaggle (search "Discogs Data Dumps"). The Discogs release
XML carries rich per-track musician credits (`extraartists` with instrument
roles) beyond what MusicBrainz has — a worthwhile future importer, but it needs
the auth-signed download path above. The app already uses the live Discogs API
for these credits when a token is configured.

---

## 4. Other open datasets — future options

| Source | Adds | Access |
|--------|------|--------|
| **Wikidata** (SPARQL / JSON dumps) | genres, band origins, associated acts | fully open |
| **ListenBrainz** data dumps | listen counts, popularity, similar recordings | open, MetaBrainz |
| **AcousticBrainz** dumps | BPM, key, mood, audio features (by MBID) | open (project archived, data still hosted) |
| **MusicBrainz `mbdump-derived.tar.bz2`** | genre tags, ratings | open (same export as #1) |

---

### Summary

The **MusicBrainz full export (#1)** is the one source that is fully open,
anonymous, and covers the whole artist→album→song→credit→label chain — so it's
what the local database is built from today. Everything else above is either an
on-demand URL (Cover Art Archive), an auth-gated extra (Discogs), or a future
enrichment layer.
