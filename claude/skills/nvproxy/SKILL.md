---
name: nvproxy
description: Turn the desktop's NVIDIA proxy on or off, or show its state. The `nvproxy on|off|status` switch on yihuai-desktop routes *.nvidia.com (browser PAC, git, ssh, and every CLI or Claude Code session that sourced ~/.config/nvproxy/env) through the laptop's SOCKS tunnel on desktop port 1080. Use when the user invokes /nvproxy [on|off|status], says "turn on/off the nvidia proxy", "enable/disable the nvidia proxy on the desktop", "route nvidia.com through the laptop", asks "is the nvidia proxy on", or reports that nicc / curl / git cannot resolve gitlab-master.nvidia.com on the desktop. For setting up or fixing the laptop-side tunnel itself, use the desktop-forwarding skill.
---

# nvproxy: NVIDIA proxy on/off for the desktop

This skill is the user-facing on/off switch. The tunnel it depends on (laptop `nvidia-tunnel.service`,
desktop port 1080) belongs to the **desktop-forwarding** skill. Script: `~/.local/bin/nvproxy` on the
desktop, a symlink to `~/ubuntu-config/slurm/nvproxy.sh`. The source of truth is the laptop's copy.
Subcommands: `on`, `off`, `status`. With no argument, run `status` and report it without asking anything.

## 1. Pick where to run it

```bash
hostname
```
- `yihuai-desktop`: run `~/.local/bin/nvproxy <cmd>` locally. Use the full path because a
  non-interactive PATH may lack `~/.local/bin`.
- Anything else (the laptop): `ssh -o BatchMode=yes -o ConnectTimeout=15 PiDesktop '~/.local/bin/nvproxy <cmd>'`.
  If PiDesktop is unreachable, use `YihuaiDesktop`. `YihuaiDesktopDirect` currently times out.

Pass: the command prints its `[OK]` lines (for `on`/`off`) or the state block (for `status`).

## 2. Run the command

| Cmd | Effect |
|---|---|
| `on` | Creates flag `~/.nvproxy-on`. Sets GNOME proxy mode `auto` with PAC `~/.config/nvproxy/nvproxy.pac`, served at `http://127.0.0.1:1081/nvproxy.pac` by `nvproxy-pac.service` (`*.nvidia.com` → SOCKS5 127.0.0.1:1080, else DIRECT). Sets `git config --global http.https://*.nvidia.com.proxy socks5h://localhost:1080`. Makes sure the HTTP router `nvproxy-http.service` (`~/.config/nvproxy/nvproxy_http.py`, 127.0.0.1:1082) is running and writes `~/.config/nvproxy/env`. ssh needs no change: the shared `~/.ssh/config` has a `Match host *.nvidia.com exec "test -f ~/.nvproxy-on"` block with `ProxyCommand nc -X 5 -x localhost:1080 %h %p`. |
| `off` | Removes the flag, restores the GNOME values recorded in `~/.config/nvproxy/gnome-proxy.prev` and unsets the git key. The router and the env file stay in place. Without the flag the router sends everything direct, so open shells keep working. |
| `status` | Shows the flag, the GNOME mode, the git key and the units, and runs a live check through 1080. |

The env file exports `HTTP(S)_PROXY=http://127.0.0.1:1082`, `NO_PROXY=localhost,127.0.0.1,::1,api.anthropic.com,.anthropic.com,statsig.anthropic.com,sentry.io,claude.ai,.claude.ai,claude.com,.claude.com`
(the Claude sign-in hosts are included)
and `NODE_USE_ENV_PROXY=1`. The desktop's `~/.zshrc`, `~/.bashrc` and `~/.zshenv` source it through a guarded line (the `.zshenv` hook is what gives non-interactive `ssh PiDesktop <cmd>` calls the variables; systemd user units and cron do not get them).
The router is always on. It sends `*.nvidia.com` to SOCKS 1080 only while the flag exists, and everything
else goes direct.

## 3. Prerequisite: the laptop tunnel

If `status` shows that port 1080 is not listening, the problem is on the **laptop** and nvproxy cannot fix
it. Run `bash ~/ubuntu-config/slurm/setup-nvidia-tunnel.sh` there (desktop-forwarding skill). The desktop
cannot start the tunnel because the laptop is behind NAT.

## 4. Verify (on the desktop)

```bash
~/.local/bin/nvproxy status
curl -s -o /dev/null -w '%{http_code}' --max-time 25 -x http://127.0.0.1:1082 https://gitlab-master.nvidia.com
ssh -l yihuaig gcp-iad-cs-001-dc-003.nvidia.com hostname     # the default ssh user on the desktop is yihuai
env | grep -i https_proxy                                    # run in a fresh shell
```
Pass when on: curl prints an HTTP code, ssh prints `gcp-iad-cs-001-dc-003`, and the env shows
`HTTPS_PROXY=http://127.0.0.1:1082`. Pass when off: curl and the bare-FQDN ssh fail fast. The env
variables are still set, which is expected.

## Claude Code sessions on the desktop

- Claude Code reads the proxy env only once, at startup. That is why the on/off toggle lives in the router,
  which checks the flag on every connection, and why running sessions follow it without a restart.
- A session started from a shell that sourced the env file inherits `HTTPS_PROXY`, so WebFetch, the Bash
  tool and every subagent follow the switch immediately.
- Sessions and shells started before the env file first existed need `source ~/.config/nvproxy/env` or a restart.
- WebSearch runs server-side at Anthropic and never reaches internal NVIDIA sites.
- Claude Code and Node cannot speak SOCKS, which is why the HTTP router on 1082 exists.

## Gotchas

- Over ssh, `gsettings` needs `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus`. The script sets it.
- GNOME proxy changes apply in the GUI session, so restart any browser that is already open.
- Desktop ports 1080, 1081 and 1082 are the proxy set (SOCKS, PAC, HTTP router). Port 2222 belongs to an
  Enroot sshd. Never reuse any of them.
- There is no sudo on the desktop. Never plan a step that needs it.
- A one-command prefix like `https_proxy=... curl ... | sh` does not reach the `sh` side, so `export`
  the variable instead. This stops mattering once the env file is sourced.
