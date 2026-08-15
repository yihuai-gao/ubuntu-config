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
   Auto-enable IS wired, but AND-gated on `ide_rc_auto_enable_gate` — the
   GrowthBook rollout kill-switch (`tengu_ide_rc_auto_enable`, default
   false), independent of your setting. Until Anthropic flips it, the
   setting is silently ignored in the IDE. We kill only that gate and keep
   the `remote_control_auto_enable` check (your remoteControlAtStartup), so
   auto-enable follows settings.json exactly. Two code shapes are handled
   (2.1.233+ helper form, and the older inline-gate method); see the patch
   entry. Builds ~2.1.181-2.1.201 had neither -> NOT FOUND.

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
#
# A patch may instead supply `alts`: a list of (find, replace, already)
# triples, for behaviors whose shipping code shape differs across extension
# versions. The first variant that matches is applied; the patch counts as
# "already patched" if ANY variant's `already` matches.
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
        # Two shipping shapes seen so far; both AND-gate auto-enable on the
        # GrowthBook rollout kill-switch `ide_rc_auto_enable_gate`
        # (tengu_ide_rc_auto_enable, default false). In both we kill ONLY the
        # gate and keep the `remote_control_auto_enable` check (= your
        # remoteControlAtStartup setting), so auto-enable follows settings.json.
        #
        # (a) 2.1.233+ : the gate moved into a module-level helper that also
        #     folds in the setting check, and the call site no longer tests
        #     the setting separately:
        #       remoteControlAutoEnableOn(e){return aTe(e)}
        #       function aTe(e){if(e.remote_control_auto_enable!==!0)return!1;
        #         return e.remote_control_auto_on_by_default===!1
        #             ||e.ide_rc_auto_enable_gate===!0}
        #     -> replace the second return with `return!0`. (Forcing
        #     remoteControlAutoEnableOn itself to true would be WRONG here: it
        #     would auto-connect even with the setting off.)
        #
        # (b) ~2.1.203-2.1.23x : the method carried the gate inline and the
        #     call site tested the setting itself:
        #       remoteControlAutoEnableOn(e){return e.ide_rc_auto_enable_gate===!0}
        #       ...this.remoteControlAutoEnableOn(g)&&g.remote_control_auto_enable&&...
        #     -> force the method to `return!0`.
        #
        # Builds ~2.1.181-2.1.201 had neither (NOT FOUND on those).
        # Only minified parameter names change between releases.
        "alts": [
            (
                re.compile(
                    r'\{if\((\w+)\.remote_control_auto_enable!==!0\)return!1;'
                    r'return \1\.remote_control_auto_on_by_default===!1'
                    r'\|\|\1\.ide_rc_auto_enable_gate===!0\}'
                ),
                lambda m: (
                    f'{{if({m.group(1)}.remote_control_auto_enable!==!0)'
                    f'return!1;return!0}}'
                ),
                re.compile(
                    r'\{if\(\w+\.remote_control_auto_enable!==!0\)'
                    r'return!1;return!0\}'
                ),
            ),
            (
                re.compile(
                    r'remoteControlAutoEnableOn\((\w+)\)\{'
                    r'return \1\.ide_rc_auto_enable_gate===!0\}'
                ),
                lambda m: (
                    f'remoteControlAutoEnableOn({m.group(1)}){{return!0}}'
                ),
                re.compile(
                    r'remoteControlAutoEnableOn\(\w+\)\{return!0\}'
                ),
            ),
        ],
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
        alts = p.get("alts") or [(p["find"], p["replace"], p["already"])]
        status = None
        for find, replace, _already in alts:
            patched, n = find.subn(replace, new)
            if n > 0:
                new = patched
                changed = True
                status = f"patched ({n})"
                break
        if status is None:
            if any(already.search(new) for _f, _r, already in alts):
                status = "already patched"
            else:
                status = "NOT FOUND (verify manually)"
        report["results"].append((p["name"], status))

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
