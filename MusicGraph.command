#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  MusicGraph Launcher
#  Double-click from Finder / your Desktop to start the app.
#
#  FIRST-TIME SETUP (one-time, in Terminal):
#    chmod +x ~/Desktop/MusicGraph.command
# ─────────────────────────────────────────────────────────────────────────────

PROJECT="/Users/christopherdimatteo/MusicGraph"

RESET='\033[0m';  BOLD='\033[1m';  DIM='\033[2m'
AMBER='\033[38;5;214m';  GREEN='\033[38;5;114m';  RED='\033[38;5;203m'

clear
echo ""
echo -e "  ${AMBER}${BOLD}♪  MusicGraph${RESET}"
echo -e "  ${DIM}────────────────────────────────────────${RESET}"
echo ""

# ── 1. Docker check ───────────────────────────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo -e "  ${RED}✗  Docker is not running.${RESET}"
    echo -e "  Start Docker Desktop then double-click this again."
    osascript -e 'display alert "Docker is not running" message "Start Docker Desktop, then double-click MusicGraph again." buttons {"OK"}' 2>/dev/null || true
    read -rn1 -p "  Press any key to exit…"
    exit 1
fi

# ── 2. Start Docker services ──────────────────────────────────────────────────
echo -e "  ${DIM}Starting Docker services…${RESET}"
cd "$PROJECT"
docker compose up -d 2>&1 | tail -5 | sed 's/^/    /'
echo ""

# ── 3. Kill anything stale on Vite's port ─────────────────────────────────────
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

# ── 4. Start Vite frontend ────────────────────────────────────────────────────
echo -e "  ${DIM}Starting frontend…${RESET}"
cd "$PROJECT/frontend"
npm run dev > /tmp/musicgraph-vite.log 2>&1 &
VITE_PID=$!

# Give Vite a moment to bind the port
for i in $(seq 1 20); do
    curl -sf http://localhost:5173 > /dev/null 2>&1 && break
    sleep 1
done

echo -e "  ${GREEN}✓  Frontend ready${RESET}"

# ── 5. Open browser ───────────────────────────────────────────────────────────
open http://localhost:5173

# ── 6. Status ─────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${AMBER}${BOLD}MusicGraph is live → http://localhost:5173${RESET}"
echo ""
echo -e "  ${DIM}Backend (API)  http://localhost:8000"
echo -e "  Neo4j          http://localhost:7474"
echo -e "  PostgreSQL     http://localhost:5432"
echo ""
echo -e "  Note: Neo4j takes ~60 s on a cold start."
echo -e "  If searches fail at first, wait a moment and try again.${RESET}"
echo ""
echo -e "  ${BOLD}Ctrl+C${RESET}${DIM} stops the frontend. Docker keeps running."
echo -e "  'docker compose down' in the project folder stops everything.${RESET}"
echo ""

# ── 7. Keep window open ───────────────────────────────────────────────────────
trap '
    echo ""
    echo -e "  ${DIM}Stopping frontend…${RESET}"
    kill "$VITE_PID" 2>/dev/null || true
    exit 0
' INT TERM

wait "$VITE_PID"
