#!/usr/bin/env python3
"""
Validator: build-crossai-required.py — OHOK-7 MANDATORY enforcement.

Post-/vg:build completion must include ≥1 CrossAI verification iteration.
This is the WIRED-OR-NOTHING gate that prevents AI from treating the
"run CrossAI after build" instruction as a promise/docs-only requirement.

Required events in the current run's event stream:

1. At least 1 `build.crossai_iteration_started` event (proves loop ran).
2. One of these terminal events (proves loop reached an accepted end state):
   - `build.crossai_loop_complete` — CrossAI PASS before max iterations
   - `build.crossai_loop_exhausted` — hit max (5) iterations, user decides
   - `build.crossai_loop_user_override` — user chose to defer/skip after
                                            exhaustion (logs HARD debt)

Missing either → BLOCK with explicit command to run the loop.

This validator is dispatched by the orchestrator at `/vg:build run-complete`.
Registered in COMMAND_VALIDATORS['vg:build'].
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import Evidence, Output, timer, emit_and_exit, find_phase_dir  # noqa: E402

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
DB_PATH = REPO_ROOT / ".vg" / "events.db"
CURRENT_RUN_FILE = REPO_ROOT / ".vg" / "current-run.json"

TERMINAL_EVENTS = {
    "build.crossai_loop_complete",
    "build.crossai_loop_exhausted",
    "build.crossai_loop_user_override",
}


def _read_current_run_id() -> str | None:
    try:
        return json.loads(CURRENT_RUN_FILE.read_text(encoding="utf-8")
                          )["run_id"]
    except Exception:
        return None


def _count_events_in_run(run_id: str, event_types: set[str]) -> dict[str, int]:
    """Return counts of each event type for this run."""
    if not DB_PATH.exists():
        return {e: 0 for e in event_types}
    counts = {e: 0 for e in event_types}
    conn = sqlite3.connect(str(DB_PATH))
    try:
        placeholders = ",".join("?" for _ in event_types)
        rows = conn.execute(
            f"SELECT event_type, COUNT(*) FROM events "
            f"WHERE run_id = ? AND event_type IN ({placeholders}) "
            f"GROUP BY event_type",
            [run_id, *event_types],
        ).fetchall()
        for et, n in rows:
            counts[et] = n
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    args = ap.parse_args()

    out = Output(validator="build-crossai-required")
    with timer(out):
        phase_dir = find_phase_dir(args.phase)
        if not phase_dir:
            # No phase dir — phase-exists validator will catch it upstream.
            emit_and_exit(out)

        run_id = _read_current_run_id()
        if not run_id:
            # No active run when run-complete validators fire would be unusual.
            # Phase-exists / other validators fire first; if we're here without
            # a run, skip quietly (loop requirement doesn't apply).
            emit_and_exit(out)

        check_events = TERMINAL_EVENTS | {"build.crossai_iteration_started"}
        counts = _count_events_in_run(run_id, check_events)

        iter_count = counts.get("build.crossai_iteration_started", 0)
        terminal_count = sum(counts.get(e, 0) for e in TERMINAL_EVENTS)

        if iter_count == 0:
            out.add(Evidence(
                type="crossai_loop_never_ran",
                message=(
                    "/vg:build run-complete without any "
                    "build.crossai_iteration_started event. OHOK-7 requires "
                    "MANDATORY CrossAI build verification after wave execution "
                    "— this is NOT a promise, NOT optional. Missing events.db "
                    "evidence = loop didn't actually run."
                ),
                expected="≥1 build.crossai_iteration_started event for this run",
                actual=f"iteration_started events = {iter_count}",
                fix_hint=(
                    "Run the loop now + re-attempt run-complete:\n"
                    "  python .claude/scripts/vg-build-crossai-loop.py "
                    f"--phase {args.phase} --iteration 1 --max-iterations 5\n"
                    "If it exits 1 (blocks found), dispatch a Sonnet fix "
                    "subagent with the findings JSON, apply fixes, commit, "
                    "then re-invoke with --iteration 2. Repeat up to 5x.\n"
                    "If exit 0 → loop is clean; main Claude emits "
                    "build.crossai_loop_complete to satisfy this gate.\n"
                    "If 5 hit without clean → prompt user for: continue / "
                    "defer / skip+debt."
                ),
            ))
            emit_and_exit(out)

        if terminal_count == 0:
            # Loop ran but never reached an accepted terminal state
            out.add(Evidence(
                type="crossai_loop_no_terminal",
                message=(
                    f"Loop ran {iter_count} iteration(s) but no terminal "
                    f"event emitted (loop_complete / loop_exhausted / "
                    f"loop_user_override). Build cannot complete without "
                    f"the caller (main Claude) deciding how the loop ends."
                ),
                expected="one of: " + ", ".join(sorted(TERMINAL_EVENTS)),
                actual=f"iterations={iter_count}, terminal events=0",
                fix_hint=(
                    "After running iterations, main Claude must emit ONE of:\n"
                    "  - build.crossai_loop_complete (if iteration exit 0)\n"
                    "  - build.crossai_loop_exhausted (if hit --max)\n"
                    "  - build.crossai_loop_user_override (if user deferred)\n"
                    "via: python .claude/scripts/vg-orchestrator emit-event "
                    "<event_type> --payload '{...}'"
                ),
            ))
            emit_and_exit(out)

        # Iterations ran + terminal event present → PASS (no evidence means
        # clean pass per Output class semantics; adding evidence would
        # escalate to BLOCK).

    emit_and_exit(out)


if __name__ == "__main__":
    main()
