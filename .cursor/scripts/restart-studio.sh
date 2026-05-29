#!/usr/bin/env bash
# Kill and restart Email Assistant Studio (FastAPI + uvicorn).
# Usage: .cursor/scripts/restart-studio.sh {stop|start|restart|status}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VENV="${VENV:-$ROOT/.venv}"
PIDFILE="$ROOT/.cursor/runtime/studio.pid"
LOGFILE="$ROOT/.cursor/runtime/studio.log"

# Dedicated port/host — override in .env (STUDIO_PORT, STUDIO_HOST)
STUDIO_HOST="${STUDIO_HOST:-127.0.0.1}"
STUDIO_PORT="${STUDIO_PORT:-8080}"

load_env_var() {
  local key="$1" default="$2"
  if [[ -f "$ROOT/.env" ]]; then
    local line val
    line="$(grep -E "^${key}=" "$ROOT/.env" | tail -1 || true)"
    if [[ -n "$line" ]]; then
      val="${line#*=}"
      val="${val%\"}"
      val="${val#\"}"
      val="${val%\'}"
      val="${val#\'}"
      if [[ -n "$val" ]]; then
        echo "$val"
        return
      fi
    fi
  fi
  echo "$default"
}

STUDIO_HOST="$(load_env_var STUDIO_HOST "$STUDIO_HOST")"
STUDIO_PORT="$(load_env_var STUDIO_PORT "$STUDIO_PORT")"
STUDIO_URL="http://${STUDIO_HOST}:${STUDIO_PORT}"

mkdir -p "$(dirname "$PIDFILE")"

log() { printf '[studio] %s\n' "$*"; }

pids_on_port() {
  lsof -ti ":${STUDIO_PORT}" -sTCP:LISTEN 2>/dev/null || true
}

is_running() {
  local pids
  pids="$(pids_on_port)"
  [[ -n "$pids" ]]
}

stop_studio() {
  local pids killed=0

  if [[ -f "$PIDFILE" ]]; then
    local saved_pid
    saved_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$saved_pid" ]] && kill -0 "$saved_pid" 2>/dev/null; then
      log "Stopping PID $saved_pid (from pidfile)..."
      kill "$saved_pid" 2>/dev/null || true
      sleep 1
      kill -9 "$saved_pid" 2>/dev/null || true
      killed=1
    fi
    rm -f "$PIDFILE"
  fi

  pids="$(pids_on_port)"
  if [[ -n "$pids" ]]; then
    log "Stopping process(es) on port ${STUDIO_PORT}: ${pids//$'\n'/ }"
    # shellcheck disable=SC2046
    kill $(echo "$pids" | tr '\n' ' ') 2>/dev/null || true
    sleep 1
    pids="$(pids_on_port)"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2046
      kill -9 $(echo "$pids" | tr '\n' ' ') 2>/dev/null || true
    fi
    killed=1
  fi

  if [[ "$killed" -eq 1 ]]; then
    log "Studio stopped."
  else
    log "Studio was not running on port ${STUDIO_PORT}."
  fi
}

activate_venv() {
  if [[ ! -d "$VENV" ]]; then
    log "ERROR: venv not found at $VENV"
    log "Create it: python3.12 -m venv .venv && source .venv/bin/activate && pip install -e \".[dev]\""
    exit 1
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
}

preflight() {
  if [[ ! -f "$ROOT/.env" ]]; then
    log "WARNING: .env missing — copy from .env.example"
  fi
  if ! command -v email-assistant >/dev/null 2>&1; then
    log "ERROR: email-assistant not on PATH — run: pip install -e \".[dev]\" inside venv"
    exit 1
  fi
}

wait_for_health() {
  local attempts="${1:-30}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -sf "${STUDIO_URL}/api/status" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

start_studio() {
  if is_running; then
    log "Studio already running on ${STUDIO_URL} — use 'restart' to recycle."
    status_studio
    exit 0
  fi

  activate_venv
  preflight

  log "Starting Email Assistant Studio..."
  log "  venv:  $VENV"
  log "  url:   $STUDIO_URL"
  log "  log:   $LOGFILE"

  nohup email-assistant ui \
    --host "$STUDIO_HOST" \
    --port "$STUDIO_PORT" \
    --no-open \
    >>"$LOGFILE" 2>&1 &

  local pid=$!
  echo "$pid" >"$PIDFILE"
  log "Started PID $pid"

  if wait_for_health 30; then
    log "Health check OK → ${STUDIO_URL}/api/status"
  else
    log "ERROR: Studio did not become healthy within 15s"
    log "Tail log: tail -f $LOGFILE"
    exit 1
  fi
}

status_studio() {
  if is_running; then
    log "RUNNING on ${STUDIO_URL}"
    if [[ -f "$PIDFILE" ]]; then
      log "  pidfile: $(cat "$PIDFILE")"
    fi
    if curl -sf "${STUDIO_URL}/api/status" >/dev/null 2>&1; then
      log "  health:  OK"
    else
      log "  health:  FAIL (port in use but /api/status unreachable)"
    fi
  else
    log "STOPPED (port ${STUDIO_PORT} free)"
  fi
}

case "${1:-restart}" in
  stop)
    stop_studio
    ;;
  start)
    start_studio
    ;;
  restart)
    stop_studio
    sleep 0.5
    start_studio
    ;;
  status)
    status_studio
    ;;
  *)
    echo "Usage: $0 {stop|start|restart|status}" >&2
    exit 1
    ;;
esac
