---
name: host-remote
description: Mirror a locally hosted static website (a directory with index.html, reports, galleries with videos) onto an NVIDIA Slurm cluster's login / VS Code node (oci-jhb by default; also oci-jhb-2, gcp-iad) through the cam_uva harness, served there at the SAME port as locally and reported by its public URL `http://<login node>.nvidia.com:<port>/` (opens on VPN and inside the cluster, no tunnel); the `ssh -L` forward is only the fallback for a machine outside the NVIDIA network. Use whenever the user invokes /host-remote <path>, asks to "host this site remotely / on the cluster / on the login node / on the vscode node", "mirror this website to oci-jhb", "publish this page on the nvidia server", "make http://127.0.0.1:<port>/ reachable from the cluster", or asks which sites are hosted remotely (/host-remote list) or to take one down (/host-remote unpublish <name>).
---

# Host a local website on a cluster login node

One command publishes a local site directory to the cluster and serves it there on the same port as the
local server. The server binds `0.0.0.0` (yaml `cluster_sites.bind`, user 2026-10-22), so the site answers
on the NVIDIA network at `http://<login node>.nvidia.com:<port>/` (oci-jhb: `http://oci-jhb-slurm-1-vscode-02.nvidia.com:<port>/`,
oci-jhb-2: `http://oci-jhb-slurm-2-vscode-02.nvidia.com:<port>/`; the `network_url` of the result, built from the yaml
`cluster_sites.public_domain`; no authentication, anyone who can reach the node reads it). That URL opens over VPN and from
inside the cluster with no tunnel. The user is ALWAYS shown that URL as the headline (user 2026-10-26), never the node's own
`.cm.cluster` name and never the forwarded `http://127.0.0.1:<port>/` as the headline; the forward is the fallback for a
machine outside the NVIDIA network. Everything goes through the cam_uva harness (`hc`): never
hand-written `ssh`, `scp` or `rsync` to a cluster.

```
HC=/home/yihuai/video-gen/repositories/imaginaire4-cam-uva-1003/projects/cosmos3/cam_uva/harness/hc
```

Verbs (`$HC schema <verb>` is the contract; `$HC list` must show them, otherwise the harness server runs
older code: see "Server not ready" below):

| verb | what it does |
|---|---|
| `site_publish cluster=<c> path=<abs dir> [name=<n>] [port=<p>] [replace=true] [upload=hf\|ssh]` | incremental upload (only changed files; the yaml default `upload: hf` goes host -> the organisation HF bucket `nvidia/camera-cross-embodiment/sites/<name>/` (`cluster_sites.hf_prefix`) -> login-node download sync, measured 20-77 MB/s up and 428 MiB/s down; `upload=ssh` streams a tar through the laptop tunnel at 2-4 MB/s), register the port, ensure the login-node server, wait until the port is bound |
| `site_list cluster=<c>` | every published site with its port, state and forward command |
| `site_unpublish cluster=<c> name=<n>` | stop serving it (files stay on Lustre; the reply names the directory) |
| `site_server cluster=<c> action=ensure|stop|restart|status` | the one server process on the login node |

## Arguments

`/host-remote <path> [cluster] [port=N] [name=X]`, `/host-remote list [cluster]`, `/host-remote unpublish <name> [cluster]`.

- `<path>`: the site directory (the one a local server serves: it holds `index.html`). Relative paths are
  resolved against the cwd; a `http://127.0.0.1:<port>/` URL instead of a path means: find the local
  process serving that port (`pgrep -af "<port>"`, read its `--directory`, `--mount /=`, positional dir or
  `/proc/<pid>/cwd`) and use its directory. `site_publish` itself detects the local port of a path the same
  way, so `port=` is only needed when nothing serves it locally and a specific port is wanted.
- `cluster` defaults to `oci-jhb`. oci-jhb-2 shares oci-jhb's Lustre (same files, its own login node);
  gcp-iad is separate.

## Steps

1. `$HC health` first (every session's first harness call). A non-empty `code.stale` means the server runs
   older code than the disk: tell the user to run `$HC restart` before anything else. Non-empty `alerts`
   are reported first, as the ops rules say.
2. Resolve `<path>` to an absolute directory; refuse politely if it has no files. Note its size
   (`du -sh --apparent-size -L <path>`): above the yaml `max_site_gb` (8) the verb refuses (raise the knob in
   `config/infra/harness.yaml` and `hc restart`, or publish a smaller tree). Symlinks inside the tree are
   dereferenced on upload. The default path relays through the organisation HF bucket
   `nvidia/camera-cross-embodiment/sites/<name>/`, `cluster_sites.hf_prefix` (one plan + one apply, then one
   login-node download sync; a live login-node sync makes the publish wait, visible in the op log); pass
   `upload=ssh` only when HF is unreachable.
3. Run `$HC --timeout 1800 --wait 1500 site_publish cluster=<c> path=<abs path> [name=..] [port=..]` (the two
   client flags go BEFORE the verb; `timeout=` as a key=value is refused). It is a long verb: when it returns an
   operation id instead of a result, follow it with
   `$HC op id=<id>` until `done` (never `sleep` in a loop inside one Bash call; use a Monitor or spaced calls).
4. Report, in at most 10 lines:
   - the public link first and as the headline: `network_url`, `http://oci-jhb-slurm-1-vscode-02.nvidia.com:<port>/`
     (user 2026-10-26: always this one; never the `.cm.cluster` name, never the forwarded URL as the headline). With a
     loopback bind it is null and only the forwarded URL exists. The hub (`hub_network_url`, every site under `/<name>/`)
     only when it is `bound` (on oci-jhb port 8900 is held by another user's process, so each site answers on its own port);
   - then, as the fallback for a machine outside the NVIDIA network only: the forward command verbatim from the result
     (`ssh -N -L <port>:127.0.0.1:<port> oci-jhb-tunnel`) and the unchanged `http://127.0.0.1:<port>/`; the VS Code
     Ports-panel forward stalls bodies above about 1 MB (0908), so videos want the `ssh -L` route;
   - uploaded files/bytes vs total, whether the server was (re)started, elapsed seconds.
5. A second publish of the same path is the update path: only changed files move; say how many.

## Failure modes (read the verb's message; never work around a gate)

- `port ... in use` / state `failed` on the login node: another user holds that port there. Re-run with
  `port=<free>` (the message suggests one) or `replace=true` when another of OUR sites holds it.
- The tunnel is down (`ssh: connect ... 8024` / transport error): the laptop's `nvidia-tunnel.service` is
  not up. Say so; nothing on this host fixes it.
- A permission / allowlist refusal (`Bash(... harness/hc site_publish:*)` denied, HF/SSH gates): stop and
  give the exact paste-ready `permissions.allow` line, per the global rule.
- `Server not ready` (`hc list` lacks `site_publish`, or `code.stale` non-empty): the user runs `$HC restart`;
  check `$HC health` afterwards.

## Where things live

- Remote: `<cluster_sites.roots.<cluster>>/<name>/` (oci-jhb: `/lustre/fsw/portfolios/cosmos/users/yihuaig/projects/sites/<name>/`),
  registry `sites.json`, server state under `_server/` (`server.log`, `status.json`).
- Code: `projects/cosmos3/cam_uva/harness/sites.py` (verbs) and `harness/site_server.py` (the stdlib server copied
  to the login node); yaml block `cluster_sites` in `config/infra/harness.yaml`; memory `reference/remote-site-hosting.md`.
