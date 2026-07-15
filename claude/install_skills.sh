#!/usr/bin/env bash
# Install Claude Code global skills from this repo into ~/.claude/skills.
# Each skill is a directory containing a SKILL.md (plus optional scripts).
# Existing skills with the same name are overwritten; other skills already
# installed on this machine are left untouched.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/skills"
DEST_DIR="${HOME}/.claude/skills"

if [[ ! -d "${SRC_DIR}" ]]; then
    echo "Error: skills source directory not found: ${SRC_DIR}" >&2
    exit 1
fi

mkdir -p "${DEST_DIR}"

for skill_path in "${SRC_DIR}"/*/; do
    skill_name="$(basename "${skill_path}")"
    rm -rf "${DEST_DIR:?}/${skill_name}"
    cp -r "${skill_path}" "${DEST_DIR}/${skill_name}"
    echo "Installed skill: ${skill_name}"
done

echo "Done. Skills installed to ${DEST_DIR}"
