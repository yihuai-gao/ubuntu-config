# hdd_io_monitor

Live read/write monitor for the `/storage/hddN` (or any mounted) disks with
per-process attribution. Standard-library Python only, no root needed: it runs
on the host and inside an enroot/Docker container that bind-mounts `/storage`.
The same sampler powers the **storage** mode of the web dashboard in
`../traffic_monitor/` (which imports this file, so keep it in place).

```bash
~/ubuntu-config/hdd_io_monitor/hdd_io_monitor.py                 # every mounted /storage/hdd* and ssd*, refresh 2 s
~/ubuntu-config/hdd_io_monitor/hdd_io_monitor.py hdd5 hdd8 -i 5  # pick disks, refresh every 5 s
~/ubuntu-config/hdd_io_monitor/hdd_io_monitor.py ssd1 /storage   # any hddN/ssdN name or mount point
~/ubuntu-config/hdd_io_monitor/hdd_io_monitor.py -d 60 --summary # run 60 s, print one cumulative summary
```

Options: `-i/--interval` (seconds between samples, default 2), `-d/--duration`
(stop after N seconds, 0 = until Ctrl-C), `-n/--top` (process rows per screen,
default 25), `--summary` (only the cumulative per-process table at the end),
`--no-clear` (append screens instead of clearing; automatic when stdout is not
a tty, e.g. `| tee log`), `--mmaps` (also scan `/proc/<pid>/maps`, slower).

## What you see

* **Disk table** — read/write bytes per second, IOPS and `util%` for every
  monitored disk, from `/proc/diskstats` (world readable, so this covers all
  users). A partition resolves to its parent disk; the last entry for a mount
  point wins, so an `autofs` trigger such as `systemd-1 /storage/ssd1` does not
  shadow the real device.
* **Attributed processes** — processes of your own uid holding files on a
  monitored disk, with their read/write rate. Rates come from the file-offset
  deltas in `/proc/<pid>/fdinfo` (exact per file, so `rsync`, `tar`, `dd`, `cp`
  are attributed to the disk the file lives on). A process that only touches
  one monitored disk but moves no offset (`pread`/`pwrite`, mmap, readahead —
  e.g. parquet readers, torch loaders) falls back to its global
  `/proc/<pid>/io` block counters and is marked `(io counters)`. The `session`
  column is the 8-char `CLAUDE_CODE_SESSION_ID` prefix of the process, so a
  Claude session's workers can be traced back to it. `st` is the process
  state (`D` = blocked on I/O).
* **Idle handles** — own processes holding files open on the disk without
  moving bytes in the window.
* **Unattributed** — processes of other users (unreadable `/proc/<pid>/fd`,
  shown as `nobody` inside a container without the uid mapped). They are
  listed when their command line mentions a monitored mount or they sit in
  `D` state; `~user` is the owner guessed from a `/home/<user>/` or
  `/storage/<disk>/<user>/` path in the command line. Kernel threads are not
  listed.
* **Summary** (always printed at exit, the only output with `--summary`) —
  cumulative bytes per process and disk over the whole run.

Caveats: writes are counted when a writable fd's offset advances, i.e. bytes
handed to the page cache, not when the disk absorbs them; the io-counter
fallback is process-wide, so a process that also hammers an unmonitored disk
is over-attributed; a file reopened on the same fd number resets its baseline.
