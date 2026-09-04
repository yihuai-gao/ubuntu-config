# traffic_monitor

Per-process network traffic dashboard for this desktop (which process is
downloading/uploading at what speed), served locally. Standard-library Python
only, so it runs on the host outside any container.

```bash
~/ubuntu-config/traffic_monitor/traffic_monitor.sh            # sudo is invoked for you
# open http://127.0.0.1:8787
~/ubuntu-config/traffic_monitor/traffic_monitor.sh --text     # terminal top-like view
~/ubuntu-config/traffic_monitor/traffic_monitor.sh -i all     # every physical NIC, not just default-route ones
~/ubuntu-config/traffic_monitor/traffic_monitor.sh -i enp6s0 -i docker0 -p 9000
```

Options: `-i/--iface` (repeatable, `all` = every non-virtual NIC; default = the
interfaces carrying the IPv4/IPv6 default route), `-p/--port`, `--bind`,
`--interval`, `--history` (seconds kept for the charts, default 300),
`--no-conntrack`, `--nice` (default 10), `--selftest`.

## What you see

* Top bar: the hostname and an interface switcher. Click the interface name to
  open a menu listing every interface on the machine with its live overall
  download/upload rate and lifetime counters (captured ones first, `down` ones
  dimmed). Picking one switches the whole dashboard to that interface; picking
  one that is not captured yet starts a sniffer for it on the fly (it stays
  captured until the monitor exits). With several captured interfaces an
  "All captured" entry shows their union. Each interface keeps its own
  per-process history, so switching back and forth loses nothing; the choice
  is remembered per browser.
* Tiles: download / upload rate from the interface counters (ground truth), how
  much of it could be attributed to a process, active process count, capture
  health (kernel-dropped packets, per-tick cost).
* Two stacked-area charts (download, upload) of the last 5 minutes split by the
  top processes; hover for per-process values. Colours stick to a process while
  it is on screen.
* Sortable table: rate, 60 s trend (solid = down, dashed = up), totals since
  start, flow count, user, container id. Click a row for its remote endpoints.

## How it works / caveats

* One `AF_PACKET` sniffer per captured interface counts bytes per flow; the kernel's
  `PACKET_OUTGOING` flag gives the direction. Only the first 128 bytes of each
  packet are copied (`MSG_TRUNC` still reports the true length).
* Flows are matched to socket inodes through `/proc/net/{tcp,udp}{,6}` of the
  host network namespace and of every other namespace found under
  `/proc/<pid>/net` (so container processes are attributed too), then inodes to
  pids through `/proc/<pid>/fd`. Bridged-container traffic that was SNAT/DNATed
  is de-NATed through `/proc/net/nf_conntrack` when that file exists.
* `unattributed` = IP traffic matching no socket: NAT without conntrack, kernel
  traffic (e.g. NFS, WireGuard), very short-lived sockets that closed before the
  1 s sample. `non-IP frames` = ARP/LLDP etc.
* Overhead: lands on the monitor process itself (roughly one core at a
  saturated 1 Gbps link, far less at desktop rates). It runs at nice 10, so
  under CPU contention it drops its own packets (shown in the health tile)
  rather than slowing anything else. Nothing is installed or changed on the
  system; stop with Ctrl-C.
