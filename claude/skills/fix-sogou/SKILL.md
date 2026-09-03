---
name: fix-sogou
description: Diagnose and (re)activate Sogou Pinyin (sogoupinyin on fcitx4) in the user's Ubuntu GNOME/X11 desktop session — start fcitx and the Sogou service if they died or never started, and switch the active input method to sogoupinyin. Use when the user says "activate/enable/fix sogou", "sogou pinyin isn't working", "can't type Chinese", "fcitx is not running", "the input method disappeared / no tray icon", "Ctrl+Space does nothing", or invokes /fix-sogou. Also handles the login-time fcitx crash (BadWindow) that leaves the session with only ibus.
---

# Fix Sogou (fcitx4 + Sogou Pinyin on Ubuntu 24.04 GNOME/X11)

Everything is in one idempotent script; run it and relay the output:

```bash
~/.claude/skills/fix-sogou/fix-sogou.sh            # diagnose + fix + switch to Sogou
~/.claude/skills/fix-sogou/fix-sogou.sh --status   # diagnose only, change nothing
~/.claude/skills/fix-sogou/fix-sogou.sh --autostart  # fix + install a delayed fcitx autostart entry
```

Lines are tagged `[ok]`, `[FAIL]`, `[..]` (informational). Exit 0 = Sogou is
usable; exit 1 = something the script could not fix (it prints the manual step).

## What the script does

1. **Locate the user's own graphical session.** Picks the X socket in
   `/tmp/.X11-unix` owned by the current user (falls back to `$DISPLAY`, then
   `:0`), uses `unix:path=/run/user/$UID/bus`, exports the fcitx IM env vars.
   Warns if the session is Wayland (fcitx4/Sogou is X11-only).
2. **Check prerequisites:** `fcitx`, `fcitx-remote`, `sogoupinyin` deb,
   `/usr/share/fcitx/addon/fcitx-sogoupinyin.conf`, `~/.xinputrc` → `run_im
   fcitx`, and the `GTK_IM_MODULE`/`QT_IM_MODULE`/`XMODIFIERS` values that
   gnome-shell actually has.
3. **Check processes — filtered to the current user (`pgrep -u`).** This is a
   multi-seat machine; other users' `fcitx` processes are listed and ignored.
   Reports the last line and timestamp of `~/.config/fcitx/log/crash.log`.
4. **Fix:** if no fcitx of ours is running, or it is running but does not
   answer on D-Bus, (kill it and) `fcitx -d`; then start
   `/opt/sogoupinyin/files/bin/sogoupinyin-service` and `-watchdog` if absent.
5. **Verify** `sogoupinyin` is `enabled=true` in fcitx's D-Bus `IMList`
   property, then best-effort `fcitx-remote -s sogoupinyin && fcitx-remote -o`.
6. `--autostart`: writes `~/.config/autostart/fcitx-delayed.desktop`
   (`sleep 5; fcitx -d`) to dodge the login race described below.

## Interpreting `fcitx-remote` state

`fcitx-remote` reports the state of the **focused input context**, not the
daemon: `0` = no text field focused, `1` = English, `2` = Sogou active,
`Not get reply` = fcitx unreachable. Only the last one is a failure. When run
from Claude Code the terminal usually has no IC, so `0` is normal — do not
"fix" that; tell the user to focus a window and press **Ctrl+Space**.

## Root cause seen on this machine (2026-08-30)

- fcitx **crashed at login** (`crash.log`: `fcitx: BadWindow (invalid Window
  parameter)`) — a known fcitx4 race when GNOME autostarts it before the
  shell is ready — leaving only GNOME's `ibus-daemon` running.
- `pgrep fcitx` was misleading: the running `fcitx` belonged to **another
  user's seat session**, not ours. Always filter by user.
- All config was already correct (`~/.xinputrc`, env vars, `sogoupinyin` in
  `EnabledIMList` and `IMName` in `~/.config/fcitx/profile`); the only fix
  needed was starting fcitx + the Sogou service in the right session.

## Manual fallbacks (when the script prints [FAIL])

| Symptom | Fix |
|---|---|
| `sogoupinyin` not in enabled IM list | `fcitx-config-gtk` → **+** → untick *Only Show Current Language* → add *Sogou Pinyin*; or edit `EnabledIMList`/`IMName` in `~/.config/fcitx/profile`, then `fcitx-remote -r` |
| `~/.xinputrc` not fcitx | `im-config -n fcitx`, then log out/in |
| Apps opened before fcitx started don't get Chinese | restart that app (env is fine; it just connected to ibus/XIM before fcitx existed) |
| Session is Wayland | log in choosing "Ubuntu on Xorg" at the GDM gear icon |
| fcitx dies again on every login | run with `--autostart` |

## After editing this skill

Mirror to `~/ubuntu-config/claude/skills/fix-sogou/` and `diff -q` (global
rule). Do not commit in `~/ubuntu-config` unless asked.
