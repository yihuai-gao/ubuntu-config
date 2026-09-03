#!/usr/bin/env bash
# Per-process network traffic dashboard. Needs root for raw sockets + /proc/<pid>/fd.
#   ./traffic_monitor.sh                 # capture default-route NICs, serve http://127.0.0.1:8787
#   ./traffic_monitor.sh -i enp6s0 -i wlp7s0 -p 9000
#   ./traffic_monitor.sh --text          # top-like terminal view instead of the web page
#   ./traffic_monitor.sh --help
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $EUID -ne 0 ]]; then
  exec sudo -- "${PYTHON:-python3}" "$DIR/traffic_monitor.py" "$@"
fi
exec "${PYTHON:-python3}" "$DIR/traffic_monitor.py" "$@"
