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
  --phase gather [--json] Phase 2: aggregate signal from events.db
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


# ---------------------------------------------------------------------------
# Phase 2 - Gather Signal (Task 5.3)
#
# Aggregate evidence from events.db and (later) narrow JSONL transcripts.
# Per Anthropic Auto Dream design (Section 13.1) + Codex #9 attribution gate
# (Section 13.4):
#
#   For procedural rules:
#     * outcomes WITHOUT attribution.executed_step_ids are DROPPED
#       (cargo-cult prevention — executor bypassed sequence). The CLI gate
#       in vg-orchestrator emit-event already rejects these at write time,
#       but we double-gate at read time so a manually-inserted row can't
#       poison consolidation either.
#     * outcomes WITH non-empty executed_step_ids count toward attributed_pass
#       or attributed_fail by event.outcome column.
#
#   For declarative rules: outcome counted as-is (no attribution required).
#
# Window: bounded by --since-days (default 30) AND --max-events (default
# 5000). Whichever fires first. Matches Anthropic's "last N days OR last
# 100 sessions, whichever smaller" pattern adapted for this repo's scale.
#
# Tier proposal:
#   tier_proposed = "A" iff attributed_pass >= 3 AND contradiction is False
#   contradiction = True iff attributed_pass >= 3 AND attributed_fail >= 3
#                  (PASS streak followed by recurring FAIL → propose retract,
#                  but NEVER auto-retract — Phase 3 invariant)
#
# Test isolation: VG_EVENTS_DB_PATH overrides .vg/events.db location.
# ---------------------------------------------------------------------------

DEFAULT_GATHER_SINCE_DAYS = 30
DEFAULT_GATHER_MAX_EVENTS = 5000


def _events_db_path() -> Path:
    """Resolve events.db path. VG_EVENTS_DB_PATH wins for tests; otherwise
    .vg/events.db at CWD (matches vg-orchestrator/db.py production layout)."""
    env = os.environ.get("VG_EVENTS_DB_PATH")
    if env:
        return Path(env).resolve()
    return Path.cwd() / ".vg" / "events.db"


def _query_outcome_events(db_path: Path, since_days: int,
                          max_events: int) -> list[dict]:
    """Pull bootstrap.outcome_recorded events within [now - since_days, now].

    Returns list of dicts with keys: outcome (column), payload (parsed dict).
    Empty list if db absent or schema missing (graceful degrade — Phase 2 must
    not raise on a fresh repo with no events.db yet).
    """
    if not db_path.exists():
        return []
    import sqlite3
    cutoff = time.time() - since_days * 86400
    # ts column is "%Y-%m-%dT%H:%M:%SZ" UTC string. ORDER BY id DESC LIMIT
    # max_events caps work; we then filter by ts >= cutoff in Python so a
    # malformed ts doesn't break the SQL.
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []
    try:
        try:
            rows = conn.execute(
                "SELECT outcome, payload_json, ts FROM events "
                "WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                ("bootstrap.outcome_recorded", max_events),
            ).fetchall()
        except sqlite3.Error:
            return []
    finally:
        conn.close()

    import datetime
    out: list[dict] = []
    for r in rows:
        ts_str = r["ts"]
        try:
            ts_dt = datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
            ts_epoch = ts_dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        except (ValueError, TypeError):
            ts_epoch = 0.0
        if ts_epoch < cutoff:
            continue
        try:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        except json.JSONDecodeError:
            payload = {}
        out.append({"outcome": r["outcome"], "payload": payload})
    return out


def _classify_outcome(outcome_col: str, payload: dict) -> str:
    """Map (event.outcome column, payload.outcome) -> normalized PASS/FAIL/OTHER.

    Some emitters set outcome via the column (--outcome PASS); others put it
    in the payload (payload['outcome']='success'). We accept both. Anything
    that isn't a clean PASS or FAIL surfaces as OTHER and is ignored for
    tier promotion (tracked separately in raw_event_count).
    """
    raw = (outcome_col or "").upper()
    if raw in {"PASS", "SUCCESS"}:
        return "PASS"
    if raw in {"FAIL", "BLOCK", "FAILURE"}:
        return "FAIL"
    payload_oc = str(payload.get("outcome", "")).lower()
    if payload_oc in {"pass", "success"}:
        return "PASS"
    if payload_oc in {"fail", "failure", "block"}:
        return "FAIL"
    return "OTHER"


def gather(state_dir: Path, since_days: int = DEFAULT_GATHER_SINCE_DAYS,
           max_events: int = DEFAULT_GATHER_MAX_EVENTS) -> dict:
    """Phase 2 - aggregate rule signals from events.db.

    Returns dict with:
      phase: "gather"
      events_window_sec
      events_processed   # rows kept after window + parse
      rule_signals: { slug: { rule_type, attributed_pass, attributed_fail,
                              dropped_no_attribution, tier_proposed,
                              contradiction } }
      transcript_signals  # placeholder for future narrow-grep work
      events_db: str
    """
    db_path = _events_db_path()
    events = _query_outcome_events(db_path, since_days, max_events)

    rule_signals: dict[str, dict] = {}
    dropped_total = 0

    for ev in events:
        payload = ev["payload"] or {}
        slug = payload.get("slug") or payload.get("rule_id")
        if not slug:
            continue
        rule_type = payload.get("rule_type", "declarative")
        sig = rule_signals.setdefault(slug, {
            "rule_type": rule_type,
            "attributed_pass": 0,
            "attributed_fail": 0,
            "dropped_no_attribution": 0,
            "tier_proposed": None,
            "contradiction": False,
        })
        # Keep the most-specific rule_type if we see it later (procedural
        # wins over declarative — declarative is the safe default fallback
        # for legacy events without rule_type).
        if rule_type == "procedural":
            sig["rule_type"] = "procedural"

        # Codex #9 attribution gate (read-side enforcement):
        #   procedural rules require non-empty executed_step_ids.
        if sig["rule_type"] == "procedural":
            attribution = payload.get("attribution") or {}
            executed = (
                attribution.get("executed_step_ids")
                if isinstance(attribution, dict) else None
            )
            if not executed:
                sig["dropped_no_attribution"] += 1
                dropped_total += 1
                continue

        norm = _classify_outcome(ev["outcome"], payload)
        if norm == "PASS":
            sig["attributed_pass"] += 1
        elif norm == "FAIL":
            sig["attributed_fail"] += 1
        # OTHER -> intentionally ignored (no signal, no drop counter)

    # Tier proposal pass — done after counting so contradiction wins over
    # tier-A promotion when both fire.
    for slug, sig in rule_signals.items():
        ap = sig["attributed_pass"]
        af = sig["attributed_fail"]
        if ap >= 3 and af >= 3:
            sig["contradiction"] = True
            sig["tier_proposed"] = None  # consolidate phase will warn-only
        elif ap >= 3 and af == 0:
            sig["tier_proposed"] = "A"
        # else: leave tier_proposed=None (insufficient evidence)

    return {
        "phase": "gather",
        "events_db": str(db_path),
        "events_window_sec": since_days * 86400,
        "events_processed": len(events),
        "events_dropped_no_attribution": dropped_total,
        "rule_signals": rule_signals,
        "transcript_signals": [],  # placeholder; narrow-grep deferred
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap consolidation gate (Task 5.1)")
    parser.add_argument("--check-gate", action="store_true", help="Check trigger gate")
    parser.add_argument("--acquire-lock", action="store_true", help="Acquire .consolidation.lock")
    parser.add_argument("--release-lock", action="store_true", help="Release .consolidation.lock")
    parser.add_argument("--update-state", action="store_true",
                        help="Update state.json after successful consolidation")
    parser.add_argument("--increment-sessions", action="store_true",
                        help="Increment sessions_since_last counter")
    parser.add_argument("--phase", choices=["orient", "gather"], default=None,
                        help="Run a 4-phase consolidation step")
    parser.add_argument("--since-days", type=int, default=DEFAULT_GATHER_SINCE_DAYS,
                        help="Phase 2 window in days (default 30)")
    parser.add_argument("--max-events", type=int, default=DEFAULT_GATHER_MAX_EVENTS,
                        help="Phase 2 max events to scan (default 5000)")
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

    if args.phase == "gather":
        report = gather(state_dir, args.since_days, args.max_events)
        if args.json:
            print(json.dumps(report))
        else:
            print(f"phase=gather events_db={report['events_db']}")
            print(f"  events_processed: {report['events_processed']}")
            print(f"  events_dropped_no_attribution: "
                  f"{report['events_dropped_no_attribution']}")
            print(f"  rule_signals:")
            for slug, sig in sorted(report["rule_signals"].items()):
                print(f"    {slug}: pass={sig['attributed_pass']} "
                      f"fail={sig['attributed_fail']} "
                      f"tier={sig['tier_proposed']} "
                      f"contradiction={sig['contradiction']}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
