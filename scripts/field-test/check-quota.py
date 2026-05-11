#!/usr/bin/env python3
"""scripts/field-test/check-quota.py — fail-stop when session exceeds caps.

Called by the /vg:field-test capture loop each iteration. Exits 0 to
continue, 1 to force-stop the pipeline (size or wall-clock cap exceeded).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _dir_size_bytes(p: Path) -> int:
    total = 0
    for entry in p.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except (FileNotFoundError, PermissionError):
                pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-dir", required=True)
    args = ap.parse_args()

    session_dir = Path(args.session_dir)
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    size_cap_mb = float(session.get("session_max_size_mb", 1024))
    hours_cap = float(session.get("max_session_hours", 4))
    started_at = float(session.get("started_at") or time.time())

    size_mb = _dir_size_bytes(session_dir) / (1024 * 1024)
    if size_mb > size_cap_mb:
        print(f"⛔ quota: size {size_mb:.1f}MB > cap {size_cap_mb}MB", file=sys.stderr)
        return 1

    elapsed_h = (time.time() - started_at) / 3600.0
    if elapsed_h > hours_cap:
        print(f"⛔ quota: wall-clock {elapsed_h:.2f}h > cap {hours_cap}h", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
