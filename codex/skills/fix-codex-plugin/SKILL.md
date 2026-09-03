---
name: fix-codex-plugin
description: Reapply the local OpenAI Codex VS Code or Cursor extension patch so new and selected conversations open in permanent editor tabs, tabs show session names, and a completion dot appears after a turn finishes. Use when any of these tab behaviors regress or after the Codex IDE extension updates; do not use for Codex CLI sessions.
---

# Fix Codex Plugin

Patch every installed `openai.chatgpt-*` IDE extension so Codex conversations
behave like editor sessions:

- `Ctrl+Shift+K` opens an independent new-agent tab.
- Selecting an existing local conversation in the Codex sidebar keeps the
  sidebar selection behavior and also opens or reveals that conversation in
  an editor tab.
- New and selected conversation tabs are permanent immediately, rather than
  italic preview tabs that another file can replace.
- Conversation editor tabs show the generated or user-renamed session name
  instead of remaining labeled `Codex`.
- A `●` prefix appears when the conversation's current turn completes and is
  cleared when the next turn starts.

Run:

```bash
python3 ~/.codex/skills/fix-codex-plugin/scripts/patch.py
```

Then reload the IDE window with **Developer: Reload Window**.

The script searches VS Code, VS Code Insiders, Cursor, and their remote-server
extension directories. It adds the `chatgpt.newCodexPanel` keybinding and uses
a loader that gives `/extension/panel/new` a unique URI fragment on every
invocation. The fragment makes VS Code create a new custom-editor document,
while Codex still receives the unchanged route. After opening a new or
selected conversation, it explicitly invokes VS Code's keep-editor action so
the tab is pinned even when a custom editor ignores the initial
`preview: false` option.

It also patches the local-conversation row handler in the generated Codex
webview asset. The handler retains its normal in-sidebar navigation, then asks
the extension host to open `/local/<conversation-id>` with the existing Codex
conversation editor. VS Code reveals an already-open tab for that conversation
instead of duplicating it.

The extension loader associates each webview with the conversation ID emitted
by `browser-use-session-route-capture`. For restored `/local/<conversation-id>`
documents it records the ID immediately and reads the newest matching
`thread_name` from `~/.codex/session_index.jsonl`, using the native preview as
fallback. This makes existing tabs receive their actual names even when the
extension's summary provider returns no preview.

The loader also listens for `thread/name/updated`, `turn/started`, and
`turn/completed` app-server notifications. It updates only the matching editor
panel, applies the extension's 30-character title limit, removes the
completion dot on a new turn, and prefixes `●` when that turn completes.
Generated titles and manual renames therefore stay in sync without changing
the sidebar title flow.

The operation is idempotent. Run it again after each extension update because
updates install a new versioned extension directory. Use `--check` to verify
all installed copies without changing them:

```bash
python3 ~/.codex/skills/fix-codex-plugin/scripts/patch.py --check
```

If the script reports that any loader, navigation-context, or local
conversation-row target is not unique, stop and inspect the updated extension
bundles; do not patch a guessed location. Update the structural patterns in
`scripts/patch.py` only after confirming the updated implementations still
open `/extension/panel/new`, propagate the thread name and turn lifecycle
notifications, capture each webview's conversation ID, and open
`/local/<conversation-id>` respectively.

For rollback, restore `package.json.fix-codex-plugin.bak` when present and
remove `out/extension-patched.js`. Also restore the generated webview asset
from its adjacent `*.fix-codex-plugin.bak` file, or reinstall the affected IDE
extension.
