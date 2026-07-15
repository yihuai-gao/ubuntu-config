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

Auto-enable is fully implemented (verified in 2.1.207), but double-gated. On
each session's init response the host runs:

```js
this.remoteControlAutoEnableOn(g)          // = g.ide_rc_auto_enable_gate===true  <- GB rollout gate
  && g.remote_control_auto_enable          // <- your remoteControlAtStartup setting
  && channel.remoteControlState==="disconnected"
  && !isTeleportedSession
) this.toggleRemoteControl(channel, true)
```

with `remoteControlAutoEnableOn(e){return e.ide_rc_auto_enable_gate===!0}`.
`ide_rc_auto_enable_gate` is the CLI's `tengu_ide_rc_auto_enable` GrowthBook
staged-rollout kill-switch (default false). Until Anthropic flips it for your
account, the setting is silently ignored in the IDE (terminal CLI sessions are
unaffected). The patch makes the gate method `return!0`; the
`remote_control_auto_enable` check (your setting) stays, so auto-enable still
strictly follows `remoteControlAtStartup` in `~/.claude/settings.json`.

> Version note: builds ~2.1.181–2.1.201 briefly removed `remoteControlAutoEnableOn`
> entirely (patch reports NOT FOUND on those); 2.1.203+ restored it. Cursor
> pins the extension via OpenVSX and may lag behind the VS Marketplace — if
> stuck on a pre-2.1.203 build, side-load a newer targeted VSIX from
> `https://open-vsx.org/api/Anthropic/claude-code/<target>/<version>/file/...`
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
`find`/`already` regexes in [patch.py](patch.py). If an anchor string is gone
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
