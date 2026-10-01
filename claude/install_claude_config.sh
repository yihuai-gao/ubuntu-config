#!/usr/bin/env bash
# Install the Claude Code user-level config from this repo into ~/.claude: the PreToolUse hooks (group_name_gate.py,
# composed_config_gate.py -- the cam_uva submission gates), the global CLAUDE.md and settings.json.
#
#   ./install_claude_config.sh            # hooks always; CLAUDE.md / settings.json only when ~/.claude lacks them
#   ./install_claude_config.sh --force    # overwrite CLAUDE.md / settings.json too (a dated backup is kept)
#
# settings.json in this repo names /home/yihuai; the copy is rewritten to the installing user's $HOME. Skills are
# installed by install_skills.sh, the CLIs by install_bin.sh. Nothing here touches ~/.claude/.credentials.json or
# ~/.claude.json (the account + MCP registrations stay per machine).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.claude"
force=0
[ "${1:-}" = "--force" ] && force=1

mkdir -p "${DEST}/hooks"
for f in "${SCRIPT_DIR}"/hooks/*.py; do
    cp -p "${f}" "${DEST}/hooks/$(basename "${f}")"
    chmod +x "${DEST}/hooks/$(basename "${f}")"
    echo "Installed hook: ${DEST}/hooks/$(basename "${f}")"
done

install_file() {  # install_file SRC DEST
    local src=$1 dest=$2
    if [ -e "${dest}" ] && [ "${force}" = 0 ]; then
        echo "Kept existing ${dest} (pass --force to overwrite; repo copy: ${src})"
        return
    fi
    [ -e "${dest}" ] && cp -p "${dest}" "${dest}.bak-$(date +%Y%m%d-%H%M%S)"
    sed "s#/home/yihuai#${HOME}#g" "${src}" > "${dest}"
    echo "Installed ${dest}"
}
install_file "${SCRIPT_DIR}/CLAUDE.md" "${DEST}/CLAUDE.md"
install_file "${SCRIPT_DIR}/settings.json" "${DEST}/settings.json"
echo "Done. Hooks -> ${DEST}/hooks; skills: ./install_skills.sh; CLIs: ./install_bin.sh"
