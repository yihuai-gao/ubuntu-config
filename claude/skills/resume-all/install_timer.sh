#!/usr/bin/env bash
# Install the minutely snapshot tick for /resume-all (resume_all.py --tick).
# Idempotent; run once per machine (and rerun freely).
#
# Primary: systemd user timer. If the user D-Bus is unreachable (broken/absent
# runtime dir — happens on long-uptime SSH boxes), the unit files are still
# installed and enabled via symlink so the timer arms itself on the next boot,
# and a detached setsid tick loop covers the current uptime.
set -uo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/resume_all.py"
UNIT_DIR="${HOME}/.config/systemd/user"
STATE_DIR="${HOME}/.local/state/claude-resume-all"
mkdir -p "${UNIT_DIR}" "${STATE_DIR}"

cat > "${UNIT_DIR}/claude-resume-all.service" <<EOF
[Unit]
Description=Snapshot live Claude Code sessions for /resume-all recovery

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${SCRIPT} --tick
EOF

cat > "${UNIT_DIR}/claude-resume-all.timer" <<EOF
[Unit]
Description=Minutely Claude Code session snapshot for /resume-all recovery

[Timer]
OnBootSec=45s
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF

# Enable without needing the bus: WantedBy symlink is all `enable` does.
mkdir -p "${UNIT_DIR}/timers.target.wants"
ln -sf "../claude-resume-all.timer" "${UNIT_DIR}/timers.target.wants/claude-resume-all.timer"

if systemctl --user daemon-reload 2>/dev/null && \
   systemctl --user start claude-resume-all.timer 2>/dev/null; then
    echo "systemd user timer installed and started."
    systemctl --user status claude-resume-all.timer --no-pager 2>/dev/null | head -4
else
    echo "systemd user bus unreachable — timer is enabled for the NEXT boot;"
    echo "starting a detached tick loop to cover the current uptime."
    LOOP_PID_FILE="${STATE_DIR}/tick-loop.pid"
    if [[ -f "${LOOP_PID_FILE}" ]] && kill -0 "$(cat "${LOOP_PID_FILE}")" 2>/dev/null; then
        echo "tick loop already running (pid $(cat "${LOOP_PID_FILE}"))."
    else
        setsid nohup bash -c "
            echo \$\$ > '${LOOP_PID_FILE}'
            while true; do
                /usr/bin/python3 '${SCRIPT}' --tick >> '${STATE_DIR}/tick-loop.log' 2>&1
                sleep 60
            done" >/dev/null 2>&1 &
        sleep 1
        echo "tick loop started (pid $(cat "${LOOP_PID_FILE}" 2>/dev/null || echo '?'))."
    fi
fi

echo "State file: ${STATE_DIR}/state.json"
