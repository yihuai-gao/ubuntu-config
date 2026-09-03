#!/usr/bin/env python3
"""Patch installed Codex IDE extensions for session-oriented editor tabs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

EXTENSION_ROOTS = (
    "~/.cursor-server/extensions",
    "~/.cursor/extensions",
    "~/.vscode-server/extensions",
    "~/.vscode/extensions",
    "~/.vscode-server-insiders/extensions",
    "~/.vscode-insiders/extensions",
)
EXTENSION_GLOB = "openai.chatgpt-*"
PATCHED_MAIN = "./out/extension-patched.js"
KEYBINDING = {"command": "chatgpt.newCodexPanel", "key": "ctrl+shift+k"}
WEBVIEW_ASSET_GLOB = "webview/assets/app-initial-*.js"
SIDEBAR_TAB_MARKER = "/*fix-codex-plugin:sidebar-conversation-tab*/"
IDENTIFIER_PATTERN = r"[A-Za-z_$][\w$]*"
TARGET_PATTERN = (
    r'async createNewPanel\(\)\{(?:let|const)\s+'
    r'[A-Za-z_$][\w$]*=[A-Za-z_$][\w$]*\("/extension/panel/new"\)'
    r'(?!\.with\()'
)
NAVIGATION_CONTEXT_PATTERN = re.compile(
    rf"if\((?P<initial>{IDENTIFIER_PATTERN})\)\{{"
    rf"(?P<bridge>{IDENTIFIER_PATTERN})\.dispatchMessage\("
    rf"`navigate-in-new-editor-tab`,"
    rf"(?P<options>{IDENTIFIER_PATTERN})\?\.replaceCurrentEditor\?"
    rf"\{{path:(?P<path>{IDENTIFIER_PATTERN}),replaceCurrentEditor:!0\}}:"
    rf"\{{path:(?P=path)\}}\);return\}}",
)
SIDEBAR_ROW_PATTERN = re.compile(
    rf"(?P<target>L1r\((?P<store>{IDENTIFIER_PATTERN}),"
    rf"tm\((?P<conversation>{IDENTIFIER_PATTERN})\),"
    rf"(?P<host>{IDENTIFIER_PATTERN})\?\?`local`\),"
    rf"(?P<before>{IDENTIFIER_PATTERN})\?\.\(\),"
    rf"(?P<navigate>{IDENTIFIER_PATTERN})\((?P=store),(?P=conversation),"
    rf"(?P=host)!=null&&(?P=host)!==`local`\?(?P=host):void 0,"
    rf"(?P<state>{IDENTIFIER_PATTERN})==null\?void 0:"
    rf"\{{state:(?P=state)\}}\))",
)
THREAD_NAME_NOTIFICATION_PATTERN = (
    rf"(onRawNotification:(?P<notification>{IDENTIFIER_PATTERN})=>\{{"
    rf"let\{{method:(?P<method>{IDENTIFIER_PATTERN}),"
    rf"params:(?P<params>{IDENTIFIER_PATTERN})\}}=(?P=notification);)"
    rf"(?P<broadcast>this\.broadcastToAllViews\(\{{"
    rf'type:"mcp-notification",hostId:"local",method:(?P=method),'
    rf"params:(?P=params)\}}\))"
)
WEBVIEW_CAPTURE_PATTERN = (
    rf'(async handleMessage\((?P<webview>{IDENTIFIER_PATTERN}),'
    rf'(?P<message>{IDENTIFIER_PATTERN})\)\{{switch\('
    rf'(?P=message)\.type\)\{{case"ready":break;[\s\S]*?)'
    rf'case"browser-use-session-route-capture":'
    rf'(?P<remaining>case"browser-use-cursor-arrived":'
    rf'case"browser-use-session-activity-ended":'
    rf'case"browser-sidebar-owner-sync":break;)'
)
PANEL_STATE_PATTERN = (
    rf'(?P<set>this\.editorPanels\.set\((?P<panel>{IDENTIFIER_PATTERN}),'
    rf'\{{ready:!1,pendingMessages:\[\],initialRoute:[\s\S]{{0,180}}?\}}\)),'
    rf'(?P<conversation>{IDENTIFIER_PATTERN})!=null&&'
    rf'this\.registerOnDidDisposeForWebviewPanel\('
    rf'(?P=panel),(?P=conversation)\)'
)
PREVIEW_TITLE_PATTERN = (
    rf'(?P<prefix>this\.previewLoader\.fetchConversationPreviews\(\)'
    rf'\.then\((?P<previews>{IDENTIFIER_PATTERN})=>\{{let '
    rf'(?P<preview>{IDENTIFIER_PATTERN})=(?P=previews)\.get\('
    rf'(?P<conversation>{IDENTIFIER_PATTERN})\);)'
    rf'this\.isPanelAlive\((?P<panel>{IDENTIFIER_PATTERN})\)&&'
    rf'\((?P=panel)\.title=(?P<formatter>{IDENTIFIER_PATTERN})\('
    rf'(?P=preview)\)\)\}}\)'
)
NAVIGATE_TAB_PATTERN = (
    rf'case"navigate-in-new-editor-tab":\{{let '
    rf'(?P<uri>{IDENTIFIER_PATTERN})=(?P<factory>{IDENTIFIER_PATTERN})\('
    rf'(?P<message>{IDENTIFIER_PATTERN})\.path\);if\(!'
    rf'(?P=message)\.replaceCurrentEditor\)\{{'
    rf'(?P<vscode>{IDENTIFIER_PATTERN})\.commands\.executeCommand\('
    rf'"vscode\.open",(?P=uri)\);break\}}'
)
PERMANENT_NEW_TAB_PATTERN = (
    rf'(?P<open>async createNewPanel\(\)\{{[\s\S]{{0,350}}?await '
    rf'(?P<vscode>{IDENTIFIER_PATTERN})\.commands\.executeCommand\('
    rf'"vscode\.openWith",[\s\S]{{0,260}}?preview:!1\}}\))\}}'
)
WRAPPER_SOURCE = r'''"use strict";

const fs = require("node:fs");
const Module = require("node:module");
const path = require("node:path");

const extensionPath = path.join(__dirname, "extension.js");
const source = fs.readFileSync(extensionPath, "utf8");
const createNewPanelPattern =
  /(async createNewPanel\(\)\{(?:let|const)\s+[A-Za-z_$][\w$]*=[A-Za-z_$][\w$]*\("\/extension\/panel\/new"\))(?!\.with\()/g;
const threadNameNotificationPattern =
  /(onRawNotification:([A-Za-z_$][\w$]*)=>\{let\{method:([A-Za-z_$][\w$]*),params:([A-Za-z_$][\w$]*)\}=\2;)(this\.broadcastToAllViews\(\{type:"mcp-notification",hostId:"local",method:\3,params:\4\}\))/g;
const webviewCapturePattern =
  /(async handleMessage\(([A-Za-z_$][\w$]*),([A-Za-z_$][\w$]*)\)\{switch\(\3\.type\)\{case"ready":break;[\s\S]*?)case"browser-use-session-route-capture":(case"browser-use-cursor-arrived":case"browser-use-session-activity-ended":case"browser-sidebar-owner-sync":break;)/g;
const panelStatePattern =
  /(this\.editorPanels\.set\(([A-Za-z_$][\w$]*),\{ready:!1,pendingMessages:\[\],initialRoute:[\s\S]{0,180}?\}\)),([A-Za-z_$][\w$]*)!=null&&this\.registerOnDidDisposeForWebviewPanel\(\2,\3\)/g;
const previewTitlePattern =
  /(this\.previewLoader\.fetchConversationPreviews\(\)\.then\(([A-Za-z_$][\w$]*)=>\{let ([A-Za-z_$][\w$]*)=\2\.get\(([A-Za-z_$][\w$]*)\);)this\.isPanelAlive\(([A-Za-z_$][\w$]*)\)&&\(\5\.title=([A-Za-z_$][\w$]*)\(\3\)\)\}\)/g;
const navigateTabPattern =
  /case"navigate-in-new-editor-tab":\{let ([A-Za-z_$][\w$]*)=([A-Za-z_$][\w$]*)\(([A-Za-z_$][\w$]*)\.path\);if\(!\3\.replaceCurrentEditor\)\{([A-Za-z_$][\w$]*)\.commands\.executeCommand\("vscode\.open",\1\);break\}/g;
const permanentNewTabPattern =
  /(async createNewPanel\(\)\{[\s\S]{0,350}?await ([A-Za-z_$][\w$]*)\.commands\.executeCommand\("vscode\.openWith",[\s\S]{0,260}?preview:!1\}\))\}/g;
const createNewPanelMatches = source.match(createNewPanelPattern) ?? [];
const threadNameNotificationMatches =
  source.match(threadNameNotificationPattern) ?? [];
const webviewCaptureMatches = source.match(webviewCapturePattern) ?? [];
const panelStateMatches = source.match(panelStatePattern) ?? [];
const previewTitleMatches = source.match(previewTitlePattern) ?? [];
const navigateTabMatches = source.match(navigateTabPattern) ?? [];
const permanentNewTabMatches = source.match(permanentNewTabPattern) ?? [];

if (createNewPanelMatches.length !== 1) {
  throw new Error(
    `Unable to apply the new-Codex-tab patch: expected one target, found ${createNewPanelMatches.length}.`,
  );
}
if (threadNameNotificationMatches.length !== 1) {
  throw new Error(
    `Unable to apply the Codex-tab-title patch: expected one target, found ${threadNameNotificationMatches.length}.`,
  );
}
for (const [label, matches] of [
  ["conversation-to-panel", webviewCaptureMatches],
  ["restored-panel state", panelStateMatches],
  ["conversation-preview title", previewTitleMatches],
  ["sidebar permanent tab", navigateTabMatches],
  ["new permanent tab", permanentNewTabMatches],
]) {
  if (matches.length !== 1) {
    throw new Error(
      `Unable to apply the ${label} patch: expected one target, found ${matches.length}.`,
    );
  }
}

const sessionTitleHelpers = String.raw`
const __fixCodexFs = require("node:fs");
const __fixCodexOs = require("node:os");
const __fixCodexPath = require("node:path");
const __fixCodexSessionIndexPath = __fixCodexPath.join(
  process.env.CODEX_HOME || __fixCodexPath.join(__fixCodexOs.homedir(), ".codex"),
  "session_index.jsonl",
);
function __fixCodexNormalizeTitle(value) {
  if (typeof value !== "string") return null;
  const title = value.trim();
  if (title.length === 0) return null;
  return title.length > 30 ? title.slice(0, 30) + "…" : title;
}
function __fixCodexSessionTitle(conversationId) {
  if (typeof conversationId !== "string" || conversationId.length === 0) {
    return null;
  }
  try {
    const lines = __fixCodexFs
      .readFileSync(__fixCodexSessionIndexPath, "utf8")
      .split(/\r?\n/);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      if (lines[index].length === 0) continue;
      try {
        const entry = JSON.parse(lines[index]);
        if (entry?.id === conversationId) {
          return __fixCodexNormalizeTitle(entry.thread_name);
        }
      } catch {
        // Ignore a partial or malformed JSONL record and keep searching.
      }
    }
  } catch {
    // The extension's native preview title remains the fallback.
  }
  return null;
}
function __fixCodexRenderPanelTitle(panel, state) {
  const title = state.fixCodexSessionTitle || "Codex";
  panel.title = (state.fixCodexTaskDone ? "● " : "") + title;
}
function __fixCodexTrackPanel(owner, panel, conversationId, fallbackTitle) {
  const state = owner.editorPanels.get(panel);
  if (state == null) return;
  if (typeof conversationId === "string" && conversationId.length > 0) {
    state.fixCodexConversationId = conversationId;
  }
  const title =
    __fixCodexSessionTitle(conversationId) ||
    __fixCodexNormalizeTitle(fallbackTitle) ||
    __fixCodexNormalizeTitle(panel.title);
  if (title != null) state.fixCodexSessionTitle = title.replace(/^● /, "");
  __fixCodexRenderPanelTitle(panel, state);
}
function __fixCodexUpdatePanels(owner, conversationId, title, taskDone) {
  for (const [panel, state] of owner.editorPanels) {
    const route = state.initialRoute?.split(/[?#]/, 1)[0];
    if (
      state.fixCodexConversationId !== conversationId &&
      route !== "/local/" + conversationId
    ) {
      continue;
    }
    if (!owner.isPanelAlive(panel)) continue;
    state.fixCodexConversationId = conversationId;
    const normalizedTitle =
      __fixCodexNormalizeTitle(title) || __fixCodexSessionTitle(conversationId);
    if (normalizedTitle != null) state.fixCodexSessionTitle = normalizedTitle;
    if (typeof taskDone === "boolean") state.fixCodexTaskDone = taskDone;
    __fixCodexRenderPanelTitle(panel, state);
  }
}
`;

const uniqueFragment =
  '.with({fragment:`${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`})';
const patchedSource = sessionTitleHelpers + source
  .replace(
    permanentNewTabPattern,
    (_match, open, vscode) =>
      `${open};await ${vscode}.commands.executeCommand("workbench.action.keepEditor")}`,
  )
  .replace(createNewPanelPattern, `$1${uniqueFragment}`)
  .replace(
    navigateTabPattern,
    (_match, uri, factory, message, vscode) =>
      `case"navigate-in-new-editor-tab":{let ${uri}=${factory}(${message}.path);` +
      `if(!${message}.replaceCurrentEditor){` +
      `await ${vscode}.commands.executeCommand("vscode.open",${uri},{preview:!1});` +
      `await ${vscode}.commands.executeCommand("workbench.action.keepEditor");break}`,
  )
  .replace(
    panelStatePattern,
    (_match, setPanelState, panel, conversation) =>
      `${setPanelState},__fixCodexTrackPanel(this,${panel},${conversation},null),` +
      `${conversation}!=null&&this.registerOnDidDisposeForWebviewPanel(${panel},${conversation})`,
  )
  .replace(
    previewTitlePattern,
    (_match, prefix, _previews, preview, conversation, panel) =>
      `${prefix}this.isPanelAlive(${panel})&&` +
      `__fixCodexTrackPanel(this,${panel},${conversation},${preview})})`,
  )
  .replace(
    webviewCapturePattern,
    (_match, prefix, webview, message, remaining) =>
      `${prefix}case"browser-use-session-route-capture":{` +
      `let fixCodexPanel=this.findPanelByWebview(${webview});` +
      `if(fixCodexPanel&&typeof ${message}.conversationId==="string")` +
      `__fixCodexTrackPanel(this,fixCodexPanel,${message}.conversationId,null);` +
      `break}${remaining}`,
  )
  .replace(
    threadNameNotificationPattern,
    (_match, prefix, _notification, method, params, broadcast) => {
      const updateTitleAndStatus =
        `if(${method}==="thread/name/updated"&&typeof ${params}?.threadId==="string"&&typeof ${params}?.threadName==="string"){` +
        `__fixCodexUpdatePanels(this,${params}.threadId,${params}.threadName)}` +
        `else if(${method}==="turn/started"&&typeof ${params}?.threadId==="string")` +
        `__fixCodexUpdatePanels(this,${params}.threadId,null,!1);` +
        `else if(${method}==="turn/completed"&&typeof ${params}?.threadId==="string")` +
        `__fixCodexUpdatePanels(this,${params}.threadId,null,!0);`;
      return `${prefix}${updateTitleAndStatus}${broadcast}`;
    },
  );
const patchedModule = new Module(extensionPath, module.parent);
patchedModule.filename = extensionPath;
patchedModule.paths = module.paths;
patchedModule._compile(patchedSource, extensionPath);

module.exports = patchedModule.exports;
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Give new and selected Codex conversations their own IDE editor tabs."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify installed extensions without modifying them",
    )
    return parser.parse_args()


def find_extensions() -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root_text in EXTENSION_ROOTS:
        root = Path(root_text).expanduser()
        if not root.is_dir():
            continue
        for extension_dir in sorted(root.glob(EXTENSION_GLOB)):
            resolved = extension_dir.resolve()
            if resolved in seen:
                continue
            if (extension_dir / "package.json").is_file() and (
                extension_dir / "out/extension.js"
            ).is_file():
                seen.add(resolved)
                found.append(extension_dir)
    return found


def load_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest is not a JSON object: {path}")
    return manifest


def has_keybinding(manifest: dict[str, object]) -> bool:
    contributes = manifest.get("contributes")
    if not isinstance(contributes, dict):
        return False
    keybindings = contributes.get("keybindings")
    if not isinstance(keybindings, list):
        return False
    return any(
        isinstance(entry, dict)
        and entry.get("command") == KEYBINDING["command"]
        and entry.get("key") == KEYBINDING["key"]
        for entry in keybindings
    )


def add_keybinding(manifest: dict[str, object]) -> None:
    contributes = manifest.get("contributes")
    if not isinstance(contributes, dict):
        raise ValueError("Extension manifest has no contributes object")
    keybindings = contributes.get("keybindings")
    if not isinstance(keybindings, list):
        raise ValueError("Extension manifest has no keybindings list")
    if not has_keybinding(manifest):
        keybindings.insert(0, KEYBINDING.copy())


def target_count(bundle_path: Path) -> int:
    source = bundle_path.read_text(encoding="utf-8", errors="surrogatepass")
    return len(re.findall(TARGET_PATTERN, source))


def thread_name_target_count(bundle_path: Path) -> int:
    source = bundle_path.read_text(encoding="utf-8", errors="surrogatepass")
    return len(re.findall(THREAD_NAME_NOTIFICATION_PATTERN, source))


def loader_target_counts(bundle_path: Path) -> dict[str, int]:
    source = bundle_path.read_text(encoding="utf-8", errors="surrogatepass")
    patterns = {
        "createNewPanel": TARGET_PATTERN,
        "thread name/status notification": THREAD_NAME_NOTIFICATION_PATTERN,
        "conversation-to-panel capture": WEBVIEW_CAPTURE_PATTERN,
        "restored-panel state": PANEL_STATE_PATTERN,
        "conversation-preview title": PREVIEW_TITLE_PATTERN,
        "sidebar permanent tab": NAVIGATE_TAB_PATTERN,
        "new permanent tab": PERMANENT_NEW_TAB_PATTERN,
    }
    return {
        label: len(re.findall(pattern, source))
        for label, pattern in patterns.items()
    }


def locate_sidebar_asset(
    extension_dir: Path,
) -> tuple[Path, str, re.Match[str], re.Match[str]]:
    candidates: list[tuple[Path, str, list[re.Match[str]], list[re.Match[str]]]] = []
    asset_paths = sorted(extension_dir.glob(WEBVIEW_ASSET_GLOB))
    for asset_path in asset_paths:
        source = asset_path.read_text(
            encoding="utf-8",
            errors="surrogatepass",
        )
        context_matches = list(NAVIGATION_CONTEXT_PATTERN.finditer(source))
        row_matches = list(SIDEBAR_ROW_PATTERN.finditer(source))
        if SIDEBAR_TAB_MARKER in source or context_matches or row_matches:
            candidates.append(
                (asset_path, source, context_matches, row_matches),
            )

    if len(candidates) != 1:
        raise RuntimeError(
            "expected one Codex webview asset containing the sidebar navigation "
            f"targets, found {len(candidates)} across {len(asset_paths)} assets",
        )

    asset_path, source, context_matches, row_matches = candidates[0]
    if len(context_matches) != 1 or len(row_matches) != 1:
        raise RuntimeError(
            f"expected one navigation context and one local conversation row in "
            f"{asset_path}, found {len(context_matches)} and {len(row_matches)}",
        )
    return asset_path, source, context_matches[0], row_matches[0]


def add_sidebar_tab_patch(
    source: str,
    context_match: re.Match[str],
    row_match: re.Match[str],
) -> str:
    if SIDEBAR_TAB_MARKER in source:
        return source

    initial_route = context_match.group("initial")
    bridge = context_match.group("bridge")
    conversation_id = row_match.group("conversation")
    injection = (
        f",{SIDEBAR_TAB_MARKER}{initial_route}==null&&"
        f"{bridge}.dispatchMessage(`navigate-in-new-editor-tab`,"
        f"{{path:`/local/${{{conversation_id}}}`}})"
    )
    return source[: row_match.end()] + injection + source[row_match.end() :]


def check_extension(extension_dir: Path) -> list[str]:
    manifest_path = extension_dir / "package.json"
    wrapper_path = extension_dir / "out/extension-patched.js"
    bundle_path = extension_dir / "out/extension.js"
    manifest = load_manifest(manifest_path)
    problems: list[str] = []

    for label, count in loader_target_counts(bundle_path).items():
        if count != 1:
            problems.append(f"{label} targets: {count} (expected 1)")
    if manifest.get("main") != PATCHED_MAIN:
        problems.append(f"main is {manifest.get('main')!r}")
    if not has_keybinding(manifest):
        problems.append("Ctrl+Shift+K keybinding is missing")
    if not wrapper_path.is_file():
        problems.append("patch loader is missing")
    elif wrapper_path.read_text(encoding="utf-8") != WRAPPER_SOURCE:
        problems.append("patch loader differs from the skill template")
    try:
        _, sidebar_source, _, _ = locate_sidebar_asset(extension_dir)
        if SIDEBAR_TAB_MARKER not in sidebar_source:
            problems.append("sidebar conversation tab patch is missing")
    except RuntimeError as error:
        problems.append(str(error))
    return problems


def patch_extension(extension_dir: Path) -> str:
    manifest_path = extension_dir / "package.json"
    wrapper_path = extension_dir / "out/extension-patched.js"
    bundle_path = extension_dir / "out/extension.js"
    for label, count in loader_target_counts(bundle_path).items():
        if count != 1:
            raise RuntimeError(
                f"expected one {label} target in {bundle_path}, found {count}",
            )

    sidebar_path, sidebar_source, context_match, row_match = locate_sidebar_asset(
        extension_dir,
    )
    patched_sidebar_source = add_sidebar_tab_patch(
        sidebar_source,
        context_match,
        row_match,
    )

    manifest = load_manifest(manifest_path)
    manifest_changed = manifest.get("main") != PATCHED_MAIN or not has_keybinding(
        manifest,
    )
    wrapper_changed = (
        not wrapper_path.is_file()
        or wrapper_path.read_text(encoding="utf-8") != WRAPPER_SOURCE
    )
    sidebar_changed = patched_sidebar_source != sidebar_source
    if not manifest_changed and not wrapper_changed and not sidebar_changed:
        return "already patched"

    if wrapper_changed:
        wrapper_path.write_text(WRAPPER_SOURCE, encoding="utf-8")

    if manifest_changed:
        backup_path = manifest_path.with_name(
            "package.json.fix-codex-plugin.bak",
        )
        if not backup_path.exists():
            shutil.copy2(manifest_path, backup_path)
        manifest["main"] = PATCHED_MAIN
        add_keybinding(manifest)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent="\t") + "\n",
            encoding="utf-8",
        )

    if sidebar_changed:
        backup_path = sidebar_path.with_name(
            sidebar_path.name + ".fix-codex-plugin.bak",
        )
        if not backup_path.exists():
            shutil.copy2(sidebar_path, backup_path)
        sidebar_path.write_text(
            patched_sidebar_source,
            encoding="utf-8",
            errors="surrogatepass",
        )

    return "patched"


def main() -> int:
    args = parse_args()
    extensions = find_extensions()
    if not extensions:
        print("No installed openai.chatgpt extension found.", file=sys.stderr)
        print("Searched: " + ", ".join(EXTENSION_ROOTS), file=sys.stderr)
        return 1

    failures = 0
    for extension_dir in extensions:
        try:
            if args.check:
                problems = check_extension(extension_dir)
                if problems:
                    failures += 1
                    print(f"✗ {extension_dir}")
                    for problem in problems:
                        print(f"  - {problem}")
                else:
                    print(f"✔ {extension_dir}: patched")
            else:
                print(f"✔ {extension_dir}: {patch_extension(extension_dir)}")
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            failures += 1
            print(f"✗ {extension_dir}: {error}", file=sys.stderr)

    if not args.check and failures == 0:
        print(
            "Reload the IDE window (Command Palette -> Developer: Reload Window) "
            "to activate the patch.",
        )
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
