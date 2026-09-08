#!/usr/bin/env python3
"""Live read/write monitor for the /storage/hddN disks with per-process attribution.

Works without root from inside the enroot container:
  * disk-level throughput for every disk comes from /proc/diskstats (world readable);
  * per-process attribution uses /proc/<pid>/fdinfo offsets and /proc/<pid>/io, which are
    readable only for processes of the mapped uid (yihuai) -- that covers every Claude
    session, its Python workers, rsync/tar/dd stagers, etc.;
  * processes of other users show as `nobody` (unmapped uid) -- for those only the command
    line and the D (I/O wait) state are visible, so they are listed as "unattributed" when
    their command line mentions one of the monitored mounts or they sit in D state.

Usage:
  hdd_io_monitor.py                       # live screen, every mounted /storage/hdd* and ssd*, refresh every 2 s
  hdd_io_monitor.py hdd5 hdd8 -i 5        # pick disks, refresh every 5 s
  hdd_io_monitor.py -d 60 --summary       # run 60 s, print one summary at the end
"""
from __future__ import annotations

import argparse
import os
import pwd
import re
import sys
import time
from collections import defaultdict

SECTOR = 512
O_ACCMODE = 0o3
CLEAR = "\x1b[2J\x1b[H"


def human(nbytes: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if abs(nbytes) < 1024 or unit == "T":
            return f"{nbytes:6.1f}{unit}"
        nbytes /= 1024
    return f"{nbytes:6.1f}T"


def _natural(name: str) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name))


def storage_disks() -> list[str]:
    """Every mounted /storage/hddN and /storage/ssdN, hdds first, in natural order."""
    with open("/proc/self/mounts") as fh:
        mps = {ln.split()[1] for ln in fh}
    names = [os.path.basename(mp) for mp in mps if re.fullmatch(r"/storage/(hdd|ssd)\d+", mp)]
    return sorted(names, key=lambda n: (n[:3] != "hdd", _natural(n)))


def resolve_mounts(names: list[str]) -> dict[str, tuple[str, str]]:
    """hddN -> (mount point, block device name as it appears in /proc/diskstats)."""
    out: dict[str, tuple[str, str]] = {}
    if not names:
        names = storage_disks()
        if not names:
            sys.exit("no /storage/hdd* or /storage/ssd* mounts found; pass disk names or mount points")
    with open("/proc/self/mounts") as fh:
        mounts = [ln.split() for ln in fh]
    with open("/proc/diskstats") as fh:
        known = {ln.split()[2] for ln in fh}
    for name in names:
        mp = name if name.startswith("/") else f"/storage/{name}"
        # The LAST entry for a mount point is the one on top (an autofs trigger such as
        # `systemd-1 /storage/ssd1 autofs` precedes the real device once it is mounted).
        srcs = [m[0] for m in mounts if m[1] == mp]
        if not srcs:
            sys.exit(f"{mp} is not mounted")
        src = srcs[-1]
        dev = os.path.basename(os.path.realpath(src))
        sysdir = f"/sys/class/block/{dev}"
        if os.path.exists(f"{sysdir}/partition"):
            dev = os.path.basename(os.path.realpath(f"{sysdir}/.."))
        if dev not in known:
            sys.exit(f"{mp}: mounted from {src}, but {dev!r} is not in /proc/diskstats (no block-device stats)")
        out[os.path.basename(mp.rstrip("/")) or mp] = (mp, dev)
    return out


def read_diskstats(devs: set[str]) -> dict[str, tuple[int, int, int, int, int]]:
    """dev -> (reads, sectors_read, writes, sectors_written, io_ticks_ms)."""
    out = {}
    with open("/proc/diskstats") as fh:
        for ln in fh:
            f = ln.split()
            if f[2] in devs:
                out[f[2]] = (int(f[3]), int(f[5]), int(f[7]), int(f[9]), int(f[12]))
    return out


def read_file(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return None


def proc_uid(pid: int) -> int | None:
    st = read_file(f"/proc/{pid}/status")
    if not st:
        return None
    m = re.search(r"^Uid:\s+(\d+)", st, re.M)
    return int(m.group(1)) if m else None


def proc_state_comm(pid: int) -> tuple[str, str] | None:
    st = read_file(f"/proc/{pid}/stat")
    if not st:
        return None
    rp = st.rindex(")")
    comm = st[st.index("(") + 1 : rp]
    state = st[rp + 2]
    return state, comm


def proc_cmdline(pid: int, width: int = 90) -> str:
    raw = read_file(f"/proc/{pid}/cmdline") or ""
    cmd = " ".join(raw.replace("\0", " ").split())
    return cmd if len(cmd) <= width else cmd[: width - 1] + "…"


def guess_owner(cmd: str, fallback: str) -> str:
    """Unmapped uids all show as nobody; a /home/<user>/ or /storage/<disk>/<user>/ path in the cmdline is the best hint."""
    m = re.search(r"/home/([A-Za-z0-9_.-]+)/", cmd) or re.search(r"/storage/(?:hdd|ssd)\d+/([A-Za-z0-9_.-]+)/", cmd)
    return f"~{m.group(1)}" if m else fallback


def proc_io(pid: int) -> tuple[int, int] | None:
    txt = read_file(f"/proc/{pid}/io")
    if txt is None:
        return None
    vals = dict(re.findall(r"^(\w+):\s+(\d+)", txt, re.M))
    try:
        return int(vals["read_bytes"]), int(vals["write_bytes"])
    except KeyError:
        return None


def proc_session(pid: int) -> str:
    env = read_file(f"/proc/{pid}/environ")
    if not env:
        return ""
    m = re.search(r"CLAUDE_CODE_SESSION_ID=([0-9a-f]{8})", env)
    return m.group(1) if m else ""


def proc_fds(pid: int, prefixes: dict[str, str]) -> dict[int, tuple[str, str, int, bool]] | None:
    """fd -> (disk, path, pos, writable) for fds under a monitored mount. None if unreadable."""
    try:
        fds = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return None
    out = {}
    for fd in fds:
        try:
            target = os.readlink(f"/proc/{pid}/fd/{fd}")
        except OSError:
            continue
        disk = next((d for d, mp in prefixes.items() if target.startswith(mp + "/") or target == mp), None)
        if disk is None:
            continue
        info = read_file(f"/proc/{pid}/fdinfo/{fd}")
        if not info:
            continue
        m_pos = re.search(r"^pos:\s+(\d+)", info, re.M)
        m_flags = re.search(r"^flags:\s+([0-7]+)", info, re.M)
        if not (m_pos and m_flags):
            continue
        out[int(fd)] = (disk, target, int(m_pos.group(1)), (int(m_flags.group(1), 8) & O_ACCMODE) != 0)
    return out


def proc_mmaps(pid: int, prefixes: dict[str, str]) -> dict[str, set[str]]:
    """disk -> set of file paths mmapped from that disk (own processes only)."""
    txt = read_file(f"/proc/{pid}/maps")
    out: dict[str, set[str]] = defaultdict(set)
    if not txt:
        return out
    for ln in txt.splitlines():
        parts = ln.split(None, 5)
        if len(parts) < 6:
            continue
        path = parts[5]
        for d, mp in prefixes.items():
            if path.startswith(mp + "/"):
                out[d].add(path)
    return out


class Sampler:
    def __init__(self, disks: dict[str, tuple[str, str]], want_mmaps: bool):
        self.disks = disks
        self.prefixes = {d: mp for d, (mp, _) in disks.items()}
        self.devs = {dev: d for d, (_, dev) in disks.items()}
        self.want_mmaps = want_mmaps
        self.prev_disk = read_diskstats(set(self.devs))
        self.prev_fd: dict[tuple[int, int, str], int] = {}
        self.prev_io: dict[int, tuple[int, int]] = {}
        self.prev_t = time.monotonic()
        self.users: dict[int, str] = {}
        # cumulative per-process attribution for the final summary
        self.cum: dict[tuple[int, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.meta: dict[int, dict] = {}

    def user(self, uid: int | None) -> str:
        if uid is None:
            return "?"
        if uid not in self.users:
            try:
                self.users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self.users[uid] = f"uid{uid}"
        return self.users[uid]

    def sample(self):
        now = time.monotonic()
        dt = max(now - self.prev_t, 1e-3)
        cur_disk = read_diskstats(set(self.devs))
        disk_rates = {}
        for dev, cur in cur_disk.items():
            prev = self.prev_disk.get(dev, cur)
            r_iops = (cur[0] - prev[0]) / dt
            r_bps = (cur[1] - prev[1]) * SECTOR / dt
            w_iops = (cur[2] - prev[2]) / dt
            w_bps = (cur[3] - prev[3]) * SECTOR / dt
            util = min(100.0, (cur[4] - prev[4]) / (dt * 1000) * 100)
            disk_rates[self.devs[dev]] = (r_bps, w_bps, r_iops, w_iops, util)
        self.prev_disk = cur_disk

        rows = []  # attributed: (pid, user, session, comm, state, disk, rB/s, wB/s, files, cmd, per_file)
        #   per_file: path -> [read bytes, written bytes] over this window (0/0 = open but idle)
        unattributed = []  # (pid, user, comm, state, cmd)
        seen_fd: dict[tuple[int, int, str], int] = {}
        seen_io: dict[int, tuple[int, int]] = {}
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            sc = proc_state_comm(pid)
            if sc is None:
                continue
            state, comm = sc
            uid = proc_uid(pid)
            fds = proc_fds(pid, self.prefixes)
            if fds is None:
                # unreadable (other user / root outside the uid mapping)
                cmd = proc_cmdline(pid)
                if not cmd:
                    continue  # kernel thread
                if any(mp in cmd for mp in self.prefixes.values()) or state == "D":
                    unattributed.append((pid, guess_owner(cmd, self.user(uid)), comm, state, cmd))
                continue
            per_disk: dict[str, dict] = defaultdict(lambda: {"r": 0.0, "w": 0.0, "files": set(), "per_file": {}})
            for fd, (disk, path, pos, writable) in fds.items():
                key = (pid, fd, path)
                seen_fd[key] = pos
                delta = pos - self.prev_fd.get(key, pos)
                pf = per_disk[disk]["per_file"].setdefault(path, [0, 0])
                if delta > 0:
                    per_disk[disk]["w" if writable else "r"] += delta / dt
                    pf[1 if writable else 0] += delta
                per_disk[disk]["files"].add(os.path.basename(path))
            if self.want_mmaps:
                for disk, paths in proc_mmaps(pid, self.prefixes).items():
                    for p in paths:
                        per_disk[disk]["files"].add("mmap:" + os.path.basename(p))
            io = proc_io(pid)
            io_r = io_w = 0.0
            if io is not None:
                seen_io[pid] = io
                prev = self.prev_io.get(pid, io)
                io_r = (io[0] - prev[0]) / dt
                io_w = (io[1] - prev[1]) / dt
            if not per_disk:
                continue
            # A process holding files on exactly one monitored disk but reading via mmap/readahead
            # shows no fd-offset movement; fall back to its global block I/O counters then.
            if len(per_disk) == 1:
                (disk, acc), = per_disk.items()
                has_ro = any(not w for (_, _, _, w) in fds.values())
                has_rw = any(w for (_, _, _, w) in fds.values())
                if acc["r"] == 0 and acc["w"] == 0 and (io_r > 0 or io_w > 0):
                    acc["r"] = io_r if has_ro else 0.0
                    acc["w"] = io_w if has_rw else 0.0
                    if acc["r"] or acc["w"]:
                        acc["files"].add("(io counters)")
                        acc["per_file"]["(io counters)"] = [acc["r"] * dt, acc["w"] * dt]
            session = proc_session(pid)
            user = self.user(uid)
            cmd = proc_cmdline(pid, 120)
            self.meta[pid] = {"user": user, "session": session, "comm": comm, "cmd": cmd}
            for disk, acc in per_disk.items():
                rows.append((pid, user, session, comm, state, disk, acc["r"], acc["w"], sorted(acc["files"]), cmd[:90], acc["per_file"]))
                c = self.cum[(pid, disk)]
                c["r"] += acc["r"] * dt
                c["w"] += acc["w"] * dt
        self.prev_fd = seen_fd
        self.prev_io = seen_io
        self.prev_t = now
        return dt, disk_rates, rows, unattributed


def render(dt, disk_rates, rows, unattributed, disks, top: int) -> str:
    lines = [time.strftime("%Y-%m-%d %H:%M:%S") + f"  (window {dt:.1f}s)"]
    lines.append(f"{'disk':6} {'dev':8} {'read/s':>9} {'write/s':>9} {'r-iops':>7} {'w-iops':>7} {'util%':>6}")
    for d, (mp, dev) in disks.items():
        r, w, ri, wi, u = disk_rates.get(d, (0, 0, 0, 0, 0))
        lines.append(f"{d:6} {dev:8} {human(r):>9} {human(w):>9} {ri:7.0f} {wi:7.0f} {u:6.1f}")
    lines.append("")
    lines.append("processes with files open on the monitored disks (own uid only; rates from fd offsets):")
    lines.append(f"{'pid':>8} {'user':8} {'session':8} {'disk':5} {'st':2} {'read/s':>9} {'write/s':>9}  comm / files / cmd")
    rows.sort(key=lambda r: -(r[6] + r[7]))
    active = [r for r in rows if r[6] + r[7] > 0]
    idle = [r for r in rows if r[6] + r[7] == 0]
    for pid, user, sess, comm, st, disk, r, w, files, cmd, _pf in active[:top]:
        lines.append(f"{pid:>8} {user:8} {sess:8} {disk:5} {st:2} {human(r):>9} {human(w):>9}  {comm}: {', '.join(files)[:70]}")
        lines.append(f"{'':8} {'':8} {'':8} {'':5} {'':2} {'':9} {'':9}  {cmd}")
    if idle:
        by_disk = defaultdict(list)
        for pid, user, sess, comm, st, disk, r, w, files, cmd, _pf in idle:
            by_disk[disk].append(f"{comm}[{pid}]")
        lines.append("  idle handles: " + "; ".join(f"{d}: {', '.join(sorted(set(v))[:8])}{' …' if len(set(v)) > 8 else ''}" for d, v in sorted(by_disk.items())))
    if unattributed:
        lines.append("")
        lines.append("unattributed (other users; ~name = owner guessed from a path in the cmdline): mentions a monitored mount or state=D")
        for pid, user, comm, st, cmd in unattributed[:top]:
            lines.append(f"{pid:>8} {user:8} {st:2} {comm}: {cmd}")
    return "\n".join(lines)


def summary(s: Sampler, elapsed: float) -> str:
    lines = [f"cumulative per-process bytes over {elapsed:.0f}s (own uid only):"]
    lines.append(f"{'pid':>8} {'user':8} {'session':8} {'disk':5} {'read':>9} {'write':>9}  comm / cmd")
    items = sorted(s.cum.items(), key=lambda kv: -(kv[1]["r"] + kv[1]["w"]))
    for (pid, disk), c in items:
        if c["r"] + c["w"] <= 0:
            continue
        m = s.meta[pid]
        lines.append(f"{pid:>8} {m['user']:8} {m['session']:8} {disk:5} {human(c['r']):>9} {human(c['w']):>9}  {m['comm']}: {m['cmd']}")
    if len(lines) == 2:
        lines.append("  (no attributable process moved bytes on these disks)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("disks", nargs="*", help="hddN/ssdN names or mount points (default: every mounted /storage/hdd* and ssd*)")
    ap.add_argument("-i", "--interval", type=float, default=2.0, help="seconds between samples")
    ap.add_argument("-d", "--duration", type=float, default=0, help="stop after this many seconds (0 = forever)")
    ap.add_argument("-n", "--top", type=int, default=25, help="max process rows per screen")
    ap.add_argument("--summary", action="store_true", help="print only a cumulative summary at the end")
    ap.add_argument("--no-clear", action="store_true", help="append screens instead of clearing the terminal")
    ap.add_argument("--mmaps", action="store_true", help="also scan /proc/<pid>/maps for mmapped files (slower)")
    args = ap.parse_args()

    disks = resolve_mounts(args.disks)
    s = Sampler(disks, args.mmaps)
    t0 = time.monotonic()
    try:
        time.sleep(min(args.interval, 1.0))  # short first window so the first screen is not empty
        while True:
            dt, disk_rates, rows, unattributed = s.sample()
            if not args.summary:
                screen = render(dt, disk_rates, rows, unattributed, disks, args.top)
                sys.stdout.write(("" if args.no_clear or not sys.stdout.isatty() else CLEAR) + screen + "\n\n")
                sys.stdout.flush()
            elapsed = time.monotonic() - t0
            if args.duration and elapsed >= args.duration:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:  # stdout closed (e.g. `| head`)
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return
    print(summary(s, time.monotonic() - t0))


if __name__ == "__main__":
    main()
