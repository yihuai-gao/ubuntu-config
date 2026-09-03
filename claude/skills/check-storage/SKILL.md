---
name: check-storage
description: Check disk usage across all mounted filesystems with df -h, highlight near-full drives, then automatically launch multi-threaded ncdu scans (~/.local/usr/bin/ncdu) in the background on the near-full drives and report the most expensive files and directories. Use whenever the user invokes /check-storage, asks to check storage or disk usage, says a disk is full or nearly full, asks "what's eating my disk space", wants to find large files to delete, or mentions "no space left on device" errors.
---

# Check Storage

Two-phase disk triage: an instant `df -h` overview with near-full drives highlighted, then automatic background `ncdu` scans of the near-full drives to find what's actually consuming the space.

The ncdu binary lives at `~/.local/usr/bin/ncdu` (v2.8+, supports `-t` threads and `-o` JSON export). Do not assume a system ncdu exists.

## Phase 1 — Overview (show immediately)

1. Run:
   ```bash
   df -h -x tmpfs -x devtmpfs -x overlay -x squashfs -x efivarfs
   ```
2. Present ALL real filesystems as a markdown table (Filesystem, Size, Used, Avail, Use%, Mounted on), sorted by Use% descending. Mark each row's status:
   - **🔴 CRITICAL** — Use% ≥ 90%
   - **🟡 NEAR-FULL** — Use% ≥ 80%
   - leave the status cell empty otherwise
3. Show this table to the user right away — do not wait for scans to finish.

"Near-full" = Use% ≥ 80% (both tiers above). If the user gave a different threshold or named specific drives, honor that instead.

## Phase 2 — Background ncdu scans of near-full drives

For each near-full filesystem, launch a scan in the background immediately after showing the table (use `run_in_background: true` so the user isn't blocked):

```bash
SCANDIR=$(mktemp -d /tmp/check-storage.XXXXXX)
~/.local/usr/bin/ncdu -0 -x -t $(nproc) -o "$SCANDIR/<mount-slug>.json" <mountpoint>
```

- `-0` — no UI (headless), `-x` — stay on that one filesystem, `-t $(nproc)` — multi-threaded scan, `-o` — export results as JSON for later analysis.
- `<mount-slug>` = mountpoint with `/` → `-` (e.g. `/home` → `home.json`, `/` → `root.json`).
- Launch one background Bash call per drive so they scan in parallel and you're notified as each finishes.
- **Skip network/FUSE mounts** (nfs, cifs, fuse.*, s3-backed mounts): scanning them is slow and can hammer remote storage. Note the skip in the table and only scan them if the user explicitly asks.
- Scanning as non-root will hit permission-denied on some system dirs — that's expected; ncdu skips them and the results are still valid for the user's own data.

If NO drive is near-full, say so, skip scanning, and stop — offer to scan a specific mount anyway if the user wants.

## Phase 3 — Report the most expensive files (as each scan completes)

When a scan's background task finishes, parse its export with the bundled script:

```bash
python3 ~/.claude/skills/check-storage/scripts/top_entries.py "$SCANDIR/<mount-slug>.json" --top 15
```

It prints the largest files and largest directories (by disk usage). For each scanned drive, report:

1. **Top directories** — where the bulk lives (helps spot caches, old checkpoints, docker/container storage, core dumps).
2. **Top files** — concrete deletion candidates with full absolute paths.
3. A one-line read of the situation, e.g. "~1.2 TiB of the 1.8 TiB on /home is under ~/video-gen/checkpoints — old run outputs are the main cost."

Also tell the user they can browse the scan interactively themselves:

```bash
~/.local/usr/bin/ncdu -f "$SCANDIR/<mount-slug>.json"
```

**Never delete anything.** This skill only finds and reports. If the user asks to clean up, confirm the specific paths before removing them.
