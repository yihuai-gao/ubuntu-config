#!/usr/bin/env bash
# Install Claude Code helper CLIs from this repo's claude/bin into ~/.local/bin.
# Currently: claude-acct (switch Claude Code accounts without re-login, show usage).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/bin"
DEST_DIR="${HOME}/.local/bin"

mkdir -p "${DEST_DIR}"
for f in "${SRC_DIR}"/*; do
    name="$(basename "${f}")"
    cp "${f}" "${DEST_DIR}/${name}"
    chmod +x "${DEST_DIR}/${name}"
    echo "Installed ${name} -> ${DEST_DIR}/${name}"
done
