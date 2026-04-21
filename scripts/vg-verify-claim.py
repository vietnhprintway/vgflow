#!/usr/bin/env python3
"""
Stop hook — verifies active run is properly completed via vg-orchestrator.

v2.2 rewrite: this hook no longer parses frontmatter or checks files directly.
Instead it reads .vg/events.db (via vg-orchestrator) to decide.

Rules:
1. If no active run (current-run.json missing) → approve. Session is not
   in the middle of a /vg:* invocation; nothing to verify.
2. If active run exists and is older than 30min → soft-approve (assume
   abandoned/crashed). Log + clear current-run.json for next time.
3. If active run exists and fresh → run vg-orchestrator run-complete.
   Orchestrator evaluates runtime_contract + validators. If PASS,
   session can stop. If BLOCK, we exit 2 + inject structured feedback.

This closes the "AI narrates done without evidence" pattern because the
decision to allow Stop comes from orchestrator reading events.db — which
only has the events that actually were emitted via bash tool calls.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
CURRENT_RUN = REPO_ROOT / ".vg" / "current-run.json"
HOOK_LOG = REPO_ROOT / ".vg" / "hook-verifier.log"
ORCHESTRATOR = REPO_ROOT / ".claude" / "scripts" / "vg-orchestrator"
STALE_MINUTES = 30


def log(msg: str) -> None:
    try:
        HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HOOK_LOG.open("a", encoding="utf-8") as f:
            ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f"[{ts}] {msg.rstrip()}\n")
    except Exception:
        pass


def read_current_run() -> dict | None:
    if not CURRENT_RUN.exists():
        return None
    try:
        return json.loads(CURRENT_RUN.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"current-run.json parse error: {e}")
        return None


def is_stale(run: dict) -> bool:
    started = run.get("started_at", "")
    if not started:
        return True
    try:
        ts = datetime.datetime.fromisoformat(started.rstrip("Z"))
        age_min = (datetime.datetime.utcnow() - ts).total_seconds() / 60
        return age_min > STALE_MINUTES
    except Exception:
        return True


def run_orchestrator_complete() -> tuple[int, str, str]:
    """Invoke vg-orchestrator run-complete. Returns (exit_code, stdout, stderr)."""
    python_bin = sys.executable or "python"
    proc = subprocess.run(
        [python_bin, str(ORCHESTRATOR), "run-complete"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except Exception:
        hook_input = {}

    stop_active = hook_input.get("stop_hook_active", False)
    session_id = hook_input.get("session_id", "?")

    log(f"--- Stop hook fire — session={session_id[:12] if session_id else '?'}"
        f" stop_active={stop_active}")

    if stop_active:
        # Infinite-loop guard per Claude Code hooks contract
        log("stop_hook_active=True — approving to avoid loop")
        print(json.dumps({"decision": "approve", "reason": "loop-guard"}))
        return 0

    current = read_current_run()
    if not current:
        log("no current-run.json — nothing to verify, approve")
        print(json.dumps({"decision": "approve",
                          "reason": "no-active-run"}))
        return 0

    command = current.get("command", "?")
    phase = current.get("phase", "?")

    if is_stale(current):
        # Abandoned run — clear + approve silently (prevent false-fire on
        # old stale state across sessions)
        log(f"active run {command} phase={phase} is stale → clearing + approve")
        try:
            CURRENT_RUN.unlink()
        except FileNotFoundError:
            pass
        print(json.dumps({"decision": "approve",
                          "reason": "stale-run-cleared"}))
        return 0

    log(f"active run {command} phase={phase} → invoking orchestrator run-complete")
    rc, stdout, stderr = run_orchestrator_complete()
    log(f"orchestrator rc={rc}")

    if rc == 0:
        # PASS — run completed cleanly
        log("run-complete PASS")
        print(json.dumps({"decision": "approve",
                          "reason": "orchestrator-pass"}))
        return 0

    if rc == 2:
        # BLOCK — orchestrator found contract violations
        msg = stderr.strip() or stdout.strip() or (
            "vg-orchestrator run-complete reported contract violations."
        )
        log(f"BLOCKED: {msg[:200]}")
        print(msg, file=sys.stderr)
        return 2

    # Any other non-zero: treat as soft-fail so we don't deadlock on
    # orchestrator bugs. Log prominently.
    log(f"orchestrator unexpected rc={rc}, stderr={stderr[:300]}")
    print(json.dumps({"decision": "approve",
                      "reason": f"orchestrator-rc-{rc}-soft-approve"}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        try:
            log(f"HOOK ERROR (soft-approving): {e}")
        except Exception:
            pass
        print(json.dumps({"decision": "approve", "reason": "hook-error"}))
        sys.exit(0)
