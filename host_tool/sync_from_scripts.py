#!/usr/bin/env python3
"""Sync the host tools from the canonical copies in <repo>/scripts.

The files in this directory are GENERATED COPIES. The single source of truth
is the repository's scripts/ directory; edit there and re-run this script.

Usage:
  python sync_from_scripts.py          # copy canonical files into host_tool/
  python sync_from_scripts.py --check  # exit 1 if host_tool/ has drifted

When this plugin is distributed standalone (without the repository), the
source directory does not exist and the script exits 0 with a notice.
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

CANONICAL_FILES = [
    "udp_log_env.py",
    "udp_log_record.py",
    "udp_log_journal.py",
    "udp_log_sequence.py",
    "udp_log_receiver.py",
    "udp_log_gui.py",
    "udp_log_web_viewer.py",
    "udp_log_tcp_bridge.py",
]

HOST_TOOL_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = HOST_TOOL_DIR.parents[2] / "scripts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not copy; exit 1 when host_tool differs from scripts/",
    )
    args = parser.parse_args()

    if not SCRIPTS_DIR.is_dir():
        print(f"Source directory not found ({SCRIPTS_DIR}); standalone package, nothing to sync.")
        return 0

    missing = [name for name in CANONICAL_FILES if not (SCRIPTS_DIR / name).is_file()]
    if missing:
        print(f"Canonical files missing in {SCRIPTS_DIR}: {', '.join(missing)}", file=sys.stderr)
        return 1

    drifted = [
        name
        for name in CANONICAL_FILES
        if not (HOST_TOOL_DIR / name).is_file()
        or not filecmp.cmp(SCRIPTS_DIR / name, HOST_TOOL_DIR / name, shallow=False)
    ]

    if args.check:
        if drifted:
            print("host_tool drifted from scripts/: " + ", ".join(drifted), file=sys.stderr)
            print("Run: python sync_from_scripts.py", file=sys.stderr)
            return 1
        print("host_tool is in sync with scripts/.")
        return 0

    for name in drifted:
        shutil.copyfile(SCRIPTS_DIR / name, HOST_TOOL_DIR / name)
        print(f"Synced {name}")
    if not drifted:
        print("Already in sync, nothing copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
