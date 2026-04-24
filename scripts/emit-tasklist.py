#!/usr/bin/env python3
"""
emit-tasklist.py — Task-list visibility helper (2026-04-24).

User requirement: "khởi tạo 1 flow nào đều phải show được Task để AI bám vào
đó mà làm". Every pipeline command entry step MUST call this helper so:
  1. User sees the authoritative step list at flow start
  2. Orchestrator emits {command}.tasklist_shown event for contract verification
  3. AI has a visible contract to follow (not a hidden internal decision)

Runs filter-steps.py to get profile-filtered step list, prints it to stdout,
emits event to orchestrator with step_list + count payload.

Usage:
  python emit-tasklist.py --command vg:build --profile web-fullstack --phase 7.14

Exit codes:
  0 — success, event emitted, list printed
  1 — filter-steps failed
  2 — orchestrator emit-event failed (still prints list so user sees something)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
FILTER_STEPS = REPO_ROOT / ".claude" / "scripts" / "filter-steps.py"
ORCHESTRATOR = REPO_ROOT / ".claude" / "scripts" / "vg-orchestrator"


def _resolve_command_file(command: str) -> Path:
    # "vg:build" → .claude/commands/vg/build.md
    if ":" in command:
        ns, name = command.split(":", 1)
        return REPO_ROOT / ".claude" / "commands" / ns / f"{name}.md"
    return REPO_ROOT / ".claude" / "commands" / f"{command}.md"


def _get_step_list(command: str, profile: str) -> list[str]:
    cmd_file = _resolve_command_file(command)
    if not cmd_file.exists():
        print(f"⛔ Command file not found: {cmd_file}", file=sys.stderr)
        return []
    proc = subprocess.run(
        [sys.executable, str(FILTER_STEPS),
         "--command", str(cmd_file),
         "--profile", profile,
         "--output-ids"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print(f"⛔ filter-steps failed: {proc.stderr}", file=sys.stderr)
        return []
    ids = proc.stdout.strip()
    return [s.strip() for s in ids.split(",") if s.strip()] if ids else []


def _emit_event(command: str, phase: str, steps: list[str]) -> bool:
    """Emit {cmd_short}.tasklist_shown event with step payload."""
    cmd_short = command.replace("vg:", "").replace(":", "_")
    event_type = f"{cmd_short}.tasklist_shown"
    payload = {
        "step_count": len(steps),
        "steps": steps,
        "command": command,
        "phase": phase,
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(ORCHESTRATOR), "emit-event",
             event_type,
             "--payload", json.dumps(payload)],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0
    except Exception as exc:
        print(f"⚠ emit-event failed: {exc}", file=sys.stderr)
        return False


def _print_tasklist(command: str, phase: str, profile: str, steps: list[str]) -> None:
    print("")
    print("━" * 70)
    print(f"  {command} — Phase {phase} — Profile {profile}")
    print(f"  {len(steps)} steps to execute:")
    print("━" * 70)
    for i, step in enumerate(steps, 1):
        print(f"  {i:2d}. {step}")
    print("━" * 70)
    print("  AI MUST touch .step-markers/{name}.done for EACH step above.")
    print("  Skipping = contract violation at Stop hook.")
    print("━" * 70)
    print("")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--command", required=True, help="e.g. vg:build")
    ap.add_argument("--profile", required=True, help="e.g. web-fullstack")
    ap.add_argument("--phase", required=True, help="e.g. 7.14")
    ap.add_argument("--no-emit", action="store_true", help="print list only")
    args = ap.parse_args()

    steps = _get_step_list(args.command, args.profile)
    if not steps:
        return 1

    _print_tasklist(args.command, args.phase, args.profile, steps)

    if args.no_emit:
        return 0

    if not _emit_event(args.command, args.phase, steps):
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
