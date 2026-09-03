#!/usr/bin/env python3
"""Print the largest files and directories from an ncdu JSON export (ncdu -o FILE).

Usage: top_entries.py EXPORT.json [--top N] [--max-dir-depth D]

The ncdu export format is [majorver, minorver, metadata, root] where root is a
nested array: [dirinfo, entry, entry, ...]. A dict entry is a file; a list
entry is a subdirectory in the same shape as root.
"""

import argparse
import json
import sys


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if size < 1024 or unit == "PiB":
            return f"{size:7.1f} {unit}" if unit != "B" else f"{int(size):7d} B"
        size /= 1024
    return f"{size:.1f} PiB"


def walk_iterative(root, files, dirs):
    """Post-order traversal without recursion (ncdu trees can be very deep)."""
    # Stack of (node, path, child_index, accumulated_size)
    root_info = root[0]
    stack = [[root, root_info["name"].rstrip("/"), 1, root_info.get("dsize", 0), 0]]
    while stack:
        frame = stack[-1]
        node, path, idx, _, depth = frame[0], frame[1], frame[2], frame[3], frame[4]
        if idx < len(node):
            frame[2] += 1
            entry = node[idx]
            if isinstance(entry, dict):
                # Skip entries ncdu couldn't read and hard-link duplicates
                size = entry.get("dsize", entry.get("asize", 0))
                if not entry.get("excluded") and not entry.get("hlnkc"):
                    files.append((size, f"{path}/{entry['name']}"))
                    frame[3] += size
            else:
                info = entry[0]
                stack.append(
                    [entry, f"{path}/{info['name']}", 1, info.get("dsize", 0), depth + 1]
                )
        else:
            stack.pop()
            dirs.append((frame[3], path, depth))
            if stack:
                stack[-1][3] += frame[3]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_file")
    parser.add_argument("--top", type=int, default=15, help="entries per list")
    parser.add_argument(
        "--max-dir-depth",
        type=int,
        default=3,
        help="only list directories at most this deep below the scan root",
    )
    args = parser.parse_args()

    with open(args.export_file) as f:
        data = json.load(f)
    if not (isinstance(data, list) and len(data) >= 4):
        sys.exit(f"error: {args.export_file} is not an ncdu JSON export")

    files: list[tuple[int, str]] = []
    dirs: list[tuple[int, str, int]] = []
    walk_iterative(data[3], files, dirs)

    total = dirs[-1][0] if dirs else 0
    root_path = data[3][0]["name"]
    print(f"Scan of {root_path} — total {human(total).strip()} "
          f"({len(files)} files)\n")

    print(f"=== Top {args.top} directories (depth ≤ {args.max_dir_depth}) ===")
    shallow = [d for d in dirs if 0 < d[2] <= args.max_dir_depth]
    for size, path, _ in sorted(shallow, reverse=True)[: args.top]:
        pct = f"{100 * size / total:5.1f}%" if total else "     "
        print(f"{human(size)}  {pct}  {path}")

    print(f"\n=== Top {args.top} files ===")
    for size, path in sorted(files, reverse=True)[: args.top]:
        print(f"{human(size)}  {path}")


if __name__ == "__main__":
    main()
