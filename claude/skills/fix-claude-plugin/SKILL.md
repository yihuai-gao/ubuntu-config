---
name: fix-claude-plugin
description: Re-apply all local patches to the Claude Code IDE extension (Cursor / VS Code) bundles — disable shift+tab mode cycling, make remoteControlAtStartup work, and force sessions to start in Auto permission mode (never bypass), and force every new / resumed session onto Fable 5.1 regardless of what other sessions switched to. Re-runnable after every extension update, since updates re-ship the bundles. Use when the user says "fix the claude plugin", "the plugin updated", remote control doesn't auto-start, shift+tab is back, sessions start in bypass permissions again, a new or resumed session starts on the wrong model (not Fable 5.1), or asks to re-apply the plugin patches.
---

# Fix Claude Plugin (Claude Code IDE extension patches)

Applies all local patches to the Claude Code **IDE extension** (Cursor / VS
Code native UI) bundles. These fix behaviors that have **no supported
setting** and can only be changed by patching the shipped JavaScript:
no shift+tab mode cycling, `remoteControlAtStartup` honored, sessions always
start in Auto permission mode, every new / resumed session runs on
**Fable 5.1** no matter what other sessions switched to, and the context-usage
pie in the input footer is always visible (not only past 50 % used).

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

### 4. Every new / resumed session runs on **Fable 5.1**  (`extension.js`)

Goal: switching a session to another model must never change what the *next*
new or resumed session starts on. Unpatched, the model of an IDE session is
resolved like this:

```
webview "launch_claude" carries NO model
  -> extension launchClaude() -> spawnClaude(..., model: void 0, ...)   // no --model flag
  -> CLI picks the model itself:
       new session    : ~/.claude/settings.json "model"
       --resume       : the model RECORDED IN THAT SESSION'S TRANSCRIPT
in-session picker ("set_model") -> writeUserSettingsAndPush(ch, {model})
  -> WRITES ~/.claude/settings.json + applyFlagSettings on the live session
```

So one session's pick was persisted to `settings.json` (leaking into every
later new session, and terminal `claude` sessions too), and resuming a session
brought back whatever model it last used. Verified on CLI 2.1.246: a haiku
session resumed without `--model` stays haiku; with `--model` the flag wins.

The patch has three pieces, all keyed on `FORCED_MODEL` at the top of
[patch.py](patch.py) (currently `claude-fable-5-1[1m]`, the 1M-context Fable 5.1;
any value the model picker / `claude --model` accepts works):

- **4a** `spawnClaude()` options `model:void 0` → `model:"<FORCED_MODEL>"`.
  The SDK turns that into `--model <value>`, which overrides both
  `settings.json` and the resumed transcript's model.
- **4b** `getModelSetting()` → early `return"<FORCED_MODEL>"`, so the model
  picker's starting selection agrees with 4a instead of echoing
  `settings.json`.
- **4c** `setModel` handler passes `flagsOnly=!0` to `writeUserSettingsAndPush`,
  so an in-session switch is applied live to *that* session only
  (`query.applyFlagSettings`) and is never written to `settings.json`. This is
  the same code path the webview's own `apply_settings {flagsOnly:true}` uses.
  Verified via the CLI control channel that `apply_flag_settings {model}`
  switches the model even when the process was spawned with `--model`.
  Two handler shapes are handled (`alts`): `return await write(...),{...}`
  (≤ 2.1.259) and `let J=await write(...);return{...applied:J}` (2.1.260+);
  the `writeUserSettingsAndPush(channel, settings, flagsOnly, scope)`
  signature is the same in both.

Notes:
- You can still switch models freely inside a session (picker or `/model`);
  it just no longer sticks. The terminal `claude` CLI is unaffected by 4a/4b
  and keeps reading `settings.json` — which 4c now keeps stable.
- To change the enforced model, edit `FORCED_MODEL` and re-run: the `find`
  regexes deliberately also match a previously forced literal, so the bundles
  are re-patched rather than reported "already patched".

### 5. Context-usage pie always visible  (`webview/index.js`)

The small orange pie next to the "Show command menu (/)" button (hover: "N %
of context remaining until auto-compact", click: compact) is the only
context-length readout in the native UI, and unpatched it is **hidden while
≥ 50 % of the context is still free**:

```js
let q=J>0?Math.min($/J*100,100):0, z=MV1!==null?MV1:q, U=100-z;   // J = usable window, U = % remaining
if(MV1===null){ if(J===0)return null; if(U>=50)return null }      // <- 5a drops the U>=50 return
```

Dropping that gate alone is not enough: the pie component only ships three
fixed SVG arcs, bucketed by `im0(p)` (`<62.5 → 50`, `<87 → 75`, else `99`), so
at 5 % used it would draw a half-filled circle. Hence two pieces:

- **5a** remove `if(U>=50)return null`. The `J===0` guard is kept — before
  the first `result` message the window size is unknown and 0 % would be a
  lie, so the pie appears after the first assistant turn.
- **5b** the pie draws a real arc for the actual percentage (`PIE_ARC_FN`
  in [patch.py](patch.py): 20×20 viewBox, r = 5 around (10,10), 12 o'clock
  clockwise — the same geometry as the shipped 50 % path) over an always-drawn
  faint background ring (`PIE_RING_PATH`). The bucket helpers are left in
  place as dead code. Tooltip and hover popup already show the exact
  percentages.

Notes:
- `J` is `contextWindow - maxOutputTokens - 13000` (the auto-compact
  threshold), so 100 % = "auto-compact now", not the raw model window.
- The arc helper is one literal string, so the `already` regex matches it
  verbatim; if you change `PIE_ARC_FN`, restore the bundles from
  `*.js.prepatch-bak` first (or the old helper stays in place and 5b reports
  NOT FOUND).

## After a plugin update

Just run the script again — the new version's bundles get patched. If a patch
reports `NOT FOUND`, the extension restructured that code: grep the target
bundle for the anchor strings (`key==="Tab"` + `shiftKey`;
`ide_rc_auto_enable_gate` / `remoteControlAutoEnableOn`;
`getInitialPermissionMode`; `,model:` next to `allowDangerouslySkipPermissions:`
in `spawnClaude`, `getModelSetting`, `async setModel(`; `% context used` /
`.usageContainer` and `{percentage:` + `style:{display:"block"}` for the pie),
locate the new form, and update that patch's
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
