---
name: fix-claude-plugin
description: Re-apply all local patches to the Claude Code IDE extension (Cursor / VS Code) bundles — disable shift+tab mode cycling, make remoteControlAtStartup work, and force sessions to start in Auto permission mode (never bypass), force every new / resumed session onto Fable 5.1 regardless of what other sessions switched to, make the AskUserQuestion prompt (multiple-choice options) text selectable / copyable, render files sent with SendUserFile (images / videos / audio) inline in the conversation, and make clicked file links (mp4, png, pdf ...) open in the VS Code editor (Media Preview) instead of failing silently or landing in a blank Simple Browser tab over Remote-SSH. Re-runnable after every extension update, since updates re-ship the bundles. Use when the user says "fix the claude plugin", "the plugin updated", remote control doesn't auto-start, shift+tab is back, sessions start in bypass permissions again, a new or resumed session starts on the wrong model (not Fable 5.1), cannot copy / select text in the options prompt (AskUserQuestion), images / videos sent to the user do not show in the plugin, clicking a file link does nothing / opens a blank tab, or asks to re-apply the plugin patches.
---

# Fix Claude Plugin (Claude Code IDE extension patches)

Applies all local patches to the Claude Code **IDE extension** (Cursor / VS
Code native UI) bundles. These fix behaviors that have **no supported
setting** and can only be changed by patching the shipped JavaScript:
no shift+tab mode cycling, `remoteControlAtStartup` honored, sessions always
start in Auto permission mode, every new / resumed session runs on
**Fable 5.1** no matter what other sessions switched to, the context-usage
pie in the input footer is always visible (not only past 50 % used), text
in the AskUserQuestion options prompt can be selected and copied, files sent
with SendUserFile (images / videos / audio) render inline, clicked file
links open in the VS Code editor (Media Preview for mp4 / png / pdf), and the
pinned "latest prompt" strip at the top of the conversation always shows
**your** latest prompt (never a cross-session message from another Claude
session), and the Session Manager's **New session** button opens the new
tab in the editor group you are in instead of splitting a new column beside it.

Supersedes and merges the retired `fix-keyboard-shortcuts` and
`fix-remote-control-startup` skills.

## How to run

```bash
python3 ~/.claude/skills/fix-claude-plugin/patch.py                   # patches 1-6, 9, 10
python3 ~/.claude/skills/fix-claude-plugin/patch7_send_user_file.py   # patches 7-8 (--check = dry run)
```

Then **reload the IDE window** (Command Palette → "Reload Window").

> Patches 7-8 live in the separate [patch7_send_user_file.py](patch7_send_user_file.py)
> for now: on 2026-09-06 the auto-mode classifier refused the edits that
> would merge them into `patch.py` (it needs a small `context` hook in
> `patch_file()` — the file's header docstring explains the 3-step merge).
> The script imports `find_bundles()` from `patch.py`, uses the same
> `*.prepatch-bak` backups and the same output format, and is idempotent.
> Merge it when a session is allowed to edit `patch.py`.

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
  (≤ 2.1.259) and `let J=await write(...);return{...applied:J}` (2.1.260+;
  from 2.1.274 a brace-free `if(typeof Q!=="object"…)throw Error("set_model:
  malformed request");` guard precedes the `let`, which the regex skips);
  the `writeUserSettingsAndPush(channel, settings, flagsOnly, scope)`
  signature is the same in all of them.

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
  lie, so the pie appears after the first assistant turn. (2.1.274 split the
  component: the gate lives in a wrapper that ends in
  `return F(N45,{percentageUsed:Q,…})` instead of the `usageContainer` div;
  the regex accepts both tails.)
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

### 6. AskUserQuestion prompt: text selectable / copyable  (`webview/index.css` + `webview/index.js`)

Symptom: while Claude is prompting with multiple-choice options
(AskUserQuestion), nothing in the prompt — question, option labels,
descriptions — can be selected with the mouse or copied. Keyboard is not the
problem (ctrl+c passes through the dialog's key handlers); it is CSS: the app
root is `user-select:none` and only a whitelist of classes (messages,
permission dialogs, …) opts back in with `user-select:text`. The question
dialog's CSS module (`questionsContainer_<hash>`, `option_<hash>`,
`optionLabel_<hash>` …) is not on that list, so it inherits `none`.

- **6a** `index.css`: append `.questionsContainer_<hash>{user-select:text}`
  right after the module's own `questionsContainer` rule, reusing the hash
  it finds there (`hONcXw` in 2.1.220–2.1.286; the regex does not depend on
  it). Everything inside the prompt (question text, options, descriptions)
  inherits from that container. Only the standalone rule gets the companion
  (2.1.286 also has `.withPreview_<h>>.questionsContainer_<h>{…}` layout
  rules, which the regex skips).
- **6b** `index.js`: a mouse drag that starts and ends inside one option row
  still fires that row's `click`, which would toggle the option (and, for
  single-select, advance to the next question). Both option `onClick`
  handlers (the mapped options and the trailing "Other" row) get
  `if(window.getSelection()?.toString())return;` in front. A plain click
  still works: the browser collapses any selection on mousedown before
  `click` fires. 2.1.286 moved the row into one shared component
  (`function am({…,onSelect:q,…})` with `onClick:q`, also used read-only for
  the review of answered questions); there the guard wraps `q` once:
  `onClick:q&&(()=>{if(window.getSelection()?.toString())return;q()})`.

Notes:
- The tab labels in the navigation bar are `<button>`s and stay
  unselectable (browser default); copy from the question body instead.
- `index.css` is backed up to `index.css.prepatch-bak` (backups are named
  `<file>.prepatch-bak`, so the JS and CSS backups do not collide).

### 7. Files sent with SendUserFile render inline  (`extension.js` + `webview/index.js`)

Symptom: `SendUserFile` (the CLI tool that "sends" an image / video / report
to the user) shows up in the native UI as a generic tool card whose OUT is
the text `2 files delivered to user. <path> → file_uuid: …` — nothing to look
at, nothing to click. Three independent reasons, hence three pieces:

- The webview has **no renderer for the tool** (tool renderers are classes
  extending a base `z2` — `name` / `header()` / `body(context,input,result,
  progress)` — looked up by name in a registry function `BG(name,context)`;
  unknown names fall back to the generic IN/OUT JSON card).
- The webview **CSP has no `media-src`** (`default-src 'none'`, only
  `img-src ${cspSource} data:`), so a `<video>`/`<audio>` could not load.
- **`localResourceRoots`** on every webview/panel is limited to the
  extension's own `webview/` and `resources/` folders, so a resource
  request for anything under `$HOME` or `/tmp` is refused.

Pieces (all in [patch7_send_user_file.py](patch7_send_user_file.py)):

- **7a** `extension.js` `getHtmlForWebview()`: `img-src ${cspSource} data:`
  → `…; media-src ${cspSource}`.
- **7b** `extension.js`: the 4 `localResourceRoots:[…webview,…resources]`
  sites get `,X.Uri.file("/")` appended. The extension host already reads
  any of these files for the webview (Read tool, diffs, …), so this widens
  nothing the webview could not already obtain.
- **7c** `webview/index.js`: a `CcSendUserFileTool` renderer
  (`name="SendUserFile"`) is inserted right before the registry function and
  prepended to its list. The base class, JSX factories and CSS module are
  resolved from the base class's own source (`context` hook in the script),
  so identifiers may change across builds. It builds each file URL as
  `<origin of the loaded webview/index.js>` + percent-encoded absolute path
  (the same `https://<scheme>+<authority>.vscode-resource.vscode-cdn.net/…`
  authority `asWebviewUri` produces — the script and the sent file live on
  the same filesystem, local or Remote-SSH) and renders `<img>` (click →
  open in editor), `<video controls>`, `<audio controls>` by extension;
  `display:"attach"` or other types → name link only. Absolute paths come
  from the result's `<path> → file_uuid:` lines (so relative inputs
  resolve), falling back to the tool input. The caption is shown above.

Notes:
- The tool's structured `tool_use_result` (media types, sizes) never reaches
  the webview — only the API `tool_result` block does — hence the
  extension-based type sniffing.
- The webview resource loader returns whole files (no range requests), so
  a very large video downloads fully before it plays.
- Chunks already in a session re-render after Reload Window, so a file
  sent before patching shows up inline afterwards.
- 2.1.286 gave the base class's `body()` a fifth argument (replay / denial
  metadata). The context regex accepts the optional parameter and the
  renderer forwards it to `super.body()`; on older builds it is `undefined`.

### 8. Clicked file links open in the editor  (`extension.js`)

Symptom: a markdown link like `[file-653.mp4](/abs/path/file-653.mp4)` in an
assistant message does nothing when clicked (text files work). Over
Remote-SSH a `http://localhost:PORT/…` link to a local http server instead
opens VS Code's Simple Browser tab, which stays **blank** for an mp4.

Path of a click: webview `a` component → `Bj0(ev, href, fileOpener)` →
`RC(href)` (accepts absolute / relative paths and anything with an
extension, plus `:L12-L20` / `#L12` suffixes) → `fileOpener.open()` →
extension `openFile()`, which ends in

```js
_$.window.showTextDocument(X).then((z)=>{ …reveal range / searchText… })
```

`showTextDocument()` only knows text documents: for an mp4 / png / pdf it
**rejects** ("binary or unsupported text encoding") and nothing has a
rejection handler, so the click is swallowed. The patch rewrites that call:

```js
if(/\.(png|jpe?g|gif|webp|bmp|ico|avif|svg|mp4|webm|mov|m4v|ogv|mkv|mp3|wav|ogg|oga|m4a|flac|aac|pdf)$/i.test(X.fsPath)){
  _$.commands.executeCommand("vscode.open",X);return}                  // media -> built-in Media Preview / image / pdf editor
_$.window.showTextDocument(X).catch(()=>{_$.commands.executeCommand("vscode.open",X)})
  .then((z)=>{if(!z)return; …original body… })                          // any other rejection -> vscode.open ("Open Anyway")
```

`vscode.open` is what the `code <path>` CLI does through Remote-SSH: the
file opens in the connected VS Code window, on the local side.

Notes:
- 2.1.274 calls `showTextDocument(W,G)` with a second argument (`{preview:!1}`
  for pinned tabs); the regex accepts an optional second identifier and keeps
  it on the rewritten call. The media fast path ignores it (media open in
  preview mode).
- Only **file paths** can be routed this way; a `http://localhost:…` URL
  cannot be mapped back to a file. Link deliverables as absolute paths (and
  send images / videos with SendUserFile) — see memory rule 65.
- Directories were already handled (`revealInExplorer`) and are untouched.

### 9. Pinned "latest prompt" strip = your latest prompt, never a cross-session message  (`webview/index.js`)

Symptom: the sticky strip pinned at the top of the conversation (the user
message of the current "turn", `position:sticky`) shows the last
`<cross-session-message from="uds:/tmp/cc-socks/…">` block sent by another
Claude session instead of the prompt you typed. Those peer messages arrive as
plain **user** messages (transcript: `type:"user"`, `isMeta:true`,
`origin:{kind:"peer",from:…,name:…}`), and the webview copies `origin` onto
its message objects. A turn starts at every user message that has a text
block and is neither tool-parented nor synthetic (`Ox(msg)`), so each peer
message opened a new turn and became its sticky header.

- **9a** `Ox(msg)` gets an early `return!1` for `msg.origin?.kind==="peer"`.
  All three turn builders (plain list, focus view, focus-view folds) call
  it, so peer messages are folded into the turn they interrupt everywhere.
- **9b** the user-message component computes `j` = "this message is the turn
  header" (sticky class, click-to-scroll handlers, screen-reader heading);
  `&&Z.origin?.kind!=="peer"` is appended so a folded peer message cannot
  stick over the turn's real header. It still renders in place as a normal
  (non-sticky) user bubble. (≤ 2.1.260 has `j=!K&&A`; 2.1.278 adds a `held`
  prop, `j=!H&&!M&&P`; 2.1.286 appends a read-only term, `O=!U&&!M&&N&&!w`
  — the regex accepts any `&&` chain of optionally negated identifiers.)

Notes:
- Keyed on the `origin` metadata, not on the `<cross-session-message>` text,
  so a prompt of yours that merely quotes such a block is unaffected.
- Task notifications (`origin.kind==="task-notification"`) already have
  their own handling and are untouched.
- Cursor's 2.1.201 / 2.1.207 builds predate peer messaging and report NOT
  FOUND for both pieces; that is expected.
- 2.1.286 also classifies a well-formed `<cross-session-message>` text block
  as its own `peerMessage` content type (not `text`), so such a message no
  longer starts a turn by itself; the patch stays as the `origin`-keyed
  backstop for blocks that parser rejects.

### 10. "New session" opens in the active editor group, never a split  (`extension.js`)

Symptom: pressing **+ New session** in the Session Manager sidebar (and the
`claude-vscode.editor.open` / `claude-vscode.window.open` commands) opens
the new Claude tab in a *new* editor column beside the current one. The
column is chosen in `createPanel(sessionId, prompt, viewColumn, …)` when the
caller passes no column:

```js
K=B4.ViewColumn.Beside;
let V=sp$();                          // a tab group whose tabs are ALL Claude panels
if(V)K=V.viewColumn;                  // reuse it
else K=this.findUnusedColumn(),W=!0   // <- first column with no tab at all = SPLIT
```

(2.1.220 inlines the group search instead of `sp$()`; the tail is identical.
2.1.274 derives the flag from the result instead of a literal:
`else G=this.findUnusedColumn(),W=G!==H4.ViewColumn.Beside}` — the regex
accepts both tails and the replacement is the same.)
As soon as a Claude tab shares its group with a file tab there is no
"Claude-only" group, so every new session split the editor. The patch keeps
the Claude-only-group preference and replaces only the fallback:
`findUnusedColumn()` → `ViewColumn.Active` (the group you are in),
`startedInNewColumn` → false. `findUnusedColumn()` has no other caller.

**2.1.282+** dropped `findUnusedColumn()`; the split moved into a helper:

```js
let q=k1.window.tabGroups.all.map(BC),
    H=BH1(q)??UH1(q,[…live panel columns…]);   // a group that already holds Claude tabs
                                                // (active one first), a lone empty group,
                                                // or a live Claude panel's column
if(!H){H=await this.startClaudeGroup(); …}      // <- newGroupRight / newGroupBelow = SPLIT
K=H?.viewColumn??k1.ViewColumn.Active,G=H?.startsClaudeGroup??!1
```

Upstream now reuses any group that holds a Claude tab, so the split is left
only for the first Claude tab in a window. The patch replaces the
`await this.startClaudeGroup()` call with `void 0`, which falls through to
`ViewColumn.Active` and `startedInNewColumn` false (so the group you are in
is not locked either). `startClaudeGroup()` has no other caller.

Notes:
- The primary-editor command and "reopen last closed session" pass an
  explicit column and are untouched.
- Drag the tab to another group if you do want a split; that never
  triggers this code.

## After a plugin update

Just run the script again — the new version's bundles get patched. If a patch
reports `NOT FOUND`, the extension restructured that code: grep the target
bundle for the anchor strings (`key==="Tab"` + `shiftKey`;
`ide_rc_auto_enable_gate` / `remoteControlAutoEnableOn`;
`getInitialPermissionMode`; `,model:` next to `allowDangerouslySkipPermissions:`
in `spawnClaude`, `getModelSetting`, `async setModel(`; `% context used` /
`.usageContainer` and `{percentage:` + `style:{display:"block"}` for the pie;
`.questionsContainer_` in `index.css` and `"aria-checked":` + `onClick:()=>`
in `index.js` for the question prompt; `img-src ${` + `cspSource`,
`localResourceRoots:[` and `window.showTextDocument(` … `.then((` +
`?.searchText` in `extension.js`, `{hidden=!1;header(` (renderer base
class) and `.fileOpener),` inside a `let X=[new …]` registry list in
`index.js` for the sent-file / link patches; `.isEmpty||` … `.isSynthetic)return!1;`
(turn-start predicate) and `.some((` … `?.type==="text"),` followed by
`=!` … `&&` (the user-message `j` flag) for the latest-prompt strip;
`this.findUnusedColumn(),` after a `.ViewColumn.Beside;` — or, 2.1.282+,
`await this.startClaudeGroup()` — for the new-session column),
locate the new form, and update that patch's
`find`/`already` regexes in [patch.py](patch.py) — or add it as another
variant in that patch's `alts` list, so older builds keep working. If an anchor string is gone
entirely, Anthropic may have shipped the behavior properly (e.g. rollout
complete) — test unpatched before re-adding.

## Rollback

Restore any bundle from its `*.prepatch-bak` sibling (`index.js.prepatch-bak`,
`extension.js.prepatch-bak`, `index.css.prepatch-bak`) and reload the window.

## Alternatives (no patching)

- Terminal mode (`"claudeCode.useTerminal": true`) runs the real CLI REPL,
  which honors `~/.claude/keybindings.json` and `remoteControlAtStartup`
  natively — at the cost of the native webview UI.
- Manual per-session: `/remote-control` to connect, mode picker to leave
  bypass.
