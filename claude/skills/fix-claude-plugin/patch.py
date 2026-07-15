#!/usr/bin/env python3
"""Patch the Claude Code IDE extension (Cursor / VS Code) bundles to fix
behaviors that cannot be changed through any supported setting.

The extension re-ships its bundles on every update (a new versioned
directory), so this script is re-runnable: it finds all installed extension
copies, patches any that still contain the original code, and skips ones
already patched. Run it again after each extension update.

Current patches (see SKILL.md for full background on each):

1. [webview/index.js] shift+tab "cycle permission mode" -> no-op.
   Hardcoded webview keydown handler; not remappable via
   ~/.claude/keybindings.json (terminal-CLI only) or VS Code keybindings.

2. [extension.js] Honor `remoteControlAtStartup`.
   Auto-enable IS wired (verified 2.1.207): on init the host checks
   `remoteControlAutoEnableOn(g) && g.remote_control_auto_enable && ...`
   then calls `toggleRemoteControl`. But `remoteControlAutoEnableOn(e)`
   returns `e.ide_rc_auto_enable_gate===true` — the GrowthBook rollout
   kill-switch (`tengu_ide_rc_auto_enable`, default false), independent of
   your setting. Until Anthropic flips it, the setting is silently ignored
   in the IDE. We force the gate method `return!0`; the
   `remote_control_auto_enable` check (your remoteControlAtStartup) stays,
   so auto-enable still follows settings.json.
   (Builds ~2.1.181-2.1.201 briefly removed this method; on those the patch
   reports NOT FOUND. 2.1.203+ restored it.)

3. [extension.js] Start every session in "auto" permission mode.
   getInitialPermissionMode() otherwise resolves: claudeCode.initialPermissionMode
   setting -> persisted last-used mode (globalState "defaultPermissionMode")
   -> "default". The persisted last-used mode is how sessions keep starting
   in bypassPermissions. We insert an early `return"auto"`. If Auto mode is
   unavailable (model/gate), the webview safely falls back to "default",
   never bypass. You can still switch modes freely within a session.

Each patch matches by STRUCTURE (minified identifiers change every release;
API-shape names like `remoteControlAutoEnableOn` survive), using regex
backreferences so we only touch the intended code.
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patch definitions. Each entry:
#   name      : human label
#   target    : bundle path relative to the extension directory
#   find      : compiled regex matching the original (unpatched) code
#   replace   : replacement (callable taking the match, or a string)
#   already   : compiled regex that is True iff this file is ALREADY patched
#               (used to distinguish "already done" from "not found / changed")
# ---------------------------------------------------------------------------

PATCHES = [
    {
        "name": "shift+tab cycles permission mode -> no-op",
        "target": "webview/index.js",
        # Original:  X.key==="Tab"&&X.shiftKey){X.preventDefault(),Y();return}
        # Y() is the permission-mode cycle call. We drop ",Y()" so shift+tab
        # is swallowed (preventDefault + return) and does nothing.
        "find": re.compile(
            r'(?P<p>\w+)\.key==="Tab"&&(?P=p)\.shiftKey\)\{'
            r'(?P=p)\.preventDefault\(\),\w+\(\);return\}'
        ),
        "replace": lambda m: (
            f'{m.group("p")}.key==="Tab"&&{m.group("p")}.shiftKey){{'
            f'{m.group("p")}.preventDefault();return}}'
        ),
        "already": re.compile(
            r'\w+\.key==="Tab"&&(\w+)\.shiftKey\)\{\1\.preventDefault\(\);return\}'
        ),
    },
    {
        "name": "remoteControlAtStartup rollout gate -> always on",
        "target": "extension.js",
        # Current shipping form (verified 2.1.207): auto-enable is fully
        # wired, but AND-gated on the GrowthBook rollout kill-switch:
        #   remoteControlAutoEnableOn(e){return e.ide_rc_auto_enable_gate===!0}
        # The call site is
        #   this.remoteControlAutoEnableOn(g)&&g.remote_control_auto_enable
        #   &&channel.remoteControlState==="disconnected"&&... this.toggleRemoteControl(...)
        # so forcing this method to return true, while leaving
        # g.remote_control_auto_enable (your remoteControlAtStartup setting)
        # intact, makes auto-enable follow your settings.json exactly.
        # NOTE: builds ~2.1.181-2.1.201 briefly stripped this method out
        # entirely (NOT FOUND on those) before 2.1.203+ restored it.
        # Only the parameter name can change between releases.
        "find": re.compile(
            r'remoteControlAutoEnableOn\((\w+)\)\{'
            r'return \1\.ide_rc_auto_enable_gate===!0\}'
        ),
        "replace": lambda m: (
            f'remoteControlAutoEnableOn({m.group(1)}){{return!0}}'
        ),
        "already": re.compile(
            r'remoteControlAutoEnableOn\(\w+\)\{return!0\}'
        ),
    },
    {
        "name": 'initial permission mode -> "auto" (never bypass)',
        "target": "extension.js",
        # Original method starts: getInitialPermissionMode(){let e=...
        # We insert an early return, leaving the original body as dead code
        # (no brace counting needed in minified source).
        "find": re.compile(r'getInitialPermissionMode\(\)\{let '),
        "replace": 'getInitialPermissionMode(){return"auto";let ',
        "already": re.compile(r'getInitialPermissionMode\(\)\{return"auto";'),
    },
]

EXT_GLOBS = [
    "~/.cursor-server/extensions",
    "~/.cursor/extensions",
    "~/.vscode-server/extensions",
    "~/.vscode/extensions",
    "~/.vscode-server-insiders/extensions",
]


def find_bundles(target: str):
    bundles = []
    for base in EXT_GLOBS:
        root = Path(base).expanduser()
        if not root.is_dir():
            continue
        for d in root.glob("anthropic.claude-code-*"):
            js = d / target
            if js.is_file():
                bundles.append(js)
    # de-dup (some setups symlink), keep stable order
    seen, uniq = set(), []
    for js in sorted(bundles):
        rp = js.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(js)
    return uniq


def patch_file(js: Path, patches) -> dict:
    text = js.read_text(encoding="utf-8", errors="surrogatepass")
    report = {"file": str(js), "results": []}
    new = text
    changed = False
    for p in patches:
        patched, n = p["find"].subn(p["replace"], new)
        if n > 0:
            new = patched
            changed = True
            report["results"].append((p["name"], f"patched ({n})"))
        elif p["already"].search(new):
            report["results"].append((p["name"], "already patched"))
        else:
            report["results"].append((p["name"], "NOT FOUND (verify manually)"))

    if changed:
        bak = js.with_suffix(".js.prepatch-bak")
        if not bak.exists():
            bak.write_text(text, encoding="utf-8", errors="surrogatepass")
        js.write_text(new, encoding="utf-8", errors="surrogatepass")
        report["wrote"] = True
    else:
        report["wrote"] = False
    return report


def main():
    by_target = {}
    for p in PATCHES:
        by_target.setdefault(p["target"], []).append(p)

    any_notfound = False
    any_found = False
    for target, patches in by_target.items():
        bundles = find_bundles(target)
        if not bundles:
            print(f"No Claude Code extension '{target}' bundles found.", file=sys.stderr)
            print("Searched:", ", ".join(EXT_GLOBS), file=sys.stderr)
            continue
        any_found = True
        for js in bundles:
            rep = patch_file(js, patches)
            print(f"\n{rep['file']}")
            for name, status in rep["results"]:
                mark = {"patched": "✔", "already": "•"}.get(status.split()[0], "✗")
                print(f"  {mark} {name}: {status}")
                if "NOT FOUND" in status:
                    any_notfound = True
            if rep["wrote"]:
                print(f"  -> written (backup: {js.with_suffix('.js.prepatch-bak')})")

    if not any_found:
        return 1
    print(
        "\nReload the IDE window (Cmd/Ctrl+Shift+P -> 'Reload Window') "
        "for changes to take effect."
    )
    return 2 if any_notfound else 0


if __name__ == "__main__":
    sys.exit(main())
