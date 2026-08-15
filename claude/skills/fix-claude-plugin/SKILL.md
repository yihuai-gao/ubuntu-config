---
name: fix-claude-plugin
description: Re-apply all local patches to the Claude Code IDE extension (Cursor / VS Code) bundles — disable shift+tab mode cycling, make remoteControlAtStartup work, and force sessions to start in Auto permission mode (never bypass). Re-runnable after every extension update, since updates re-ship the bundles. Use when the user says "fix the claude plugin", "the plugin updated", remote control doesn't auto-start, shift+tab is back, sessions start in bypass permissions again, or asks to re-apply the plugin patches.
---

# Fix Claude Plugin (Claude Code IDE extension patches)

Applies all local patches to the Claude Code **IDE extension** (Cursor / VS
Code native UI) bundles. These fix behaviors that have **no supported
setting** and can only be changed by patching the shipped JavaScript.

Supersedes and merges the retired `fix-keyboard-shortcuts` and
`fix-remote-control-startup` skills.

## How to run

```bash
python3 ~/.claude/skills/fix-claude-plugin/patch.py
```

Then **reload the IDE window** (Command Palette → "Reload Window").

The script finds every installed `anthropic.claude-code-*` extension under
`~/.cursor-server`, `~/.cursor`, `~/.vscode-server`, `~/.vscode` (and
insiders), matches each patch by **structure** (regex with backreferences —
survives minifier renames across versions), backs each file up once to
`*.js.prepatch-bak`, and is **idempotent** (safe to run repeatedly). Output
per patch: `patched`, `already patched`, or `NOT FOUND` (= the extension
restructured that code; see "After a plugin update" below).

## The patches

### 1. shift+tab "cycle permission mode" → no-op  (`webview/index.js`)

The native UI's input is a webview with keydown handlers compiled into
`webview/index.js`. It does not read `~/.claude/keybindings.json` (terminal
CLI only) and the handler is not a VS Code command, so it cannot be remapped.
The patch drops the cycle call, leaving shift+tab swallowed.

> Related but NOT patched: **ctrl+j** = insert newline (left intact);
> **ctrl/cmd+escape** = focus input is the registered command
> `claude-vscode.focus` and is remappable normally in VS Code keybindings.

### 2. `remoteControlAtStartup` honored  (`extension.js`)

Auto-enable is fully implemented, but double-gated: your setting **and** the
GrowthBook rollout kill-switch `ide_rc_auto_enable_gate` (the CLI's
`tengu_ide_rc_auto_enable`, default false). Until Anthropic flips that gate for
your account, the setting is silently ignored in the IDE (terminal CLI sessions
are unaffected). The patch kills **only the gate**, keeping the
`remote_control_auto_enable` check, so auto-enable still strictly follows
`remoteControlAtStartup` in `~/.claude/settings.json`.

Two code shapes exist; `patch.py` handles both.

**2.1.233+** — the gate lives in a module-level helper that also folds in the
setting check, and the call site no longer tests the setting separately:

```js
remoteControlAutoEnableOn(e){return aTe(e)}
function aTe(e){
  if(e.remote_control_auto_enable!==!0) return!1;      // <- your setting (kept)
  return e.remote_control_auto_on_by_default===!1
      || e.ide_rc_auto_enable_gate===!0                // <- GB rollout gate (patched to return!0)
}
```

Here forcing `remoteControlAutoEnableOn` itself to `return!0` would be **wrong**
— it would auto-connect even with the setting off. Only the second `return` is
replaced.

**~2.1.203–2.1.23x** — the gate was inline in the method, and the call site
tested the setting itself:

```js
remoteControlAutoEnableOn(e){return e.ide_rc_auto_enable_gate===!0}   // -> return!0
// call site: this.remoteControlAutoEnableOn(g) && g.remote_control_auto_enable && ...
```

> Version note: builds ~2.1.181–2.1.201 had neither form (patch reports NOT
> FOUND on those). Cursor pins the extension via OpenVSX and may lag behind the
> VS Marketplace — if stuck on a pre-2.1.203 build, side-load a newer targeted
> VSIX from `https://open-vsx.org/api/Anthropic/claude-code/<target>/<version>/file/...`
> (e.g. `linux-x64`) via Command Palette → "Extensions: Install from VSIX".

Prerequisites if it "doesn't work": `"remoteControlAtStartup": true` in
`~/.claude/settings.json`, signed in with a claude.ai account (not API key),
CLI ≥ 2.1.51, org toggle enabled on Team/Enterprise plans.

### 3. Sessions always start in **Auto** permission mode  (`extension.js`)

Unpatched resolution order in `getInitialPermissionMode()`:

```js
claudeCode.initialPermissionMode setting   // workspace/user VS Code setting
?? globalState "defaultPermissionMode"     // <- persisted LAST-USED mode
?? "default"
```

The persisted last-used mode is why sessions kept starting in
**bypassPermissions** after it was used once. The patch inserts an early
`return"auto"`, so every new session starts in Auto ("approve actions that
pass a safety check, pause for anything risky").

Notes:
- You can still switch modes freely inside a session; the choice just no
  longer leaks into the next session's starting mode.
- If Auto mode is unavailable (model doesn't support it, `disableAutoMode`
  policy, or the `tengu_auto_mode_state` gate), the webview automatically
  falls back to "default" (Manual) — never bypass.
- This intentionally overrides the `claudeCode.initialPermissionMode` VS Code
  setting (whose enum doesn't offer "auto" anyway). To change the enforced
  mode, edit the `replace` string of patch 3 in [patch.py](patch.py).

## After a plugin update

Just run the script again — the new version's bundles get patched. If a patch
reports `NOT FOUND`, the extension restructured that code: grep the target
bundle for the anchor strings (`key==="Tab"` + `shiftKey`;
`ide_rc_auto_enable_gate` / `remoteControlAutoEnableOn`;
`getInitialPermissionMode`), locate the new form, and update that patch's
`find`/`already` regexes in [patch.py](patch.py) — or add it as another
variant in that patch's `alts` list, so older builds keep working. If an anchor string is gone
entirely, Anthropic may have shipped the behavior properly (e.g. rollout
complete) — test unpatched before re-adding.

## Rollback

Restore any bundle from its `*.js.prepatch-bak` sibling and reload the window.

## Alternatives (no patching)

- Terminal mode (`"claudeCode.useTerminal": true`) runs the real CLI REPL,
  which honors `~/.claude/keybindings.json` and `remoteControlAtStartup`
  natively — at the cost of the native webview UI.
- Manual per-session: `/remote-control` to connect, mode picker to leave
  bypass.
