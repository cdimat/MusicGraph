#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  MusicGraph Launcher
#  Double-click this file from Finder / your Desktop to start the app.
#
#  FIRST-TIME SETUP (run once in Terminal):
#    chmod +x /path/to/MusicGraph.command
#
#  What this does:
#    1. Confirms Docker Desktop is running
#    2. Starts Neo4j + PostgreSQL + Backend via docker compose
#    3. Waits (no timeout) for the backend health-check to pass
#       Note: Neo4j takes ~60 s on a cold start; the backend starts after it.
#    4. Starts the Vite frontend dev server
#    5. Opens http://localhost:5173 in your browser
# ─────────────────────────────────────────────────────────────────────────────

PROJECT="/Users/christopherdimatteo/MusicGraph"

# ── ANSI colours ─────────────────────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
AMBER='\033[38;5;214m'
GREEN='\033[38;5;114m'
RED='\033[38;5;203m'
YELLOW='\033[38;5;221m'

# ── Header ───────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${AMBER}${BOLD}♪  MusicGraph${RESET}"
echo -e "  ${DIM}────────────────────────────────────────${RESET}"
echo ""

# ── Check Docker ─────────────────────────────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo -e "  ${RED}✗  Docker is not running.${RESET}"
    echo ""
    echo -e "  Please start ${BOLD}Docker Desktop${RESET} and try again."
    echo ""
    osascript -e 'display alert "Docker is not running" message "Please start Docker Desktop, then double-click MusicGraph again." buttons {"OK"} default button "OK"' 2>/dev/null || true
    echo "  Press any key to exit…"
    read -rn1
    exit 1
fi

# ── Docker services ───────────────────────────────────────────────────────────
echo -e "  ${DIM}Starting services (Neo4j · PostgreSQL · Backend)…${RESET}"
cd "$PROJECT"
docker compose up -d --remove-orphans 2>&1 || true
echo ""

# ── Wait for backend — no hard timeout ───────────────────────────────────────
# Neo4j takes ~60 s on a cold start; backend waits for it before launching.
# We poll every 3 s and print a dot each tick so you can see progress.
# The elapsed timer in brackets reassures you it hasn't frozen.

if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓  Backend already running${RESET}"
else
    echo -e "  ${DIM}Waiting for backend (Neo4j takes ~60 s on first start)…${RESET}"
    printf "  "
    SECS=0
    while ! curl -sf http://localhost:8000/health > /dev/null 2>&1; do
        printf "."
        sleep 3
        SECS=$((SECS + 3))
        # Print elapsed time every 30 s so it's clear things are still moving
        if [ $((SECS % 30)) -eq 0 ]; then
            printf " [${SECS}s] "
        fi
    done
    echo ""
    echo -e "  ${GREEN}✓  Backend ready${RESET} (${SECS}s)"
fi
echo ""

# ── Frontend dev server ───────────────────────────────────────────────────────
echo -e "  ${DIM}Starting frontend dev server…${RESET}"
cd "$PROJECT/frontend"

# Kill any stale Vite process left on port 5173
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

npm run dev > /tmp/musicgraph-vite.log 2>&1 &
VITE_PID=$!

# Wait up to 30 s for Vite
for i in $(seq 1 30); do
    if curl -sf http://localhost:5173 > /dev/null 2>&1; then
        break
    fi
    sleep 1
done
echo -e "  ${GREEN}✓  Frontend ready${RESET}"

# ── Open browser ──────────────────────────────────────────────────────────────
sleep 0.3
open http://localhost:5173

# ── Status summary ────────────────────────────────────────────────────────────
echo ""
echo -e "  ${AMBER}${BOLD}MusicGraph is live${RESET}"
echo ""
echo -e "  ${BOLD}→  http://localhost:5173${RESET}   ${DIM}(app)${RESET}"
echo -e "  ${DIM}   http://localhost:8000   (API)"
echo -e "     http://localhost:7474   (Neo4j browser)"
echo -e "     http://localhost:5432   (PostgreSQL)${RESET}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop the frontend."
echo -e "  ${DIM}Docker services continue running in the background."
echo -e "  Run  docker compose down  in the project folder to stop everything.${RESET}"
echo ""

# ── Keep Terminal open; clean up on Ctrl+C ────────────────────────────────────
trap '
    echo ""
    echo -e "  ${DIM}Stopping frontend server…${RESET}"
    kill "$VITE_PID" 2>/dev/null || true
    echo -e "  ${DIM}Done. Docker services are still running.${RESET}"
    echo ""
    exit 0
' INT TERM

wait "$VITE_PID"
