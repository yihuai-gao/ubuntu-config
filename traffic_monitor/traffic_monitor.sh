#!/usr/bin/env bash
# Per-process network traffic dashboard. Needs root for raw sockets + /proc/<pid>/fd.
#   ./traffic_monitor.sh                 # capture default-route NICs, serve http://127.0.0.1:8787
#   ./traffic_monitor.sh -i enp6s0 -i wlp7s0 -p 9000
#   ./traffic_monitor.sh --text          # top-like terminal view instead of the web page
#   ./traffic_monitor.sh --counters-only  # no sudo: overall interface rates only (no per-process rows)
#   ./traffic_monitor.sh --help
# A previous traffic_monitor.py instance (any port) is stopped first, so re-running the
# script after a code change just replaces the server. Set TM_KEEP_RUNNING=1 to skip that.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/traffic_monitor.py"
PYTHON="${PYTHON:-python3}"

for a in "$@"; do
  case "$a" in --selftest|-h|--help|--counters-only) exec "$PYTHON" "$PY" "$@" ;; esac   # no root needed
done

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PYTHON,TM_KEEP_RUNNING -- bash "${BASH_SOURCE[0]}" "$@"
fi

if [[ -z "${TM_KEEP_RUNNING:-}" ]]; then
  # every other python process running traffic_monitor.py (anchored, so an editor or shell that
  # merely mentions the file is not matched; old-style `sudo -- python3 ...` wrappers exit with their child)
  PAT='^[^ ]*python[0-9.]* [^ ]*traffic_monitor\.py( |$)'
  mapfile -t old < <(pgrep -f "$PAT" | grep -vx -e "$$" -e "$PPID" || true)
  if ((${#old[@]})); then
    echo "[traffic_monitor] stopping previous instance: pid(s) ${old[*]}" >&2
    kill -TERM "${old[@]}" 2>/dev/null || true
    for _ in $(seq 20); do
      pgrep -f "$PAT" | grep -vx -e "$$" -e "$PPID" >/dev/null || break
      sleep 0.1
    done
    kill -KILL "${old[@]}" 2>/dev/null || true
  fi
fi

exec "$PYTHON" "$PY" "$@"
