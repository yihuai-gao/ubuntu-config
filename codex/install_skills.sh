#!/usr/bin/env bash
# Sync Codex global skills from this repository into the active Codex home.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/skills"
CODEX_SKILLS_DIR="${CODEX_HOME:-${HOME}/.codex}/skills"

if [[ ! -d "${SOURCE_DIR}" ]]; then
    echo "Error: skills source directory not found: ${SOURCE_DIR}" >&2
    exit 1
fi

mkdir -p "${CODEX_SKILLS_DIR}"
shopt -s nullglob
skill_paths=("${SOURCE_DIR}"/*/)

if (( ${#skill_paths[@]} == 0 )); then
    echo "Error: no skills found in ${SOURCE_DIR}" >&2
    exit 1
fi

for skill_path in "${skill_paths[@]}"; do
    skill_name="$(basename "${skill_path}")"
    if [[ ! -f "${skill_path}/SKILL.md" ]]; then
        echo "Error: ${skill_path} has no SKILL.md" >&2
        exit 1
    fi
    rm -rf -- "${CODEX_SKILLS_DIR:?}/${skill_name}"
    cp -a -- "${skill_path}" "${CODEX_SKILLS_DIR}/${skill_name}"
    echo "Installed skill: ${skill_name}"
done

echo "Done. Skills synced to ${CODEX_SKILLS_DIR}"
