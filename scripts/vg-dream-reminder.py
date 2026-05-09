#!/usr/bin/env python3
"""Dream consolidation reminder — soft hint emitted from Stop hook.

When meta_memory_mode != "disabled" AND bootstrap-consolidate gate met
(24h + 5 sessions since last consolidate), prints a one-line reminder.

Once-per-session via state file `.vg/dream-reminder-shown`.

Exit always 0 — soft hint never blocks.

Usage:
  python3 scripts/vg-dream-reminder.py            # normal
  python3 scripts/vg-dream-reminder.py --reset    # clear state file (for tests)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT_ENV = "VG_REPO_ROOT"
CONFIG_PATH_ENV = "VG_CONFIG_PATH"  # test override
STATE_PATH_ENV = "VG_DREAM_STATE_PATH"  # test override
CONSOLIDATE_HELPER_ENV = "VG_CONSOLIDATE_HELPER"  # test override


def _resolve_root() -> Path:
    return Path(os.environ.get(REPO_ROOT_ENV) or os.getcwd()).resolve()


def _config_path(root: Path) -> Path:
    override = os.environ.get(CONFIG_PATH_ENV)
    if override:
        return Path(override)
    return root / ".claude" / "vg.config.md"


def _state_path(root: Path) -> Path:
    override = os.environ.get(STATE_PATH_ENV)
    if override:
        return Path(override)
    return root / ".vg" / "dream-reminder-shown"


def _consolidate_helper(root: Path) -> Path:
    override = os.environ.get(CONSOLIDATE_HELPER_ENV)
    if override:
        return Path(override)
    p = root / ".claude" / "scripts" / "bootstrap-consolidate.py"
    if not p.exists():
        p = root / "scripts" / "bootstrap-consolidate.py"
    return p


def _read_mode(cfg: Path) -> str:
    if not cfg.exists():
        return "disabled"
    try:
        body = cfg.read_text(encoding="utf-8")
    except OSError:
        return "disabled"
    m = re.search(r"^meta_memory_mode:\s*(\S+)", body, re.MULTILINE)
    return m.group(1) if m else "disabled"


def _gate_met(helper: Path) -> bool:
    if not helper.exists():
        return False
    try:
        rc = subprocess.run(
            [sys.executable, str(helper), "--check-gate"],
            capture_output=True, timeout=10,
        ).returncode
    except Exception:
        return False
    return rc == 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true",
                   help="Clear the once-per-session state file")
    args = p.parse_args(argv)

    root = _resolve_root()
    state = _state_path(root)

    if args.reset:
        state.unlink(missing_ok=True)
        return 0

    mode = _read_mode(_config_path(root))
    if mode == "disabled":
        return 0
    if state.exists():
        return 0
    if not _gate_met(_consolidate_helper(root)):
        return 0

    # Mark shown then emit (mark first so concurrent stops don't double-emit)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.touch()

    print("\U0001F319 Meta-memory: consolidation gate met (24h + 5 sessions accumulated).", file=sys.stderr)
    print("   Run `/vg:learn --consolidate --apply` to merge promoted rules.", file=sys.stderr)
    print("   (Skip if not ready — does not affect pipeline.)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
