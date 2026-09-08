# traffic_monitor

Per-process network traffic dashboard for this desktop (which process is
downloading/uploading at what speed), served locally, with a **storage** mode
(which process is reading/writing which `/storage/hddN` / `ssdN` disk at what
speed). Standard-library Python only, so it runs on the host outside any
container.

```bash
~/ubuntu-config/traffic_monitor/traffic_monitor.sh            # sudo is invoked for you
# open http://127.0.0.1:8787
~/ubuntu-config/traffic_monitor/traffic_monitor.sh --text     # terminal top-like view
~/ubuntu-config/traffic_monitor/traffic_monitor.sh -i all     # every physical NIC, not just default-route ones
~/ubuntu-config/traffic_monitor/traffic_monitor.sh -i enp6s0 -i docker0 -p 9000
~/ubuntu-config/traffic_monitor/traffic_monitor.sh -d hdd5 -d hdd6 --storage-interval 1   # storage mode: only these disks, 1 s
# open http://127.0.0.1:8787/?mode=storage&iface=hdd5   (URL overrides the remembered mode/view)
```

Options: `-i/--iface` (repeatable, `all` = every non-virtual NIC; default = the
interfaces carrying the IPv4/IPv6 default route), `-p/--port`, `--bind`,
`--interval`, `--history` (seconds kept for the charts, default 300),
`--no-conntrack`, `--nice` (default 10), `--selftest`. Storage mode:
`-d/--disk` (repeatable, `hddN`/`ssdN` or a mount point; default = every
mounted `/storage/hdd*` and `/storage/ssd*`), `--storage-interval` (default
2 s), `--no-storage`.

## What you see

* Top bar: the hostname, a **network / storage** switch, and an interface (or
  disk) switcher. Each mode remembers its own view; `?mode=storage&iface=hdd5`
  in the URL overrides both.
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

## Storage mode

Backed by `../hdd_io_monitor/hdd_io_monitor.py` (imported at start-up; the
dashboard falls back to network mode with a notice if it is missing). The same
layout as network mode with read/write in place of download/upload:

* **Disk menu** — every monitored disk with its block device, live read/write
  rate, lifetime counters from `/proc/diskstats`, a `% busy` tag, and the
  space used (with the `df` percentage, red above 90 %) and free; "All disks"
  is the union. Disks are discovered when the server starts, so a disk mounted
  later needs a restart (or `-d`).
* **Tiles** — read and write rate of the selected disk(s) with a 60 s
  sparkline, the share attributed to a process, active processes, and *Disk
  busy* (`util%` of the busiest selected disk).
* **Charts and table** — read/write by process over the history window; the
  table shows the rate, the 60 s sparkline, totals since the server started,
  the number of open files on the disk and the user. Processes carry a
  `CLAUDE_CODE_SESSION_ID` tag when they belong to a Claude Code session.
  Clicking a row lists the files (disk, path, bytes read/written, last active).
* **unattributed** — disk throughput not matched to an open file: page-cache
  writeback, readahead, mmap-only access, processes that exited between two
  samples. Attribution comes from `/proc/<pid>/fdinfo` offsets (all users, the
  server runs as root) with a `/proc/<pid>/io` fallback for `pread`/`pwrite`
  readers, see `../hdd_io_monitor/README.md` for the caveats.

Sampling cost is one `/proc` walk per `--storage-interval` (about 0.1 s of one
core per sample on a 1,200-process desktop); the disks themselves are never
touched.
