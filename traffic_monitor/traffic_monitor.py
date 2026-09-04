#!/usr/bin/env python3
"""traffic_monitor.py - per-process network traffic dashboard for a Linux desktop.

Standard library only; needs root (CAP_NET_RAW + reading every /proc/<pid>/fd).

How it works
  * One AF_PACKET sniffer thread per monitored interface counts bytes per flow
    (proto, local ip, local port, remote ip, remote port), using the kernel's
    packet direction flag (PACKET_OUTGOING) to tell upload from download.
  * Every interval the flows are matched to socket inodes through
    /proc/net/{tcp,tcp6,udp,udp6} (host namespace first, then every other
    network namespace found under /proc/<pid>/net, so containers count too),
    and inodes to pids through /proc/<pid>/fd.
  * SNAT/DNAT traffic of bridged containers is de-NATed through
    /proc/net/nf_conntrack when that file exists.
  * Per-process accounting is kept per captured interface (plus an "all"
    union when several are captured); the dashboard switches between them
    with /api/state?iface=<name>.  Selecting an interface that is not captured
    yet starts a sniffer for it on the fly.  Overall rates of EVERY interface
    (from /proc/net/dev) are always reported for the switcher menu.
  * A tiny HTTP server (default http://127.0.0.1:8787) serves the dashboard
    and /api/state (JSON).  --text prints a top-like table instead.
"""

import argparse
import collections
import ipaddress
import json
import os
import pwd
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ETH_P_ALL = 0x0003
PACKET_OUTGOING = 4
ARPHRD_ETHER = 1
SOL_PACKET = 263
PACKET_STATISTICS = 6
SO_RCVBUFFORCE = getattr(socket, "SO_RCVBUFFORCE", 33)
RCVBUF = 64 << 20        # requested per-interface socket queue (kernel reports 2x via SO_RCVBUF)
SNAPLEN = 128           # bytes copied per packet; enough for VLAN + IPv6 + ext headers + ports
PROTO_TCP = 6
PROTO_UDP = 17
PROTO_NAMES = {6: "tcp", 17: "udp", 1: "icmp", 58: "icmp6", 2: "igmp", 47: "gre", 50: "esp"}

PID_UNATTRIBUTED = -1   # IP traffic that matches no socket (NAT, kernel, other netns)
PID_NON_IP = -2         # ARP, LLDP, non-IP frames


# --------------------------------------------------------------------------- #
# Packet parsing
# --------------------------------------------------------------------------- #
def parse_packet(data, hatype):
    """Return (proto, src_ip_bytes, sport, dst_ip_bytes, dport) or None for non-IP."""
    off = 0
    if hatype == ARPHRD_ETHER:
        if len(data) < 14:
            return None
        et = (data[12] << 8) | data[13]
        off = 14
        while et in (0x8100, 0x88A8):  # 802.1Q / QinQ
            if len(data) < off + 4:
                return None
            et = (data[off + 2] << 8) | data[off + 3]
            off += 4
        if et == 0x0800:
            ver = 4
        elif et == 0x86DD:
            ver = 6
        else:
            return None
    else:  # tun/ppp/wireguard: raw IP
        if not data:
            return None
        ver = data[0] >> 4
    if ver == 4:
        if len(data) < off + 20:
            return None
        ihl = (data[off] & 0x0F) * 4
        proto = data[off + 9]
        frag_off = ((data[off + 6] & 0x1F) << 8) | data[off + 7]
        src = data[off + 12:off + 16]
        dst = data[off + 16:off + 20]
        l4 = off + ihl
        if frag_off:
            return (proto, src, 0, dst, 0)
    elif ver == 6:
        if len(data) < off + 40:
            return None
        proto = data[off + 6]
        src = data[off + 8:off + 24]
        dst = data[off + 24:off + 40]
        l4 = off + 40
        while proto in (0, 43, 60, 44, 51):  # hop-by-hop, routing, dst-opts, fragment, AH
            if len(data) < l4 + 2:
                return None
            nxt = data[l4]
            if proto == 44:
                hl = 8
            elif proto == 51:
                hl = (data[l4 + 1] + 2) * 4
            else:
                hl = (data[l4 + 1] + 1) * 8
            proto = nxt
            l4 += hl
    else:
        return None
    if proto in (PROTO_TCP, PROTO_UDP) and len(data) >= l4 + 4:
        return (proto, src, (data[l4] << 8) | data[l4 + 1], dst, (data[l4 + 2] << 8) | data[l4 + 3])
    return (proto, src, 0, dst, 0)


def norm_ip(b):
    """Collapse IPv4-mapped IPv6 (::ffff:a.b.c.d) to 4 bytes."""
    if len(b) == 16 and b[:10] == b"\x00" * 10 and b[10:12] == b"\xff\xff":
        return b[12:]
    return b


def ip_str(b):
    try:
        return str(ipaddress.ip_address(b))
    except ValueError:
        return b.hex()


# --------------------------------------------------------------------------- #
# Sniffer thread
# --------------------------------------------------------------------------- #
class Sniffer(threading.Thread):
    def __init__(self, iface):
        super().__init__(name=f"sniff-{iface}", daemon=True)
        self.iface = iface
        self.lock = threading.Lock()
        self.counts = {}           # flow key -> [rx_bytes, tx_bytes]
        self.non_ip = [0, 0]
        self.packets = 0
        self.error = None
        self.sock = None

    def run(self):
        try:
            s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
            # SO_RCVBUF is silently clamped to net.core.rmem_max (~208 kB by default);
            # SO_RCVBUFFORCE (root) bypasses the cap so bursts are queued, not dropped.
            try:
                s.setsockopt(socket.SOL_SOCKET, SO_RCVBUFFORCE, RCVBUF)
            except OSError:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
            s.bind((self.iface, 0))
        except OSError as e:
            self.error = f"{self.iface}: {e}"
            return
        self.sock = s
        # Copy only the headers (SNAPLEN bytes) into user space; MSG_TRUNC makes
        # recvmsg_into still return the packet's true length.
        buf = bytearray(SNAPLEN)
        bufs = [buf]
        recv = s.recvmsg_into
        lock = self.lock
        trunc = socket.MSG_TRUNC
        while True:
            try:
                n, _anc, _flags, addr = recv(bufs, 0, trunc)
            except OSError as e:
                self.error = f"{self.iface}: {e}"
                return
            out = 1 if addr[2] == PACKET_OUTGOING else 0
            p = parse_packet(bytes(buf[:n if n < SNAPLEN else SNAPLEN]), addr[3])
            with lock:
                self.packets += 1
                if p is None:
                    self.non_ip[out] += n
                    continue
                proto, src, sp, dst, dp = p
                key = (proto, src, sp, dst, dp) if out else (proto, dst, dp, src, sp)
                c = self.counts.get(key)
                if c is None:
                    self.counts[key] = [n, 0] if out == 0 else [0, n]
                else:
                    c[out] += n

    def drops(self):
        """Packets the kernel dropped for this socket since the last call (tpacket_stats)."""
        if self.sock is None:
            return 0
        try:
            raw = self.sock.getsockopt(SOL_PACKET, PACKET_STATISTICS, 8)
            return int.from_bytes(raw[4:8], sys.byteorder)
        except OSError:
            return 0

    def drain(self):
        with self.lock:
            counts, self.counts = self.counts, {}
            non_ip, self.non_ip = self.non_ip, [0, 0]
            return counts, non_ip


# --------------------------------------------------------------------------- #
# /proc helpers
# --------------------------------------------------------------------------- #
def _hex_ip(h):
    if len(h) == 8:
        return bytes.fromhex(h)[::-1]
    return norm_ip(b"".join(bytes.fromhex(h[i:i + 8])[::-1] for i in range(0, 32, 8)))


def parse_proc_net(path, proto, conn, listen):
    """Fill conn[(proto,lip,lport,rip,rport)] and listen[(proto,lip|None,lport)] with inodes."""
    try:
        f = open(path)
    except OSError:
        return
    with f:
        next(f, None)
        for line in f:
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                inode = int(parts[9])
                if inode == 0:
                    continue
                lip, lport = parts[1].split(":")
                rip, rport = parts[2].split(":")
                lport, rport = int(lport, 16), int(rport, 16)
                lb, rb = _hex_ip(lip), _hex_ip(rip)
            except ValueError:
                continue
            if rport == 0 and not any(rb):
                listen.setdefault((proto, lb if any(lb) else None, lport), inode)
            else:
                conn.setdefault((proto, lb, lport, rb, rport), inode)


def build_socket_table(netns_pids):
    """netns_pids: ordered list of (netns_id, representative pid) — host first."""
    conn, listen = {}, {}
    seen = set()
    for _ns, pid in netns_pids:
        base = "/proc/net" if pid is None else f"/proc/{pid}/net"
        if base in seen:
            continue
        seen.add(base)
        for fn, proto in (("tcp", PROTO_TCP), ("tcp6", PROTO_TCP), ("udp", PROTO_UDP), ("udp6", PROTO_UDP)):
            parse_proc_net(f"{base}/{fn}", proto, conn, listen)
    return conn, listen


def scan_fds():
    """Return (inode->pid, {netns_id: pid}) by walking /proc/<pid>/fd."""
    inode_pid = {}
    netns = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            ns = os.readlink(f"/proc/{name}/ns/net")
            netns.setdefault(ns, pid)
        except OSError:
            pass
        fdd = f"/proc/{name}/fd"
        try:
            fds = os.listdir(fdd)
        except OSError:
            continue
        for fd in fds:
            try:
                t = os.readlink(f"{fdd}/{fd}")
            except OSError:
                continue
            if t.startswith("socket:["):
                try:
                    inode_pid[int(t[8:-1])] = pid
                except ValueError:
                    pass
    return inode_pid, netns


def parse_conntrack(path="/proc/net/nf_conntrack"):
    """Map on-the-wire (NATed) flow keys back to the pre-NAT keys the sockets see."""
    nat = {}
    try:
        f = open(path)
    except OSError:
        return nat
    with f:
        for line in f:
            parts = line.split()
            if len(parts) < 4 or not parts[3].isdigit():
                continue
            proto = int(parts[3])
            if proto not in (PROTO_TCP, PROTO_UDP):
                continue
            tup = []
            cur = {}
            for tok in parts[4:]:
                for k in ("src=", "dst=", "sport=", "dport="):
                    if tok.startswith(k):
                        if k == "src=" and cur:
                            tup.append(cur)
                            cur = {}
                        cur[k[:-1]] = tok[len(k):]
                        break
            if cur:
                tup.append(cur)
            if len(tup) != 2:
                continue
            try:
                o, r = tup
                osrc, odst = ipaddress.ip_address(o["src"]).packed, ipaddress.ip_address(o["dst"]).packed
                rsrc, rdst = ipaddress.ip_address(r["src"]).packed, ipaddress.ip_address(r["dst"]).packed
                osp, odp, rsp, rdp = int(o["sport"]), int(o["dport"]), int(r["sport"]), int(r["dport"])
            except (KeyError, ValueError):
                continue
            # SNAT/masquerade: wire sees (reply.dst:reply.dport <-> reply.src:reply.sport)
            if rdst != osrc or rdp != osp:
                nat[(proto, rdst, rdp, rsrc, rsp)] = (proto, osrc, osp, odst, odp)
            # DNAT/port-forward: wire sees (orig.dst:orig.dport <-> orig.src:orig.sport)
            if rsrc != odst or rsp != odp:
                nat[(proto, odst, odp, osrc, osp)] = (proto, rsrc, rsp, rdst, rdp)
    return nat


def read_net_dev():
    out = {}
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                name, rest = line.split(":", 1)
                cols = rest.split()
                if len(cols) >= 9:
                    out[name.strip()] = (int(cols[0]), int(cols[8]))
    except OSError:
        pass
    return out


def iface_state(name):
    try:
        with open(f"/sys/class/net/{name}/operstate") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def iface_exists(name):
    return name and "/" not in name and name not in (".", "..") and os.path.isdir(f"/sys/class/net/{name}")


def default_interfaces():
    ifs = []
    for fam in ("-4", "-6"):
        try:
            out = subprocess.run(["ip", fam, "-o", "route", "show", "default"],
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        for line in out.splitlines():
            parts = line.split()
            if "dev" in parts:
                d = parts[parts.index("dev") + 1]
                if d not in ifs:
                    ifs.append(d)
    if not ifs:
        ifs = all_interfaces()
    return ifs


def all_interfaces():
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return []
    return [n for n in names if n != "lo" and not n.startswith(("veth", "docker", "br-", "virbr"))]


def proc_info(pid):
    info = {"name": "?", "cmd": "", "user": "", "container": "", "alive": False}
    try:
        with open(f"/proc/{pid}/comm") as f:
            info["name"] = f.read().strip()
        info["alive"] = True
    except OSError:
        return info
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        info["cmd"] = cmd[:240]
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("Uid:"):
                    uid = int(line.split()[1])
                    try:
                        info["user"] = pwd.getpwuid(uid).pw_name
                    except KeyError:
                        info["user"] = str(uid)
                    break
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            cg = f.read()
        for marker in ("docker-", "/docker/", "libpod-", "/lxc/"):
            i = cg.find(marker)
            if i >= 0:
                cid = cg[i + len(marker):].lstrip("/")
                cid = "".join(ch for ch in cid[:64] if ch.isalnum())
                info["container"] = cid[:12]
                break
    except OSError:
        pass
    return info


# --------------------------------------------------------------------------- #
# Monitor: ties it together
# --------------------------------------------------------------------------- #
class ProcStats:
    __slots__ = ("pid", "info", "rx_rate", "tx_rate", "rx_total", "tx_total", "conns",
                 "remotes", "first_seen", "last_active", "info_time", "spark")

    def __init__(self, pid, now):
        self.pid = pid
        self.info = None
        self.rx_rate = self.tx_rate = 0.0
        self.rx_total = self.tx_total = 0
        self.conns = 0
        self.remotes = {}          # (proto, rip, rport) -> [rx, tx, last_active]
        self.first_seen = now
        self.last_active = now
        self.info_time = 0.0
        self.spark = collections.deque(maxlen=60)  # (rx_rate, tx_rate)


class View:
    """Per-process accounting for one captured interface, or ("all") the union of every captured one."""

    def __init__(self, name, ifaces, history):
        self.name = name
        self.ifaces = list(ifaces)
        self.history_len = history
        self.procs = {}                                   # pid -> ProcStats
        self.hist = collections.deque(maxlen=history)     # (t, {pid: (rx, tx)})
        self.totals = {"rx_bps": 0.0, "tx_bps": 0.0, "attr_rx_bps": 0.0, "attr_tx_bps": 0.0}
        self.start = time.time()

    def update(self, resolved, non_ip, dt, now, rates, info_for):
        """resolved: list of (pid, key, rx, tx); rates: {iface: (rx_bps, tx_bps, rx_total, tx_total)}."""
        per_pid = {}
        per_pid_conns = collections.defaultdict(set)
        per_pid_remotes = collections.defaultdict(dict)
        for pid, key, rx, tx in resolved:
            e = per_pid.get(pid)
            if e is None:
                per_pid[pid] = [rx, tx]
            else:
                e[0] += rx
                e[1] += tx
            per_pid_conns[pid].add(key)
            rk = (key[0], key[3], key[4])
            r = per_pid_remotes[pid].get(rk)
            if r is None:
                per_pid_remotes[pid][rk] = [rx, tx]
            else:
                r[0] += rx
                r[1] += tx
        if non_ip[0] or non_ip[1]:
            per_pid[PID_NON_IP] = list(non_ip)

        attr_rx = attr_tx = 0
        for ps in self.procs.values():
            ps.rx_rate = ps.tx_rate = 0.0
            ps.conns = 0
        for pid, (rx, tx) in per_pid.items():
            ps = self.procs.get(pid)
            if ps is None:
                ps = self.procs[pid] = ProcStats(pid, now)
            ps.rx_rate = rx / dt
            ps.tx_rate = tx / dt
            ps.rx_total += rx
            ps.tx_total += tx
            ps.conns = len(per_pid_conns.get(pid, ()))
            if rx or tx:
                ps.last_active = now
            if pid >= 0:
                attr_rx += rx
                attr_tx += tx
            for rk, (rrx, rtx) in per_pid_remotes.get(pid, {}).items():
                r = ps.remotes.get(rk)
                if r is None:
                    ps.remotes[rk] = [rrx, rtx, now]
                else:
                    r[0] += rrx
                    r[1] += rtx
                    r[2] = now
            if len(ps.remotes) > 40:
                keep = sorted(ps.remotes.items(), key=lambda kv: kv[1][0] + kv[1][1], reverse=True)[:30]
                ps.remotes = dict(keep)
        for pid, ps in list(self.procs.items()):
            ps.spark.append((ps.rx_rate, ps.tx_rate))
            if now - ps.info_time > 30 or ps.info is None:
                ps.info = info_for(pid)
                ps.info_time = now
            if not ps.info["alive"] and now - ps.last_active > self.history_len + 60:
                del self.procs[pid]
        self.hist.append((now, {pid: (v[0] / dt, v[1] / dt) for pid, v in per_pid.items()}))
        tot_rx = sum(rates[i][0] for i in self.ifaces if i in rates)
        tot_tx = sum(rates[i][1] for i in self.ifaces if i in rates)
        self.totals = {"rx_bps": tot_rx, "tx_bps": tot_tx,
                       "attr_rx_bps": attr_rx / dt, "attr_tx_bps": attr_tx / dt}


ALL_VIEW = "all"


class Monitor:
    def __init__(self, ifaces, interval=1.0, history=300, use_conntrack=True):
        self.interval = interval
        self.history_len = history
        self.use_conntrack = use_conntrack and os.path.exists("/proc/net/nf_conntrack")
        self.hostname = socket.gethostname()
        self.sniffers = {}                    # iface -> Sniffer (insertion order = capture order)
        self.views = {}                       # iface | ALL_VIEW -> View
        self.inode_pid = {}
        self.netns = {}
        self.host_ns = self._read_host_ns()
        self.last_scan = 0.0
        self.scan_ms = 0.0
        self.tick_ms = 0.0
        self.flows = 0
        self.drops = 0
        self._nat = {}
        self._nat_time = 0.0
        self._info_cache = {}                 # pid -> (time, info) shared by every view
        self.start = time.time()
        self.lock = threading.Lock()
        self.iface_rates = {}                 # EVERY /proc/net/dev iface -> (rx_bps, tx_bps, rx_total, tx_total, state)
        self._last_dev = read_net_dev()
        self._last_t = time.monotonic()
        for i in ifaces:
            self._add_capture(i)

    @property
    def ifaces(self):
        return list(self.sniffers)

    @property
    def default_view(self):
        return ALL_VIEW if len(self.sniffers) > 1 else next(iter(self.sniffers), ALL_VIEW)

    @staticmethod
    def _read_host_ns():
        try:
            return os.readlink("/proc/self/ns/net")
        except OSError:
            return None

    def _add_capture(self, iface):
        """Register a sniffer + view for iface (call under self.lock once threads run). Returns the Sniffer."""
        s = self.sniffers[iface] = Sniffer(iface)
        self.views[iface] = View(iface, [iface], self.history_len)
        if len(self.sniffers) > 1 and ALL_VIEW not in self.views:
            self.views[ALL_VIEW] = View(ALL_VIEW, self.sniffers, self.history_len)
        if ALL_VIEW in self.views:
            self.views[ALL_VIEW].ifaces = list(self.sniffers)
        return s

    def ensure_capture(self, iface):
        """Start capturing iface on demand (dashboard switch). Returns an error string or None."""
        with self.lock:
            if iface in self.views:
                return None
            if not iface_exists(iface):
                return f"{iface}: no such interface"
            s = self._add_capture(iface)
            s.start()
        time.sleep(0.3)  # bind errors surface almost immediately
        if s.error:
            with self.lock:
                self.sniffers.pop(iface, None)
                self.views.pop(iface, None)
                if ALL_VIEW in self.views:
                    if len(self.sniffers) > 1:
                        self.views[ALL_VIEW].ifaces = list(self.sniffers)
                    else:   # the union view only existed because of this failed capture
                        del self.views[ALL_VIEW]
            return s.error
        print(f"[traffic_monitor] now also capturing {iface}", file=sys.stderr)
        return None

    def start_threads(self):
        for s in self.sniffers.values():
            s.start()
        threading.Thread(target=self._loop, name="aggregate", daemon=True).start()

    def errors(self):
        return [s.error for s in self.sniffers.values() if s.error]

    # -- resolution ---------------------------------------------------------
    def _rescan_fds(self):
        t0 = time.monotonic()
        self.inode_pid, self.netns = scan_fds()
        self.last_scan = t0
        self.scan_ms = (time.monotonic() - t0) * 1000

    def _netns_order(self):
        order = [(self.host_ns, None)]
        for ns, pid in self.netns.items():
            if ns != self.host_ns:
                order.append((ns, pid))
        return order

    @staticmethod
    def _lookup(key, conn, listen):
        inode = conn.get(key)
        if inode is None:
            proto, lip, lport = key[0], key[1], key[2]
            inode = listen.get((proto, lip, lport))
            if inode is None:
                inode = listen.get((proto, None, lport))
        return inode

    def _socket_table(self):
        if time.monotonic() - self.last_scan > 15:
            self._rescan_fds()
        return build_socket_table(self._netns_order())

    def _resolve(self, flows, conn, listen):
        """flows: {key: [rx, tx]} -> list of (pid, key, rx, tx)."""
        nat = None
        pending = []
        out = []

        def attach(key, rx, tx, inode):
            pid = self.inode_pid.get(inode)
            if pid is None:
                pending.append((key, rx, tx, inode))
            else:
                out.append((pid, key, rx, tx))

        for key, (rx, tx) in flows.items():
            inode = self._lookup(key, conn, listen)
            if inode is None and self.use_conntrack and key[0] in (PROTO_TCP, PROTO_UDP):
                if nat is None:
                    if time.monotonic() - self._nat_time > 5:
                        self._nat = parse_conntrack()
                        self._nat_time = time.monotonic()
                    nat = self._nat
                nk = nat.get(key)
                if nk is not None:
                    inode = self._lookup(nk, conn, listen)
                    key = nk
            if inode is None:
                out.append((PID_UNATTRIBUTED, key, rx, tx))
            else:
                attach(key, rx, tx, inode)
        if pending:
            if time.monotonic() - self.last_scan > 0.5:
                self._rescan_fds()
            for key, rx, tx, inode in pending:
                pid = self.inode_pid.get(inode)
                out.append((pid if pid is not None else PID_UNATTRIBUTED, key, rx, tx))
        return out

    # -- main loop ----------------------------------------------------------
    def _loop(self):
        while True:
            time.sleep(self.interval)
            try:
                self._tick()
            except Exception as e:  # keep the loop alive; report in the UI
                print(f"[traffic_monitor] tick error: {e!r}", file=sys.stderr)

    def _tick(self):
        t0 = time.monotonic()
        dt = t0 - self._last_t
        self._last_t = t0
        if dt <= 0:
            return
        now = time.time()

        with self.lock:
            sniffers = list(self.sniffers.items())
        drained = {}                          # iface -> (flows, non_ip)
        nflows = 0
        for iface, s in sniffers:
            c, n = s.drain()
            drained[iface] = (c, n)
            nflows += len(c)
        self.flows = nflows
        self.drops += sum(s.drops() for _i, s in sniffers)
        conn, listen = self._socket_table()
        resolved = {iface: self._resolve(c, conn, listen) for iface, (c, _n) in drained.items()}

        dev = read_net_dev()
        rates = {}
        for i, b in dev.items():
            a = self._last_dev.get(i)
            if a:
                rates[i] = (max(0, b[0] - a[0]) / dt, max(0, b[1] - a[1]) / dt, b[0], b[1], iface_state(i))
        self._last_dev = dev

        with self.lock:
            self._info_cache = {p: v for p, v in self._info_cache.items() if now - v[0] < 300}
            for name, view in self.views.items():
                ifs = list(self.sniffers) if name == ALL_VIEW else [name]
                res, non_ip = [], [0, 0]
                for i in ifs:
                    r = resolved.get(i)
                    if r is None:
                        continue
                    res.extend(r)
                    non_ip[0] += drained[i][1][0]
                    non_ip[1] += drained[i][1][1]
                view.ifaces = ifs
                view.update(res, non_ip, dt, now, rates, self._info_for)
            self.iface_rates = rates
            self.tick_ms = (time.monotonic() - t0) * 1000

    def _info_for(self, pid):
        if pid == PID_UNATTRIBUTED:
            return {"name": "unattributed", "cmd": "IP traffic matching no local socket (NAT, kernel, short-lived)",
                    "user": "", "container": "", "alive": True}
        if pid == PID_NON_IP:
            return {"name": "non-IP frames", "cmd": "ARP / LLDP / other link-layer frames",
                    "user": "", "container": "", "alive": True}
        c = self._info_cache.get(pid)
        now = time.time()
        if c is None or now - c[0] > 30:
            c = self._info_cache[pid] = (now, proc_info(pid))
        return c[1]

    # -- snapshot -----------------------------------------------------------
    def iface_list(self):
        """Every interface with its overall rates, captured ones first (call under self.lock)."""
        captured = list(self.sniffers)
        rest = sorted(i for i in self.iface_rates if i not in self.sniffers)
        rest.sort(key=lambda i: (self.iface_rates[i][4] == "down", i))   # lo reports "unknown": keep it with the live ones
        out = []
        for i in captured + rest:
            r = self.iface_rates.get(i)
            if r is None:
                continue
            out.append({"name": i, "rx_bps": r[0], "tx_bps": r[1], "rx_total": r[2], "tx_total": r[3],
                        "state": r[4], "captured": i in self.sniffers})
        return out

    def snapshot(self, view=None, top_series=7):
        """Dashboard state for one view (an interface name or ALL_VIEW); None for the default. None if unknown."""
        with self.lock:
            name = view or self.default_view
            v = self.views.get(name)
            if v is None:
                return None
            now = time.time()
            procs = []
            for pid, ps in v.procs.items():
                info = ps.info or {}
                remotes = sorted(ps.remotes.items(), key=lambda kv: kv[1][0] + kv[1][1], reverse=True)[:12]
                procs.append({
                    "pid": pid, "name": info.get("name", "?"), "cmd": info.get("cmd", ""),
                    "user": info.get("user", ""), "container": info.get("container", ""),
                    "alive": info.get("alive", False),
                    "rx_bps": ps.rx_rate, "tx_bps": ps.tx_rate,
                    "rx_total": ps.rx_total, "tx_total": ps.tx_total,
                    "conns": ps.conns, "idle_s": now - ps.last_active,
                    "spark": [[round(a), round(b)] for a, b in ps.spark],
                    "remotes": [{"proto": PROTO_NAMES.get(rk[0], str(rk[0])), "host": ip_str(rk[1]),
                                 "port": rk[2], "rx": v[0], "tx": v[1], "idle_s": now - v[2]}
                                for rk, v in remotes],
                })
            procs.sort(key=lambda p: (-(p["rx_bps"] + p["tx_bps"]), -(p["rx_total"] + p["tx_total"])))

            # history: top entities over the window + "other"
            sums = collections.Counter()
            for _t, d in v.hist:
                for pid, (rx, tx) in d.items():
                    sums[pid] += rx + tx
            top = [pid for pid, _ in sums.most_common(top_series)]
            top_set = set(top)
            ts, rx_series, tx_series = [], {str(p): [] for p in top}, {str(p): [] for p in top}
            rx_series["other"], tx_series["other"] = [], []
            for t, d in v.hist:
                ts.append(round(t))
                orx = otx = 0.0
                for p in top:
                    pv = d.get(p)
                    rx_series[str(p)].append(round(pv[0]) if pv else 0)
                    tx_series[str(p)].append(round(pv[1]) if pv else 0)
                for pid, (rx, tx) in d.items():
                    if pid not in top_set:
                        orx += rx
                        otx += tx
                rx_series["other"].append(round(orx))
                tx_series["other"].append(round(otx))
            names = {str(p): (v.procs[p].info or {}).get("name", "?") if p in v.procs else "?" for p in top}
            names["other"] = "other"

            return {
                "t": now, "started": v.start, "interval": self.interval,
                "hostname": self.hostname,
                "view": {"name": name, "ifaces": list(v.ifaces), "started": v.start},
                "default_view": self.default_view, "captured": list(self.sniffers),
                "ifaces": self.iface_list(),
                "totals": dict(v.totals),
                "procs": procs,
                "history": {"t": ts, "rx": rx_series, "tx": tx_series, "names": names, "order": [str(p) for p in top]},
                "meta": {"flows": self.flows, "drops": self.drops, "scan_ms": round(self.scan_ms, 1), "tick_ms": round(self.tick_ms, 1),
                         "conntrack": self.use_conntrack, "netns": len(self.netns),
                         "errors": self.errors()},
            }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def make_handler(monitor, index_html):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, "application/json", json.dumps(obj, separators=(",", ":")).encode())

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", index_html.encode())
            elif path == "/api/state":
                # ?iface=<name> selects a view; an interface not captured yet is captured on demand.
                view = urllib.parse.parse_qs(query).get("iface", [None])[0] or None
                if view and view != ALL_VIEW:
                    err = monitor.ensure_capture(view)
                    if err:
                        return self._json(400, {"error": err, "default_view": monitor.default_view})
                snap = monitor.snapshot(view)
                if snap is None:
                    return self._json(404, {"error": f"unknown view {view!r}", "default_view": monitor.default_view})
                self._json(200, snap)
            else:
                self._send(404, "text/plain", b"not found\n")
    return Handler


def human(bps, bits=False):
    v = bps * 8 if bits else bps
    units = ["b", "kb", "Mb", "Gb"] if bits else ["B", "kB", "MB", "GB"]
    i = 0
    while v >= 1000 and i < len(units) - 1:
        v /= 1000
        i += 1
    return f"{v:6.1f} {units[i]}/s"


def text_loop(monitor, rows=25):
    while True:
        time.sleep(monitor.interval)
        s = monitor.snapshot()
        t = s["totals"]
        lines = ["\x1b[H\x1b[2J",
                 f"traffic_monitor  {monitor.hostname}  ifaces={','.join(s['view']['ifaces'])}  total ↓{human(t['rx_bps'])} ↑{human(t['tx_bps'])}"
                 f"  attributed ↓{human(t['attr_rx_bps'])} ↑{human(t['attr_tx_bps'])}"
                 f"  flows={s['meta']['flows']}  drops={s['meta']['drops']}  fdscan={s['meta']['scan_ms']}ms",
                 f"{'PID':>7} {'NAME':<22} {'USER':<10} {'DOWN':>12} {'UP':>12} {'TOT DOWN':>10} {'TOT UP':>10} {'CONN':>5}  CMD"]
        for p in s["procs"][:rows]:
            lines.append(f"{p['pid']:>7} {p['name'][:22]:<22} {p['user'][:10]:<10} {human(p['rx_bps']):>12} "
                         f"{human(p['tx_bps']):>12} {human(p['rx_total'])[:-2]:>10} {human(p['tx_total'])[:-2]:>10} "
                         f"{p['conns']:>5}  {p['cmd'][:60]}")
        if s["meta"]["errors"]:
            lines.append("errors: " + "; ".join(s["meta"]["errors"]))
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()


def selftest():
    import struct
    eth = b"\xaa" * 6 + b"\xbb" * 6 + b"\x08\x00"
    ip4 = bytes([0x45, 0, 0, 40, 0, 0, 0x40, 0, 64, 6]) + b"\x00\x00" + bytes([10, 0, 0, 2]) + bytes([93, 184, 216, 34])
    tcp = struct.pack("!HH", 43210, 443) + b"\x00" * 16
    r = parse_packet(eth + ip4 + tcp, ARPHRD_ETHER)
    assert r == (6, bytes([10, 0, 0, 2]), 43210, bytes([93, 184, 216, 34]), 443), r
    vlan = b"\xaa" * 6 + b"\xbb" * 6 + b"\x81\x00\x00\x05\x08\x00"
    assert parse_packet(vlan + ip4 + tcp, ARPHRD_ETHER) == r
    ip6 = bytes([0x60, 0, 0, 0, 0, 8, 17, 64]) + bytes(range(16)) + bytes(range(16, 32))
    udp = struct.pack("!HHHH", 5353, 53, 8, 0)
    r6 = parse_packet(b"\xaa" * 12 + b"\x86\xdd" + ip6 + udp, ARPHRD_ETHER)
    assert r6 == (17, bytes(range(16)), 5353, bytes(range(16, 32)), 53), r6
    # hop-by-hop ext header before UDP
    ip6h = bytes([0x60, 0, 0, 0, 0, 16, 0, 64]) + bytes(range(16)) + bytes(range(16, 32)) + bytes([17, 0]) + b"\x00" * 6
    assert parse_packet(b"\xaa" * 12 + b"\x86\xdd" + ip6h + udp, ARPHRD_ETHER)[2] == 5353
    assert parse_packet(ip4 + tcp, 65534) == r            # raw IP (tun)
    assert parse_packet(b"\xaa" * 12 + b"\x08\x06" + b"\x00" * 28, ARPHRD_ETHER) is None  # ARP
    assert _hex_ip("0100007F") == bytes([127, 0, 0, 1])
    assert _hex_ip("0000000000000000FFFF00000100007F") == bytes([127, 0, 0, 1])
    assert norm_ip(b"\x00" * 10 + b"\xff\xff" + b"\x01\x02\x03\x04") == b"\x01\x02\x03\x04"
    conn, listen = {}, {}
    parse_proc_net("/proc/net/tcp", PROTO_TCP, conn, listen)
    parse_proc_net("/proc/net/tcp6", PROTO_TCP, conn, listen)
    inode_pid, netns = scan_fds()
    print(f"selftest OK: /proc/net/tcp{{,6}} conn={len(conn)} listen={len(listen)}; "
          f"fd scan inodes={len(inode_pid)} netns={len(netns)}; conntrack entries={len(parse_conntrack())}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-i", "--iface", action="append",
                    help="interface to monitor (repeatable; 'all' = every non-virtual NIC). "
                         "Default: interfaces carrying the default route.")
    ap.add_argument("--bind", default="127.0.0.1", help="HTTP bind address (default 127.0.0.1)")
    ap.add_argument("-p", "--port", type=int, default=8787, help="HTTP port (default 8787)")
    ap.add_argument("--interval", type=float, default=1.0, help="sampling interval in seconds")
    ap.add_argument("--history", type=int, default=300, help="seconds of history kept for the charts")
    ap.add_argument("--no-conntrack", action="store_true", help="do not de-NAT container traffic via nf_conntrack")
    ap.add_argument("--text", action="store_true", help="print a top-like table to the terminal instead of serving HTTP")
    ap.add_argument("--nice", type=int, default=10, help="nice value for the monitor itself (default 10; it drops its own packets under CPU contention instead of slowing other processes)")
    ap.add_argument("--selftest", action="store_true", help="run parser self-tests and exit")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if os.geteuid() != 0:
        sys.exit("traffic_monitor needs root (raw sockets + /proc/<pid>/fd of every user): run with sudo")

    try:
        os.nice(args.nice)
    except OSError:
        pass

    ifaces = []
    for i in args.iface or []:
        ifaces.extend(all_interfaces() if i == "all" else [i])
    if not ifaces:
        ifaces = default_interfaces()
    if not ifaces:
        sys.exit("no network interface found; pass --iface")

    mon = Monitor(ifaces, interval=args.interval, history=args.history, use_conntrack=not args.no_conntrack)
    mon.start_threads()
    time.sleep(0.3)
    for e in mon.errors():
        print(f"[traffic_monitor] capture error: {e}", file=sys.stderr)
    if all(s.error for s in mon.sniffers.values()):
        sys.exit("no interface could be captured")

    if args.text:
        try:
            text_loop(mon)
        except KeyboardInterrupt:
            pass
        return

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "dashboard.html"), encoding="utf-8") as f:
        index_html = f.read()
    srv = ThreadingHTTPServer((args.bind, args.port), make_handler(mon, index_html))
    srv.daemon_threads = True
    print(f"[traffic_monitor] {mon.hostname}: capturing {', '.join(ifaces)}"
          f"{' (conntrack de-NAT on)' if mon.use_conntrack else ''}", file=sys.stderr)
    print(f"[traffic_monitor] dashboard: http://{args.bind}:{args.port}/   (Ctrl-C to stop)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
