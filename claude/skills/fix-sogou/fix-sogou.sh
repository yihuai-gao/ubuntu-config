#!/usr/bin/env bash
# fix-sogou.sh — (re)start fcitx4 + Sogou Pinyin in the current user's desktop
# session and switch the active input method to sogoupinyin.
#
# Usage: fix-sogou.sh [--autostart] [--status]
#   --status     only diagnose/print state, change nothing
#   --autostart  also install a delayed fcitx autostart entry in
#                ~/.config/autostart so fcitx survives the login race
#
# Idempotent: safe to run repeatedly. Exit 0 on success, 1 on failure.
set -uo pipefail

ME="$(id -un)"; UID_="$(id -u)"
STATUS_ONLY=0; AUTOSTART=0
for a in "$@"; do
  case "$a" in
    --status) STATUS_ONLY=1 ;;
    --autostart) AUTOSTART=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
ok()  { printf '  [ok]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; }
note(){ printf '  [..]   %s\n' "$*"; }

# ---------- 1. locate the user's graphical session ----------
say "== Session =="
# Prefer an X socket owned by this user; fall back to $DISPLAY, then :0.
if [[ -z "${DISPLAY:-}" ]]; then
  for s in /tmp/.X11-unix/X*; do
    [[ -O "$s" ]] && { DISPLAY=":${s##*/X}"; break; }
  done
fi
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/${UID_}/bus}"
export GTK_IM_MODULE=fcitx QT_IM_MODULE=fcitx XMODIFIERS=@im=fcitx SDL_IM_MODULE=fcitx
note "user=$ME DISPLAY=$DISPLAY bus=$DBUS_SESSION_BUS_ADDRESS"

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  note "WARNING: XDG_SESSION_TYPE=wayland — fcitx4/Sogou only works properly on X11 (Xorg) sessions."
fi

# ---------- 2. prerequisites ----------
say "== Packages =="
command -v fcitx >/dev/null        && ok "fcitx binary present"        || { bad "fcitx not installed (apt install fcitx fcitx-config-gtk)"; exit 1; }
command -v fcitx-remote >/dev/null && ok "fcitx-remote present"        || { bad "fcitx-remote missing (apt install fcitx-bin)"; exit 1; }
dpkg -s sogoupinyin >/dev/null 2>&1 && ok "sogoupinyin $(dpkg-query -W -f='${Version}' sogoupinyin)" || { bad "sogoupinyin package not installed"; exit 1; }
[[ -f /usr/share/fcitx/addon/fcitx-sogoupinyin.conf ]] && ok "fcitx-sogoupinyin addon registered" || bad "fcitx-sogoupinyin addon conf missing"

# im-config selection
if grep -qs 'run_im fcitx' "$HOME/.xinputrc"; then
  ok "~/.xinputrc selects fcitx"
else
  note "~/.xinputrc does not select fcitx (im-config -n fcitx to fix; needs re-login)"
fi
# GTK/QT env in *this* shell is not what apps see; just report what the user's session has.
for v in GTK_IM_MODULE QT_IM_MODULE XMODIFIERS; do
  cur="$(tr '\0' '\n' < /proc/$(pgrep -u "$UID_" -x gnome-shell | head -1)/environ 2>/dev/null | grep "^$v=" | cut -d= -f2-)"
  [[ -n "$cur" ]] && note "gnome-shell env: $v=$cur"
done

# ---------- 3. who is running fcitx? (multi-user machine: other seats have their own) ----------
say "== Processes (this user only) =="
FCITX_PID="$(pgrep -u "$UID_" -x fcitx | head -1 || true)"
OTHER="$(pgrep -x fcitx | while read -r p; do [[ "$p" != "$FCITX_PID" ]] && printf '%s(%s) ' "$p" "$(ps -o user= -p "$p")"; done)"
[[ -n "$OTHER" ]] && note "fcitx processes owned by OTHER users (ignored): $OTHER"
if [[ -n "$FCITX_PID" ]]; then ok "fcitx running as $ME (pid $FCITX_PID)"; else bad "fcitx NOT running as $ME"; fi
pgrep -u "$UID_" -f sogoupinyin-service  >/dev/null && ok "sogoupinyin-service running"  || bad "sogoupinyin-service not running"
pgrep -u "$UID_" -f sogoupinyin-watchdog >/dev/null && ok "sogoupinyin-watchdog running" || note "sogoupinyin-watchdog not running"
if [[ -s "$HOME/.config/fcitx/log/crash.log" ]]; then
  note "last fcitx crash ($(date -r "$HOME/.config/fcitx/log/crash.log" '+%F %T')): $(tail -1 "$HOME/.config/fcitx/log/crash.log")"
fi

state() { fcitx-remote 2>/dev/null || echo "?"; }   # 0 closed, 1 inactive, 2 active, ? unreachable
current_im() {
  dbus-send --session --print-reply --dest=org.fcitx.Fcitx /inputmethod \
    org.freedesktop.DBus.Properties.Get string:org.fcitx.Fcitx.InputMethod string:CurrentIM 2>/dev/null \
    | awk -F'"' '/string/{print $2}'
}
IM_NOW="$(current_im)"; note "fcitx-remote state: $(state)  current IM: ${IM_NOW:-<none>}"

if (( STATUS_ONLY )); then exit 0; fi

# ---------- 4. start what is missing ----------
say "== Fix =="
if [[ -z "$FCITX_PID" ]] || [[ "$(state)" == "?" ]]; then
  if [[ -n "$FCITX_PID" ]]; then
    note "fcitx pid $FCITX_PID is unresponsive on D-Bus; killing it"
    kill "$FCITX_PID" 2>/dev/null; sleep 1; kill -9 "$FCITX_PID" 2>/dev/null
  fi
  note "starting fcitx -d"
  setsid nohup fcitx -d >/dev/null 2>&1 < /dev/null
  for i in $(seq 1 20); do [[ "$(state)" != "?" ]] && break; sleep 0.5; done
  [[ "$(state)" != "?" ]] && ok "fcitx up (pid $(pgrep -u "$UID_" -x fcitx | head -1))" || { bad "fcitx did not come up; check ~/.config/fcitx/log/crash.log"; exit 1; }
fi
if ! pgrep -u "$UID_" -f sogoupinyin-service >/dev/null; then
  note "starting sogoupinyin-service"
  setsid nohup /opt/sogoupinyin/files/bin/sogoupinyin-service >/dev/null 2>&1 < /dev/null &
fi
if ! pgrep -u "$UID_" -f sogoupinyin-watchdog >/dev/null; then
  note "starting sogoupinyin-watchdog"
  setsid nohup /opt/sogoupinyin/files/bin/sogoupinyin-watchdog >/dev/null 2>&1 < /dev/null &
fi
sleep 2

# ---------- 5. verify sogou is enabled, then switch to it ----------
# IMList D-Bus property: struct { uniqueName, name, langCode, enabled }
sogou_enabled() {
  dbus-send --session --print-reply --dest=org.fcitx.Fcitx /inputmethod \
    org.freedesktop.DBus.Properties.Get string:org.fcitx.Fcitx.InputMethod string:IMList 2>/dev/null \
    | grep -A3 'string "sogoupinyin"' | grep -q 'boolean true'
}
if sogou_enabled; then
  ok "sogoupinyin is in fcitx's enabled IM list"
else
  bad "sogoupinyin is NOT enabled in fcitx"
  note "fix: fcitx-config-gtk → '+' → untick 'Only Show Current Language' → add 'Sogou Pinyin'; or set EnabledIMList in ~/.config/fcitx/profile and run fcitx-remote -r"
  exit 1
fi
# Best-effort switch + activate. fcitx-remote reports the *focused* input
# context: 0 = no text field focused, 1 = English, 2 = Sogou active.
# The user may legitimately toggle back to English (Ctrl+Space) at any time,
# so a non-2 result here is informational, not a failure.
fcitx-remote -s sogoupinyin >/dev/null 2>&1
fcitx-remote -o            >/dev/null 2>&1
sleep 1
IM="$(current_im)"; ST="$(state)"
case "$ST" in
  2) ok "switched: active input method = ${IM:-?} (state 2)" ;;
  0) ok "fcitx healthy; no text field focused right now (state 0). Focus a window and press Ctrl+Space." ;;
  1) ok "fcitx healthy; current IM = ${IM:-?} (state 1, English). Press Ctrl+Space to switch to Sogou." ;;
  *) bad "fcitx unreachable after start (state $ST)"; exit 1 ;;
esac

# ---------- 6. optional: delayed autostart ----------
if (( AUTOSTART )); then
  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/fcitx-delayed.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Fcitx (delayed start)
Comment=Start fcitx a few seconds after login to avoid the BadWindow crash race
Exec=sh -c 'sleep 5; pgrep -u "$(id -u)" -x fcitx >/dev/null || fcitx -d; sleep 3; fcitx-remote -s sogoupinyin'
Terminal=false
X-GNOME-Autostart-Delay=5
NoDisplay=false
DESK
  ok "installed ~/.config/autostart/fcitx-delayed.desktop"
fi

say
say "Done. Ctrl+Space toggles English/Sogou. Apps opened before fcitx started may need a restart to pick it up."
