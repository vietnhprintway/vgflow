#!/usr/bin/env python3
"""Bootstrap consolidation engine - Anthropic Auto Dream 4-phase pattern.

Task 5.1: gate + lock foundation. Subsequent tasks 5.2-5.5 add 4 phases:
  Phase 1 - Orient (read memory directory state)             [Task 5.2]
  Phase 2 - Gather (narrow grep events.db + transcripts)     [Task 5.3]
  Phase 3 - Consolidate (in-place merge per Anthropic Dreams) [Task 5.4]
  Phase 4 - Prune & Index (rebuild MEMORY.md <= 200 lines)   [Task 5.5]

Task 5.6 wires /vg:learn --consolidate skill mode.

Trigger gate (per design Section 13.1):
  - 24+ hours since last consolidation (default; override VG_DREAMS_GATE_HOURS)
  - >5 sessions since last consolidation (default; override VG_DREAMS_GATE_SESSIONS)
  - No existing .consolidation.lock (else refuse - concurrent dream prevention)

State tracked: .vg/bootstrap/state.json with last_run_ts + sessions_since_last.

Subcommands:
  --check-gate [--json]   Print gate decision (rc=0 open / rc=1 closed)
  --acquire-lock          Create .consolidation.lock with PID
  --release-lock          Remove .consolidation.lock
  --update-state          Update state.json after consolidation
  --increment-sessions    Increment sessions_since_last counter
  --phase orient [--json] Phase 1: snapshot bootstrap state directory
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


DEFAULT_GATE_HOURS = 24.0
DEFAULT_GATE_SESSIONS = 5


def _state_dir() -> Path:
    """Resolve bootstrap state directory.

    Priority:
      1. VG_BOOTSTRAP_STATE_DIR env (tests + explicit override)
      2. <cwd>/.vg/bootstrap/ (production default)
    """
    env = os.environ.get("VG_BOOTSTRAP_STATE_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd() / ".vg" / "bootstrap"


def _read_state(state_dir: Path) -> dict | None:
    state_file = state_dir / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_gate(state_dir: Path) -> tuple[bool, str]:
    """Return (gate_open, reason)."""
    lock_file = state_dir / ".consolidation.lock"
    if lock_file.exists():
        return False, f"lock file present at {lock_file} - concurrent dream blocked"

    state = _read_state(state_dir)
    if state is None:
        return True, "first run - no state.json, gate open"

    last_run = state.get("last_run_ts", 0)
    sessions_since = state.get("sessions_since_last", 0)

    gate_hours = float(os.environ.get("VG_DREAMS_GATE_HOURS", DEFAULT_GATE_HOURS))
    gate_sessions = int(os.environ.get("VG_DREAMS_GATE_SESSIONS", DEFAULT_GATE_SESSIONS))

    elapsed = time.time() - last_run
    if elapsed < gate_hours * 3600:
        elapsed_h = elapsed / 3600
        # Strip trailing .0 so integer thresholds render as "24h" not "24.0h"
        gate_h_str = f"{gate_hours:g}h"
        return False, f"<{gate_h_str} since last run ({elapsed_h:.1f}h elapsed)"

    if sessions_since <= gate_sessions:
        return False, f"<={gate_sessions} sessions since last run ({sessions_since} counted)"

    return True, "both gates passed (24h+ elapsed + sessions threshold met)"


def acquire_lock(state_dir: Path) -> bool:
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_file = state_dir / ".consolidation.lock"
    if lock_file.exists():
        return False
    lock_file.write_text(f"pid={os.getpid()}\n", encoding="utf-8")
    return True


def release_lock(state_dir: Path) -> bool:
    lock_file = state_dir / ".consolidation.lock"
    if lock_file.exists():
        lock_file.unlink()
        return True
    return False


def update_state(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    new_state = {
        "last_run_ts": time.time(),
        "sessions_since_last": 0,
    }
    state_file.write_text(json.dumps(new_state, indent=2), encoding="utf-8")


def increment_sessions(state_dir: Path):
    state = _read_state(state_dir) or {"last_run_ts": 0, "sessions_since_last": 0}
    state["sessions_since_last"] = state.get("sessions_since_last", 0) + 1
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 1 - Orient (Task 5.2)
#
# Read .vg/bootstrap/ directory to produce a JSON snapshot of current memory
# state. Pure-read; never mutates anything. Used by Phase 2/3/4 as the input
# baseline ("where are we starting from?") and by /vg:learn --consolidate as
# a quick health probe.
#
# Snapshot fields:
#   accepted_md_exists / rejected_md_exists / retracted_md_exists / candidates_md_exists  bool
#   rule_count                          int   # len(rules/*.md)
#   memory_md_lines                     int   # 0 if MEMORY.md absent
#   last_consolidation_ts               float|None  # from state.json
#   sessions_since_last                 int|None    # from state.json
#   oversized_files                     list[str]   # rel paths > OVERSIZE_BYTES
#   orphan_files                        list[str]   # rel paths not matching any
#                                                   # known schema slot
#   state_dir                           str   # absolute path
# ---------------------------------------------------------------------------

OVERSIZE_BYTES = 50_000  # 50 KB - design Section 13.1 storage health probe

# Files we recognize at the top of .vg/bootstrap/. Anything else under the
# state dir that is not a rules/ entry, topics/ entry, or known artifact is
# flagged as orphan so consolidation can decide whether to re-home or prune.
KNOWN_TOP_LEVEL = frozenset({
    "MEMORY.md",
    "ACCEPTED.md",
    "REJECTED.md",
    "RETRACTED.md",
    "CANDIDATES.md",
    "CONSOLIDATION-LOG.md",
    "overlay.yml",
    "state.json",
    ".consolidation.lock",
})


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    if not text:
        return 0
    # Trailing newline shouldn't add a phantom line: "a\n" is 1 line.
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _walk_files(root: Path):
    """Yield every regular file under root (recursive). Skip if root absent."""
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def orient(state_dir: Path) -> dict:
    """Phase 1 - return snapshot dict (never raises on missing dir)."""
    rules_dir = state_dir / "rules"
    rule_files = []
    if rules_dir.exists() and rules_dir.is_dir():
        rule_files = sorted(p for p in rules_dir.glob("*.md") if p.is_file())

    state = _read_state(state_dir) or {}

    snap: dict = {
        "phase": "orient",
        "state_dir": str(state_dir),
        "accepted_md_exists": (state_dir / "ACCEPTED.md").exists(),
        "rejected_md_exists": (state_dir / "REJECTED.md").exists(),
        "retracted_md_exists": (state_dir / "RETRACTED.md").exists(),
        "candidates_md_exists": (state_dir / "CANDIDATES.md").exists(),
        "memory_md_exists": (state_dir / "MEMORY.md").exists(),
        "overlay_yml_exists": (state_dir / "overlay.yml").exists(),
        "consolidation_log_exists": (state_dir / "CONSOLIDATION-LOG.md").exists(),
        "rule_count": len(rule_files),
        "memory_md_lines": _count_lines(state_dir / "MEMORY.md"),
        "last_consolidation_ts": state.get("last_run_ts"),
        "sessions_since_last": state.get("sessions_since_last"),
        "oversized_files": [],
        "orphan_files": [],
    }

    if not state_dir.exists():
        return snap

    # Storage health: any file > OVERSIZE_BYTES anywhere under state_dir
    for f in _walk_files(state_dir):
        try:
            size = f.stat().st_size
        except OSError:
            continue
        rel = f.relative_to(state_dir).as_posix()
        if size > OVERSIZE_BYTES:
            snap["oversized_files"].append(rel)

    # Orphan detection: top-level files not in KNOWN_TOP_LEVEL and not under
    # rules/ or topics/. We deliberately don't recurse into rules/topics here;
    # those are owned by Phase 3/4 and have their own naming rules.
    for child in state_dir.iterdir():
        if child.is_dir():
            if child.name not in {"rules", "topics"}:
                snap["orphan_files"].append(child.name + "/")
            continue
        if child.name not in KNOWN_TOP_LEVEL:
            snap["orphan_files"].append(child.name)

    snap["oversized_files"].sort()
    snap["orphan_files"].sort()
    return snap


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap consolidation gate (Task 5.1)")
    parser.add_argument("--check-gate", action="store_true", help="Check trigger gate")
    parser.add_argument("--acquire-lock", action="store_true", help="Acquire .consolidation.lock")
    parser.add_argument("--release-lock", action="store_true", help="Release .consolidation.lock")
    parser.add_argument("--update-state", action="store_true",
                        help="Update state.json after successful consolidation")
    parser.add_argument("--increment-sessions", action="store_true",
                        help="Increment sessions_since_last counter")
    parser.add_argument("--phase", choices=["orient"], default=None,
                        help="Run a 4-phase consolidation step")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv[1:])

    state_dir = _state_dir()

    if args.check_gate:
        gate_open, reason = check_gate(state_dir)
        payload = {"gate_open": gate_open, "reason": reason, "state_dir": str(state_dir)}
        if args.json:
            print(json.dumps(payload))
        else:
            print(f"gate_open={gate_open} reason={reason}")
        return 0 if gate_open else 1

    if args.acquire_lock:
        ok = acquire_lock(state_dir)
        if not ok:
            print("acquire_lock: lock already present", file=sys.stderr)
            return 1
        return 0

    if args.release_lock:
        ok = release_lock(state_dir)
        if not ok:
            print("release_lock: no lock file present", file=sys.stderr)
            return 1
        return 0

    if args.update_state:
        update_state(state_dir)
        return 0

    if args.increment_sessions:
        increment_sessions(state_dir)
        return 0

    if args.phase == "orient":
        snap = orient(state_dir)
        if args.json:
            print(json.dumps(snap))
        else:
            print(f"phase=orient state_dir={snap['state_dir']}")
            print(f"  rules: {snap['rule_count']}")
            print(f"  MEMORY.md: {snap['memory_md_lines']} lines"
                  f" (exists={snap['memory_md_exists']})")
            print(f"  ACCEPTED.md exists: {snap['accepted_md_exists']}")
            print(f"  oversized files: {len(snap['oversized_files'])}")
            print(f"  orphan files: {len(snap['orphan_files'])}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
