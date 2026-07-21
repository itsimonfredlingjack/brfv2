#!/usr/bin/env bash
# Demo process control: start/stop the pilot backend + canonical frontend as
# tracked, named background processes (PID files under .demo/), so `stop`
# only ever kills what `start` actually launched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT/.demo"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
FRONTEND_PID_FILE="$STATE_DIR/frontend.pid"
BACKEND_LOG="$STATE_DIR/backend.log"
FRONTEND_LOG="$STATE_DIR/frontend.log"

TUNNEL_URL="http://127.0.0.1:8000/v1"
BACKEND_URL="http://127.0.0.1:8787"
FRONTEND_URL="http://127.0.0.1:5173/brfv2/"
REQUIRED_MODEL="gemma4:e12b"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

fail() {
  red "FEL: $*"
  exit 1
}

check_tunnel() {
  local models_json
  if ! models_json=$(curl -sf --max-time 5 "$TUNNEL_URL/models" 2>/dev/null); then
    red "SSH-tunneln till agenntserver saknas eller port 8000 svarar inte."
    echo "Starta den i en egen terminal och försök igen:"
    echo
    echo "  ssh -N -L 8000:127.0.0.1:8000 agenntserver"
    echo
    exit 1
  fi

  # The llama.cpp OpenAI-compat server reports its model `id` as the full
  # weights file path (not the BRF_LLM_MODEL alias we send in requests), so
  # match on the model family/size in that id rather than an exact string.
  if ! echo "$models_json" | jq -e '[.data[]?.id | ascii_downcase | select(contains("gemma-4-12b") or contains("gemma4-12b") or contains("gemma_4_12b"))] | length > 0' >/dev/null 2>&1; then
    red "Modelltjänsten på port 8000 annonserar ingen Gemma 4 12B-modell."
    echo "Tillgängliga modeller:"
    echo "$models_json" | jq -r '.data[]?.id // empty' | sed 's/^/  - /'
    echo
    echo "Detta är inte agenntserver-tjänsten med Gemma 4 12B. Kontrollera tunneln"
    echo "och att Ubuntu-servern kör rätt modell. Ingen fallback till Macens"
    echo "lokala Ollama (gemma4:e4b) sker eller ska ske."
    exit 1
  fi

  green "SSH-tunnel OK — port 8000 annonserar Gemma 4 12B."
}

pid_is_alive_and_named() {
  # $1 = pid file, $2 = substring expected in its command line
  local pid_file="$1" expect="$2" pid
  [ -f "$pid_file" ] || return 1
  pid=$(cat "$pid_file")
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  ps -o command= -p "$pid" 2>/dev/null | grep -qF "$expect" || return 1
  return 0
}

port_in_use_by_other() {
  # $1 = port, $2 = pid we own (may be empty) -> 0 if occupied by a PID we don't own
  local port="$1" own_pid="${2:-}" holder
  holder=$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)
  [ -z "$holder" ] && return 1
  if [ -n "$own_pid" ] && [ "$holder" = "$own_pid" ]; then
    return 1
  fi
  echo "$holder"
  return 0
}

wait_for_http() {
  local url="$1" tries="${2:-40}"
  for _ in $(seq 1 "$tries"); do
    curl -sf --max-time 2 "$url" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 1
}

cmd_start() {
  mkdir -p "$STATE_DIR"

  if pid_is_alive_and_named "$BACKEND_PID_FILE" "uvicorn"; then
    yellow "Backend körs redan (PID $(cat "$BACKEND_PID_FILE")) — hoppar över start."
  else
    rm -f "$BACKEND_PID_FILE"
    local holder=""
    holder=$(port_in_use_by_other 8787 || true)
    if [ -n "$holder" ]; then
      # Not a process we started (no/stale PID file). If it's already a
      # healthy pilot/selfhosted backend, adopt it rather than kill or
      # duplicate it — we never touch processes `make demo` didn't start,
      # so `make demo-stop` will knowingly leave it running.
      local health mode provider
      if health=$(curl -sf --max-time 3 "$BACKEND_URL/api/health" 2>/dev/null) \
          && mode=$(echo "$health" | jq -r '.mode') \
          && provider=$(echo "$health" | jq -r '.llm_provider') \
          && [ "$mode" = "pilot" ] && [ "$provider" = "selfhosted" ]; then
        yellow "Port 8787 hade redan en fristående pilot-backend (PID $holder) igång — återanvänder den. 'make demo-stop' rör den inte."
      else
        fail "Port 8787 är upptagen av en okänd process (PID $holder) som inte är en giltig pilot-backend (mode=${mode:-?} llm_provider=${provider:-?}). Kör 'make demo-stop' eller undersök processen manuellt — vi dödar inte okända processer automatiskt."
      fi
    else
      check_tunnel

      echo "Startar backend (pilot, Gemma 4 12B via agenntserver) på :8787 ..."
      (
        cd "$ROOT/backend"
        exec env BRF_MODE=pilot BRF_LLM=selfhosted \
          BRF_LLM_BASE_URL="$TUNNEL_URL" BRF_LLM_MODEL="$REQUIRED_MODEL" \
          uv run uvicorn app.main:create_app --factory --port 8787
      ) >"$BACKEND_LOG" 2>&1 &
      echo $! > "$BACKEND_PID_FILE"

      if ! wait_for_http "$BACKEND_URL/api/health" 60; then
        red "Backend svarade inte på $BACKEND_URL/api/health inom tidsgränsen."
        tail -n 40 "$BACKEND_LOG" || true
        cmd_stop
        exit 1
      fi

      local health mode provider
      health=$(curl -sf "$BACKEND_URL/api/health")
      mode=$(echo "$health" | jq -r '.mode')
      provider=$(echo "$health" | jq -r '.llm_provider')
      if [ "$mode" != "pilot" ] || [ "$provider" != "selfhosted" ]; then
        red "Backend startade men rapporterar mode=$mode llm_provider=$provider (väntat pilot/selfhosted)."
        tail -n 40 "$BACKEND_LOG" || true
        cmd_stop
        exit 1
      fi
      green "Backend redo — mode=pilot, llm_provider=selfhosted."
    fi
  fi

  if pid_is_alive_and_named "$FRONTEND_PID_FILE" "vite"; then
    yellow "Frontend körs redan (PID $(cat "$FRONTEND_PID_FILE")) — hoppar över start."
  else
    rm -f "$FRONTEND_PID_FILE"
    local fholder=""
    fholder=$(port_in_use_by_other 5173 || true)
    if [ -n "$fholder" ]; then
      if curl -sf --max-time 3 "$FRONTEND_URL" >/dev/null 2>&1; then
        yellow "Port 5173 hade redan en fristående frontend (PID $fholder) igång — återanvänder den. 'make demo-stop' rör den inte."
      else
        fail "Port 5173 är upptagen av en okänd process (PID $fholder) som inte svarar korrekt. Kör 'make demo-stop' eller undersök processen manuellt."
      fi
    else
      echo "Startar kanoniska frontend (brfv2-mockup) på :5173 ..."
      (
        cd "$ROOT/brfv2-mockup"
        exec node_modules/.bin/vite --host 127.0.0.1 --port 5173
      ) >"$FRONTEND_LOG" 2>&1 &
      echo $! > "$FRONTEND_PID_FILE"

      if ! wait_for_http "$FRONTEND_URL" 40; then
        red "Frontend svarade inte på $FRONTEND_URL inom tidsgränsen."
        tail -n 40 "$FRONTEND_LOG" || true
        cmd_stop
        exit 1
      fi
      green "Frontend redo."
    fi
  fi

  echo
  green "Demo igång:"
  echo "  URL:      $FRONTEND_URL"
  echo "  Backend:  $BACKEND_URL  (mode=pilot, llm_provider=selfhosted, modell=$REQUIRED_MODEL)"
  echo
  echo "Demokonton (kör 'make demo-reset' först om detta är en ren miljö):"
  echo "  anna@gjutformen12.se  / gjutformen-demo-2026   (admin, Brf Gjutformen 12)"
  echo "  bo@gjutformen12.se    / gjutformen-medlem-2026 (medlem, Brf Gjutformen 12 — ingen upload/delete)"
  echo "  stina@sjoutsikten7.se / sjoutsikten-demo-2026  (admin, Brf Sjöutsikten 7)"
  echo "  max@demo.se           / max-demo-2026          (två föreningar — visar BRF-växlaren)"
  echo
  echo "Loggar: $BACKEND_LOG , $FRONTEND_LOG"
}

stop_one() {
  local pid_file="$1" name="$2" expect="$3"
  if [ ! -f "$pid_file" ]; then
    yellow "$name: ingen PID-fil, inget att stoppa."
    return 0
  fi
  local pid
  pid=$(cat "$pid_file")
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    yellow "$name: PID $pid körs inte längre."
    rm -f "$pid_file"
    return 0
  fi
  if ! ps -o command= -p "$pid" 2>/dev/null | grep -qF "$expect"; then
    yellow "$name: PID $pid matchar inte förväntad process ('$expect') — lämnar den orörd."
    rm -f "$pid_file"
    return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.3
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  green "$name (PID $pid) stoppad."
}

cmd_stop() {
  stop_one "$FRONTEND_PID_FILE" "Frontend" "vite"
  stop_one "$BACKEND_PID_FILE" "Backend" "uvicorn"
}

cmd_status() {
  if pid_is_alive_and_named "$BACKEND_PID_FILE" "uvicorn"; then
    green "Backend: körs (PID $(cat "$BACKEND_PID_FILE"), startad av make demo)"
  elif health=$(curl -sf --max-time 3 "$BACKEND_URL/api/health" 2>/dev/null); then
    yellow "Backend: körs men inte startad av make demo (mode=$(echo "$health" | jq -r '.mode') llm_provider=$(echo "$health" | jq -r '.llm_provider')) — 'make demo-stop' rör den inte."
  else
    yellow "Backend: stoppad"
  fi
  if pid_is_alive_and_named "$FRONTEND_PID_FILE" "vite"; then
    green "Frontend: körs (PID $(cat "$FRONTEND_PID_FILE"), startad av make demo)"
  elif curl -sf --max-time 3 "$FRONTEND_URL" >/dev/null 2>&1; then
    yellow "Frontend: körs men inte startad av make demo — 'make demo-stop' rör den inte."
  else
    yellow "Frontend: stoppad"
  fi
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  check-tunnel) check_tunnel ;;
  *) echo "Usage: $0 {start|stop|status|check-tunnel}"; exit 2 ;;
esac
