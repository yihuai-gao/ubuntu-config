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

4. [extension.js] Every new / resumed session runs on FORCED_MODEL (Fable 5.1),
   regardless of what any other session switched to. Three pieces:
   4a. spawnClaude() passes `model:void 0` -> no --model flag -> the CLI picks
       the model itself: settings.json `model` for new sessions, and the
       model RECORDED IN THE TRANSCRIPT for --resume (verified on 2.1.246: a
       haiku session resumed without --model stays haiku). An explicit
       --model beats both, so we hardwire `model:"<FORCED_MODEL>"` there.
   4b. getModelSetting() (what the webview's model picker shows as the
       session's starting model) -> early `return"<FORCED_MODEL>"`, so the
       picker agrees with 4a instead of echoing settings.json.
   4c. The in-session model picker (`set_model` request) persisted the pick
       to ~/.claude/settings.json via writeUserSettingsAndPush(ch, {model})
       -- that write is how one session's choice leaked into every later
       session (and into terminal `claude` sessions). We pass flagsOnly=!0
       so the switch is applied live to that session only
       (query.applyFlagSettings) and never written to disk.
   To change the enforced model, edit FORCED_MODEL below and re-run: the
   `find` regexes deliberately also match a previously forced value.

5. [webview/index.js] Always show the context-usage indicator (the pie next
   to the "Show command menu" button). Unpatched it is hidden while >= 50%
   of the context is still free, and its pie only has three fixed arcs
   (50 / 75 / 99 % buckets), so merely un-hiding it would draw a
   half-filled circle at 5 % usage. Two pieces:
   5a. drop the `if(remaining>=50)return null` early return (the
       `contextWindow===0` guard is kept: before the first result the
       window size is unknown and there is nothing to show).
   5b. the pie draws a real arc for the actual percentage (12 o'clock,
       clockwise, r=5 on the 20x20 viewBox -- same geometry as the
       shipped 50 % path) over an always-drawn faint background ring.
       Tooltip / hover popup already print the exact percentages.

6. [webview/index.css + webview/index.js] Text in the AskUserQuestion
   prompt (question, option labels/descriptions) is selectable/copyable.
   The app root sets `user-select:none` and only whitelists a few areas
   (messages, dialogs) back to `user-select:text`; the question dialog's
   CSS module (`questionsContainer_<hash>` ...) is not among them, so
   nothing in the prompt can be selected or copied. Two pieces:
   6a. [index.css] append `.questionsContainer_<hash>{user-select:text}`
       next to the module's own rule (hash read from the existing rule).
   6b. [index.js] a drag-select that starts and ends inside one option
       still fires that option's onClick (= toggles it / advances to the
       next question). Guard both option onClick handlers with
       `if(window.getSelection()?.toString())return;`.

7. [extension.js + webview/index.js] Files sent with the SendUserFile tool
   (images, videos, audio) render INLINE in the conversation instead of a
   bare "2 files delivered to user" text result. The webview has no renderer
   for the tool at all (it falls back to the generic IN/OUT JSON card) and,
   even if it had, it could not load the file: the webview CSP allows
   `img-src` only (no `media-src`), and `localResourceRoots` is limited to
   the extension's own webview/ and resources/ folders. Three pieces:
   7a. [extension.js] CSP: add `media-src <cspSource>` next to img-src.
   7b. [extension.js] localResourceRoots: append `Uri.file("/")` so any
       file the extension host can read is servable to the webview
       (asWebviewUri-style https://<scheme>+<authority>.vscode-resource...
       URLs; works for local and Remote-SSH extension hosts alike).
   7c. [webview/index.js] a `SendUserFile` tool renderer (class
       CcSendUserFileTool) registered first in the tool-renderer registry.
       It builds each file's URL from the origin of the loaded index.js
       script (same authority / filesystem as the sent file) + the
       percent-encoded absolute path, and renders <img> / <video controls>
       / <audio controls> by extension (chips only for display:"attach" or
       other file types); every entry is a link that opens the file in the
       editor via the existing fileOpener. Absolute paths are taken from
       the tool result's "<path> -> file_uuid" lines (so relative inputs
       resolve), falling back to the tool input.

9. [webview/index.js] The pinned "latest prompt" strip at the top of the
   conversation always shows YOUR latest prompt, never a cross-session
   (peer) message. Messages another Claude session sends (the
   `<cross-session-message ...>` blocks) reach the webview as USER messages
   with `origin.kind === "peer"`, so unpatched each one opens a new "turn"
   and becomes that turn's sticky header (position:sticky user message),
   replacing your prompt in the strip. Two pieces:
   9a. the turn-start predicate (`Ox(msg)`: user message with text, not a
       tool-parented / synthetic one) returns false for peer-origin
       messages, so they are folded into the CURRENT turn (all three turn
       builders -- plain, focus view, focus-view folds -- share it).
   9b. the user-message component drops the stickyHeader class (and the
       click-to-scroll / screen-reader turn heading) for peer-origin
       messages, so a folded peer message cannot stick over the turn's own
       header. It still renders as a normal (non-sticky) user bubble in
       place.

Each patch matches by STRUCTURE (minified identifiers change every release;
API-shape names like `remoteControlAutoEnableOn` survive), using regex
backreferences so we only touch the intended code.
"""

import re
import sys
from pathlib import Path

# Patch 4: the model every new / resumed IDE session is spawned with
# (--model). Any value accepted by the model picker / `claude --model`
# works; the "[1m]" suffix selects the 1M-context variant.
FORCED_MODEL = "claude-fable-5-1[1m]"
_FM = re.escape(FORCED_MODEL)

# Patch 5b: SVG geometry for the context-usage pie (20x20 viewBox, circle
# r=5 centred at (10,10), arcs start at 12 o'clock and run clockwise -- the
# same geometry as the extension's own fixed 50/75/99 % paths).
PIE_RING_PATH = "M10 5A5 5 0 1 1 9.999 5"          # (almost) full circle
# Inline IIFE-free helper: percentage -> arc path. Kept on one line so the
# `already` regex can match it verbatim.
PIE_ARC_FN = (
    "(function(p){p=Math.max(0,Math.min(p,100));"
    'if(p>=99.9)return"' + PIE_RING_PATH + '";if(p<=0)return"";'
    "var a=p/50*Math.PI;"
    'return"M10 5A5 5 0 "+(p>50?1:0)+" 1 "'
    '+(10+5*Math.sin(a)).toFixed(3)+" "+(10-5*Math.cos(a)).toFixed(3)})'
)

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
#
# A patch may also supply `context`: a function(text) -> dict | None that
# resolves minified identifiers found ELSEWHERE in the bundle (e.g. the JSX
# factory, the tool-renderer base class). It runs before `find`; None means
# NOT FOUND, otherwise the dict is passed to `replace(match, ctx)`.
# ---------------------------------------------------------------------------

PATCHES = [
    {
        "name": "shift+tab cycles permission mode -> no-op",
        "target": "webview/index.js",
        # Original:  X.key==="Tab"&&X.shiftKey){X.preventDefault(),Y();return}
        # Y() is the permission-mode cycle call. We drop ",Y()" so shift+tab
        # is swallowed (preventDefault + return) and does nothing.
        # NB: minified identifiers may contain "$" (2.1.251 named the cycle
        # fn `$6`), so match [\w$]+ rather than \w+.
        "find": re.compile(
            r'(?P<p>[\w$]+)\.key==="Tab"&&(?P=p)\.shiftKey\)\{'
            r'(?P=p)\.preventDefault\(\),[\w$]+\(\);return\}'
        ),
        "replace": lambda m: (
            f'{m.group("p")}.key==="Tab"&&{m.group("p")}.shiftKey){{'
            f'{m.group("p")}.preventDefault();return}}'
        ),
        "already": re.compile(
            r'[\w$]+\.key==="Tab"&&([\w$]+)\.shiftKey\)\{\1\.preventDefault\(\);return\}'
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
        # Only minified parameter names change between releases (2.1.245 uses `$`,
        # hence `[\w$]+` for identifiers).
        "alts": [
            (
                re.compile(
                    r'\{if\(([\w$]+)\.remote_control_auto_enable!==!0\)return!1;'
                    r'return \1\.remote_control_auto_on_by_default===!1'
                    r'\|\|\1\.ide_rc_auto_enable_gate===!0\}'
                ),
                lambda m: (
                    f'{{if({m.group(1)}.remote_control_auto_enable!==!0)'
                    f'return!1;return!0}}'
                ),
                re.compile(
                    r'\{if\([\w$]+\.remote_control_auto_enable!==!0\)'
                    r'return!1;return!0\}'
                ),
            ),
            (
                re.compile(
                    r'remoteControlAutoEnableOn\(([\w$]+)\)\{'
                    r'return \1\.ide_rc_auto_enable_gate===!0\}'
                ),
                lambda m: (
                    f'remoteControlAutoEnableOn({m.group(1)}){{return!0}}'
                ),
                re.compile(
                    r'remoteControlAutoEnableOn\([\w$]+\)\{return!0\}'
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
    {
        "name": f'4a spawn: always pass --model {FORCED_MODEL} (new + resumed)',
        "target": "extension.js",
        # spawnClaude() SDK options: ...allowDangerouslySkipPermissions:W,model:X,stderr:...
        # X is launchClaude()'s model argument, which is always `void 0`.
        # The SDK turns a set `model` into `--model <value>` (verbatim, so
        # "[1m]" survives). Also matches a previously forced *different*
        # literal so editing FORCED_MODEL re-patches instead of "already".
        "find": re.compile(
            r'(allowDangerouslySkipPermissions:[\w$]+,model:)'
            r'(?!"' + _FM + r'")(?:[\w$]+|"[^"]*")(,stderr:)'
        ),
        "replace": lambda m: f'{m.group(1)}"{FORCED_MODEL}"{m.group(2)}',
        "already": re.compile(
            r'allowDangerouslySkipPermissions:[\w$]+,model:"' + _FM + r'",stderr:'
        ),
    },
    {
        "name": f'4b getModelSetting -> "{FORCED_MODEL}" (picker matches spawn)',
        "target": "extension.js",
        # getModelSetting(){return this.cachedClaudeSettings?.effective?.model
        #   ??this.cachedUserSettings?.model??"default"}
        # Early return, original body left as dead code (as in patch 3).
        "find": re.compile(
            r'getModelSetting\(\)\{(?:return"(?!' + _FM + r'")[^"]*";)?'
            r'(?=return this\.)'
        ),
        "replace": f'getModelSetting(){{return"{FORCED_MODEL}";',
        "already": re.compile(r'getModelSetting\(\)\{return"' + _FM + r'";'),
    },
    {
        "name": "4c in-session model switch -> session-only (no settings.json write)",
        "target": "extension.js",
        # async setModel($,Q){return await this.writeUserSettingsAndPush($,
        #   {model:Q.value==="default"?null:Q.value}),{type:"set_model_response"}}
        # writeUserSettingsAndPush(channel, settings, flagsOnly): with
        # flagsOnly truthy it skips the ~/.claude/settings.json write and only
        # calls query.applyFlagSettings(settings) on the live session -- the
        # same path the webview's own `apply_settings {flagsOnly:true}` uses.
        # Two shapes (writeUserSettingsAndPush(channel, settings, flagsOnly,
        # scope) is unchanged in both -- `!flagsOnly` still gates the disk write):
        #   <= 2.1.259: async setModel($,Q){return await this.writeUserSettingsAndPush($,
        #                 {model:...}),{type:"set_model_response"}}
        #   >= 2.1.260: async setModel($,Q){let J=await this.writeUserSettingsAndPush($,
        #                 {model:...});return{type:"set_model_response",...J!==void 0&&{applied:J}}}
        #   >= 2.1.274: same, with a brace-free guard in front of the `let`:
        #               {if(typeof Q!=="object"||...)throw Error("set_model: malformed request");let J=...
        "alts": [
            (
                re.compile(
                    r'(async setModel\(([\w$]+),([\w$]+)\)\{return await '
                    r'this\.writeUserSettingsAndPush\(\2,'
                    r'\{model:\3\.value==="default"\?null:\3\.value\})\)'
                ),
                lambda m: f'{m.group(1)},!0)',
                re.compile(
                    r'async setModel\(([\w$]+),([\w$]+)\)\{return await '
                    r'this\.writeUserSettingsAndPush\(\1,'
                    r'\{model:\2\.value==="default"\?null:\2\.value\},!0\)'
                ),
            ),
            (
                re.compile(
                    r'(async setModel\(([\w$]+),([\w$]+)\)\{(?:[^{}]*?;)?let [\w$]+=await '
                    r'this\.writeUserSettingsAndPush\(\2,'
                    r'\{model:\3\.value==="default"\?null:\3\.value\})\)'
                ),
                lambda m: f'{m.group(1)},!0)',
                re.compile(
                    r'async setModel\(([\w$]+),([\w$]+)\)\{(?:[^{}]*?;)?let [\w$]+=await '
                    r'this\.writeUserSettingsAndPush\(\1,'
                    r'\{model:\2\.value==="default"\?null:\2\.value\},!0\)'
                ),
            ),
        ],
    },
    {
        "name": "5a context-usage pie: show below 50% used",
        "target": "webview/index.js",
        # Usage component body (2.1.220 .. 2.1.247, only identifiers differ):
        #   let q=J>0?Math.min($/J*100,100):0,z=MV1!==null?MV1:q,U=100-z;
        #   if(MV1===null){if(J===0)return null;if(U>=50)return null}
        #   return E("div",{className:lW.usageContainer,...
        # J = usable context window, U = % remaining. Drop only the U>=50
        # early return; keep the J===0 guard (window size unknown yet).
        # 2.1.274 split the component: the gate now sits in a wrapper that
        # returns the inner component instead of the div:
        #   if(DF1===null){if(J===0)return null;if(G>=50)return null}
        #   return F(N45,{percentageUsed:Q,onCompact:Z,...
        "find": re.compile(
            r'(if\([\w$]+===0\)return null);if\([\w$]+>=50\)return null'
            r'(\}return [\w$]+\((?:"div",\{className:[\w$]+\.usageContainer'
            r'|[\w$]+,\{percentageUsed:))'
        ),
        "replace": lambda m: f"{m.group(1)}{m.group(2)}",
        "already": re.compile(
            r'if\([\w$]+===0\)return null'
            r'\}return [\w$]+\((?:"div",\{className:[\w$]+\.usageContainer'
            r'|[\w$]+,\{percentageUsed:)'
        ),
    },
    {
        "name": "5b context-usage pie: true arc for any percentage",
        "target": "webview/index.js",
        # Pie component:
        #   function d90({percentage:$,className:J}){let Y=im0($),X=sm0[Y];
        #     return E("svg",{...,style:{display:"block"},children:[
        #       X&&j("path",{d:X,stroke:"currentColor",strokeOpacity:"0.15",...}),
        #       j("path",{d:rm0[Y],stroke:"var(--app-claude-clay-button-orange)",...})]})}
        # im0() buckets the percentage into 50/75/99 and rm0/sm0 hold one
        # fixed arc per bucket (sm0[99] is null -> no background ring). We
        # always draw a full background ring and compute the filled arc from
        # the real percentage. The bucket helpers are left in place (dead).
        "find": re.compile(
            r'(\{percentage:([\w$]+),className:[\w$]+\}\)\{'
            r'let ([\w$]+)=[\w$]+\(\2\),([\w$]+)=[\w$]+\[\3\];'
            r'return [\w$]+\("svg",\{[^{}]*?style:\{display:"block"\},children:\[)'
            r'\4&&([\w$]+)\("path",\{d:\4,'
            r'(stroke:"currentColor",strokeOpacity:"[\d.]+",strokeWidth:"[\d.]+",'
            r'strokeLinecap:"round"\}\),\5\("path",\{d:)[\w$]+\[\3\],'
        ),
        "replace": lambda m: (
            f'{m.group(1)}{m.group(5)}("path",{{d:"{PIE_RING_PATH}",'
            f'{m.group(6)}{PIE_ARC_FN}({m.group(2)}),'
        ),
        "already": re.compile(
            r'\{percentage:([\w$]+),className:[\w$]+\}\)\{.{0,800}?'
            r'\("path",\{d:' + re.escape(PIE_ARC_FN) + r'\(\1\),'
        ),
    },
    {
        "name": "6a AskUserQuestion prompt: text selectable (user-select:text)",
        "target": "webview/index.css",
        # Root: `.root_<h>{...user-select:none...}`; only a whitelist of
        # classes opts back in with `user-select:text` and the question
        # dialog module (`.questionsContainer_<hash>`, `.option_<hash>`,
        # `.optionLabel_<hash>` ...) is not on it. Append one rule right
        # after the module's own questionsContainer rule, reusing its hash.
        # (`(?<!>)`: 2.1.286 adds `.withPreview_<h>>.questionsContainer_<h>{...}`
        # layout rules; only the module's standalone rule gets the companion.)
        "find": re.compile(
            r'((?<!>)\.questionsContainer_([\w-]+)\{(?!user-select:text\})[^{}]*\})'
            r'(?!\.questionsContainer_\2\{user-select:text\})'
        ),
        "replace": lambda m: (
            f'{m.group(1)}.questionsContainer_{m.group(2)}{{user-select:text}}'
        ),
        "already": re.compile(
            r'\.questionsContainer_([\w-]+)\{[^{}]*\}'
            r'\.questionsContainer_\1\{user-select:text\}'
        ),
    },
    {
        "name": "6b AskUserQuestion prompt: drag-select does not click the option",
        "target": "webview/index.js",
        # Option rows (2.1.220 .. 2.1.260, identifiers differ):
        #   tabIndex:0,role:O.multiSelect?"checkbox":"radio","aria-checked":R(L.label),
        #   onClick:()=>N(O.question,L.label),onKeyDown:...
        # and the trailing "Other" row with `R("Other")` / `N(O.question,"Other")`.
        # A mouse drag that starts and ends inside the row fires `click` on
        # it, so with 6a a text selection would toggle the option; skip the
        # handler while a non-empty selection exists (a plain click always
        # collapses the selection on mousedown first, so it still works).
        #
        # 2.1.286 moved the row into one shared component (also used, without
        # `onSelect`, for the read-only review of answered questions):
        #   function am({multiSelect:$,...,onSelect:q,...}){let B=q===void 0;
        #     return R("div",{...,tabIndex:B?void 0:0,role:$?"checkbox":"radio",
        #       "aria-checked":X,"aria-disabled":B?!0:void 0,"aria-describedby":G,
        #       onClick:q,onMouseEnter:U,...,onKeyDown:q&&((K)=>{...q()}),...
        # Callers pass `onSelect:()=>f(p.question,label)` (no event argument),
        # so the guard wraps `q` once, in the component.
        "alts": [
            (
                re.compile(
                    r'(tabIndex:0,role:([\w$]+)\.multiSelect\?"checkbox":"radio",'
                    r'"aria-checked":[\w$]+\((?:[\w$]+\.label|"Other")\),onClick:)'
                    r'\(\)=>([\w$]+\(\2\.question,(?:[\w$]+\.label|"Other")\)),'
                ),
                lambda m: (
                    f'{m.group(1)}()=>{{if(window.getSelection()?.toString())return;'
                    f'{m.group(3)}}},'
                ),
                re.compile(
                    r'"aria-checked":[\w$]+\((?:[\w$]+\.label|"Other")\),onClick:\(\)=>'
                    r'\{if\(window\.getSelection\(\)\?\.toString\(\)\)return;'
                ),
            ),
            (
                re.compile(
                    r'(role:[\w$]+\?"checkbox":"radio","aria-checked":[\w$]+,'
                    r'"aria-disabled":[\w$]+\?!0:void 0,(?:"aria-describedby":[\w$]+,)?'
                    r'onClick:)([\w$]+)(?=,onMouseEnter:)'
                ),
                lambda m: (
                    f'{m.group(1)}{m.group(2)}&&(()=>{{'
                    f'if(window.getSelection()?.toString())return;{m.group(2)}()}})'
                ),
                re.compile(
                    r'role:[\w$]+\?"checkbox":"radio","aria-checked":[\w$]+,'
                    r'"aria-disabled":[\w$]+\?!0:void 0,(?:"aria-describedby":[\w$]+,)?'
                    r'onClick:([\w$]+)&&\(\(\)=>\{'
                    r'if\(window\.getSelection\(\)\?\.toString\(\)\)return;\1\(\)\}\)'
                ),
            ),
        ],
    },
    {
        "name": "9a peer (cross-session) messages do not start a new turn",
        "target": "webview/index.js",
        # Turn-start predicate (2.1.260):
        #   function Ox($){if($?.type!=="user")return!1;
        #     if($.isEmpty||$.parentToolUseId||$.isSynthetic)return!1;
        #     ... has a text block -> !0 }
        # Used by every turn builder (plain list, focus view, focus folds), so
        # one early `return!1` for origin.kind==="peer" folds cross-session
        # messages into the current turn everywhere. `origin` is copied from
        # the SDK user message (transcript `origin:{kind:"peer",...}`).
        "find": re.compile(
            r'(function [\w$]+\(([\w$]+)\)\{if\(\2\?\.type!=="user"\)return!1;'
            r'if\(\2\.isEmpty\|\|\2\.parentToolUseId\|\|\2\.isSynthetic\)return!1;)'
            r'(?!if\(\2\.origin\?\.kind==="peer"\)return!1;)'
        ),
        "replace": lambda m: (
            f'{m.group(1)}if({m.group(2)}.origin?.kind==="peer")return!1;'
        ),
        "already": re.compile(
            r'function [\w$]+\(([\w$]+)\)\{if\(\1\?\.type!=="user"\)return!1;'
            r'if\(\1\.isEmpty\|\|\1\.parentToolUseId\|\|\1\.isSynthetic\)return!1;'
            r'if\(\1\.origin\?\.kind==="peer"\)return!1;'
        ),
    },
    {
        "name": "9b peer (cross-session) messages never become the sticky header",
        "target": "webview/index.js",
        # User-message component (2.1.260):
        #   function({session:J,message:Z,...}){let V=H1(null),H=[...Z.content].reverse(),
        #     B=H.map((R)=>xz(R.content)),W="";for(...){...}
        #     let K=B.find((R)=>R?.type==="ideDiagnostics"),A=B.some((R)=>R?.type==="text"),
        #     j=!K&&A,P=q$0(j),...
        # 2.1.278 adds a `held` prop and a second text test:
        #     P=K.some(...)||U41(Z.content),j=!H&&!M&&P,w=hG0(j),...
        # 2.1.286 appends a read-only term: O=!U&&!M&&N&&!w,_=yK0(O),...
        # so any `&&` chain of optionally negated identifiers is accepted (the
        # `,p=fn(j),` tail pins the end of the chain).
        #   ... className:`${a0.message} ${w} ${j?a0.stickyHeader:""} ...`
        # `j` = "this message is the turn header" (sticky class, click-to-
        # scroll handlers, screen-reader heading). A peer message folded into
        # a turn by 9a must not stick over that turn's real header.
        "find": re.compile(
            r'(let [\w$]+=[\w$]+\(null\),[\w$]+=\[\.\.\.(?P<msg>[\w$]+)\.content\]'
            r'\.reverse\(\),.{0,1500}?'
            r',(?P<j>[\w$]+)=!?[\w$]+(?:&&!?[\w$]+)+)'
            r'(?!&&(?P=msg)\.origin\?\.kind!=="peer")'
            r'(?P<tail>,(?P<p>[\w$]+)=[\w$]+\((?P=j)\),)'
        ),
        "replace": lambda m: (
            f'{m.group(1)}&&{m.group("msg")}.origin?.kind!=="peer"{m.group("tail")}'
        ),
        "already": re.compile(
            r'=\[\.\.\.([\w$]+)\.content\]\.reverse\(\),.{0,1500}?'
            r',([\w$]+)=!?[\w$]+(?:&&!?[\w$]+)+&&\1\.origin\?\.kind!=="peer",[\w$]+=[\w$]+\(\2\),'
        ),
    },
    {
        "name": "10 New session opens in the active editor group (never a split)",
        "target": "extension.js",
        # createPanel(sessionId, prompt, viewColumn, ...) picks the column
        # when the caller passes none (sidebar "New session",
        # claude-vscode.editor.open / window.open):
        #   K=B4.ViewColumn.Beside;
        #   let V=sp$();                         // a tab group holding ONLY Claude panels
        #   if(V)K=V.viewColumn;
        #   else K=this.findUnusedColumn(),W=!0  // <- first column without any tab = SPLIT
        # (2.1.220 inlines the group search instead of sp$(); same tail.
        #  2.1.274: `else G=this.findUnusedColumn(),W=G!==H4.ViewColumn.Beside}`
        #  -- the flag is derived from the result instead of a literal !0.)
        # The Claude-only-group preference is kept; only the split fallback
        # becomes ViewColumn.Active (the group you are in), startedInNewColumn
        # = false. findUnusedColumn() has no other caller.
        #
        # 2.1.282+ dropped findUnusedColumn(). The column is now
        #   let q=k1.window.tabGroups.all.map(BC),
        #       H=BH1(q)??UH1(q,[...this.panelComms.keys()].flatMap(...));
        #                    // a group that already holds Claude tabs (active one
        #                    // first), or a lone empty group, or a live panel's column
        #   if(!H){H=await this.startClaudeGroup();   // <- newGroupRight/Below = SPLIT
        #          let Z=$!==void 0?this.sessionPanels.get($):void 0; ...}
        #   K=H?.viewColumn??k1.ViewColumn.Active,G=H?.startsClaudeGroup??!1
        # so a split only happens when no group holds a Claude tab yet. Dropping
        # the startClaudeGroup() call leaves H undefined -> ViewColumn.Active,
        # startedInNewColumn false (the active group is not locked either).
        # startClaudeGroup() has no other caller.
        "alts": [
            (
                re.compile(
                    r'(?P<v>[\w$]+)=(?P<ns>[\w$]+)\.ViewColumn\.Beside;(?P<mid>let [\w$]+=.{0,400}?)'
                    r'else (?P=v)=this\.findUnusedColumn\(\),(?P<w>[\w$]+)='
                    r'(?:!0|(?P=v)!==(?P=ns)\.ViewColumn\.Beside)\}'
                ),
                lambda m: (
                    f'{m.group("v")}={m.group("ns")}.ViewColumn.Beside;{m.group("mid")}'
                    f'else {m.group("v")}={m.group("ns")}.ViewColumn.Active,{m.group("w")}=!1}}'
                ),
                re.compile(
                    r'([\w$]+)=([\w$]+)\.ViewColumn\.Beside;let [\w$]+=.{0,400}?'
                    r'else \1=\2\.ViewColumn\.Active,[\w$]+=!1\}'
                ),
            ),
            (
                re.compile(
                    r'(if\(!(?P<h>[\w$]+)\)\{(?P=h)=)await this\.startClaudeGroup\(\)'
                    r'(?P<tail>;let [\w$]+=[\w$]+!==void 0\?this\.sessionPanels\.get\()'
                ),
                lambda m: f'{m.group(1)}void 0{m.group("tail")}',
                re.compile(
                    r'if\(!([\w$]+)\)\{\1=void 0'
                    r';let [\w$]+=[\w$]+!==void 0\?this\.sessionPanels\.get\('
                ),
            ),
        ],
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
        bak = js.with_name(js.name + ".prepatch-bak")
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
                print(f"  -> written (backup: {js.with_name(js.name + '.prepatch-bak')})")

    if not any_found:
        return 1
    print(
        "\nReload the IDE window (Cmd/Ctrl+Shift+P -> 'Reload Window') "
        "for changes to take effect."
    )
    return 2 if any_notfound else 0


if __name__ == "__main__":
    sys.exit(main())
