"""
vg-orchestrator CLI dispatcher.

Entry point for ALL /vg:* pipeline transitions. Skill-MD bash blocks call
subcommands here; AI cannot legitimately advance pipeline state without
going through this binary.

Subcommands:
  run-start <command> <phase> [args...]
  run-status
  run-complete [outcome]
  run-abort --reason <text>
  run-resume
  run-repair [--force]
  emit-event <event_type> [--payload JSON]
  mark-step <namespace> <step_name>
  wave-start <wave_n>
  wave-complete <wave_n> < evidence.json   (reads stdin or --evidence-file)
  validate <validator_name> [args...]
  verify-hash-chain [--since-id N]
  query-events [--phase X] [--event-type Y] [--run-id Z]
  override --flag <f> --reason <text>

Exit codes:
  0 = success
  1 = validation/state error (AI should read stderr + retry)
  2 = hook-blocking (forces Claude Code Stop to block)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Ensure package-relative imports work when run via `python -m vg_orchestrator`
# or `python .claude/scripts/vg-orchestrator/__main__.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402
import contracts  # noqa: E402
import state as state_mod  # noqa: E402
import evidence  # noqa: E402


def _git_sha() -> str | None:
    import subprocess
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def cmd_run_start(args) -> int:
    """Write runs row + emit run.started. Return run_id on stdout."""
    if state_mod.read_current_run():
        # Existing active run — fail loud rather than overwrite silently
        active = state_mod.read_current_run()
        print(f"⛔ Active run exists: {active.get('command')} "
              f"phase={active.get('phase')}. Abort or complete first.",
              file=sys.stderr)
        return 1

    session_id = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    extra_str = " ".join(args.extra) if isinstance(args.extra, list) else (args.extra or "")
    run_id = db.create_run(
        command=args.command,
        phase=args.phase,
        args=extra_str,
        session_id=session_id,
        git_sha=_git_sha(),
    )

    state_mod.write_current_run({
        "run_id": run_id,
        "command": args.command,
        "phase": args.phase,
        "args": extra_str,
        "started_at": _now_iso(),
    })

    db.append_event(
        run_id=run_id,
        event_type="run.started",
        phase=args.phase,
        command=args.command,
        actor="orchestrator",
        outcome="INFO",
        payload={"args": extra_str, "git_sha": _git_sha()},
    )
    # Also emit {cmd}.started for backward compat with contract declarations
    short_cmd = args.command.replace("vg:", "")
    db.append_event(
        run_id=run_id,
        event_type=f"{short_cmd}.started",
        phase=args.phase,
        command=args.command,
        actor="orchestrator",
        outcome="INFO",
        payload={},
    )
    print(run_id)
    return 0


def cmd_run_status(_args) -> int:
    current = state_mod.read_current_run()
    if not current:
        print("no-active-run")
        return 0
    run = db.get_run(current["run_id"])
    print(json.dumps({"current_run": current, "run_row": run}, indent=2,
                     default=str))
    return 0


def cmd_run_complete(args) -> int:
    """Verify runtime_contract evidence, emit completion event, clear current-run."""
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run to complete.", file=sys.stderr)
        return 1

    run_id = current["run_id"]
    command = current["command"]
    phase = current["phase"]
    run_args = current.get("args", "")

    contract = contracts.parse(command)
    verdict, violations = _verify_contract(contract, run_id, command, phase,
                                           run_args)

    outcome = "PASS" if verdict else args.outcome or "BLOCK"
    # {cmd}.completed must be emitted BY THE SKILL before run-complete so we
    # can verify it here. Orchestrator emits only run.completed/run.blocked.
    db.append_event(
        run_id=run_id,
        event_type="run.completed" if verdict else "run.blocked",
        phase=phase,
        command=command,
        actor="orchestrator",
        outcome=outcome,
        payload={"violations": violations} if violations else {},
    )

    # Outcome attribution — any bootstrap.rule_fired events from this run
    # inherit the run verdict. This closes the learning loop that was dead
    # in v1 (success_count / fail_count stayed 0 forever because nobody
    # emitted bootstrap.outcome_recorded).
    _record_rule_outcomes(run_id, command, phase, verdict)

    if verdict:
        db.complete_run(run_id, outcome="PASS")
        state_mod.clear_current_run()
        print(f"✓ {command} phase={phase} PASS")
        return 0

    # Verdict failed — keep current_run so user/AI can inspect + retry
    print(_format_block_message(command, phase, violations), file=sys.stderr)
    return 2


def cmd_run_abort(args) -> int:
    current = state_mod.read_current_run()
    if not current:
        print("no-active-run")
        return 0
    db.append_event(
        run_id=current["run_id"],
        event_type="run.aborted",
        phase=current["phase"],
        command=current["command"],
        actor="user",
        outcome="INFO",
        payload={"reason": args.reason},
    )
    db.complete_run(current["run_id"], outcome="ABORTED")
    state_mod.clear_current_run()
    print(f"aborted: {args.reason}")
    return 0


def cmd_emit_event(args) -> int:
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run. Call run-start first.", file=sys.stderr)
        return 1

    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"⛔ Invalid payload JSON: {e}", file=sys.stderr)
            return 1

    evt = db.append_event(
        run_id=current["run_id"],
        event_type=args.event_type,
        phase=current["phase"],
        command=current["command"],
        actor=args.actor,
        outcome=args.outcome,
        step=args.step,
        payload=payload,
    )
    print(evt["this_hash"][:16])
    return 0


def cmd_mark_step(args) -> int:
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run. Call run-start first.", file=sys.stderr)
        return 1

    phase_dir = contracts.resolve_phase_dir(current["phase"])
    if not phase_dir:
        print(f"⛔ Phase dir not found for phase={current['phase']}",
              file=sys.stderr)
        return 1

    marker = state_mod.mark_step(phase_dir, args.namespace, args.step_name)
    db.append_event(
        run_id=current["run_id"],
        event_type="step.marked",
        phase=current["phase"],
        command=current["command"],
        actor="orchestrator",
        outcome="INFO",
        step=args.step_name,
        payload={"namespace": args.namespace, "marker": str(marker)},
    )
    print(f"marked: {args.namespace}/{args.step_name}")
    return 0


def cmd_verify_hash_chain(args) -> int:
    ok, broken_at, reason = db.verify_hash_chain(since_id=args.since_id or 0)
    if ok:
        print("hash-chain: OK")
        return 0
    print(f"⛔ hash-chain BROKEN at id={broken_at}: {reason}",
          file=sys.stderr)
    current = state_mod.read_current_run()
    if current:
        db.append_event(
            run_id=current["run_id"],
            event_type="integrity.compromised",
            phase=current["phase"],
            command=current["command"],
            actor="orchestrator",
            outcome="BLOCK",
            payload={"broken_at_id": broken_at, "reason": reason},
        )
    return 2


def cmd_wave_start(args) -> int:
    """Register new wave in active build run. Emit wave.started event.
    Same-wave re-start rejected (idempotency)."""
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run. Call run-start first.", file=sys.stderr)
        return 1
    if current["command"] != "vg:build":
        print(f"⛔ wave-start only valid in vg:build runs, not "
              f"{current['command']}", file=sys.stderr)
        return 1

    # Check same wave already started
    existing = db.query_events(
        run_id=current["run_id"], event_type="wave.started",
    )
    for e in existing:
        try:
            if json.loads(e["payload_json"]).get("wave") == args.wave_n:
                print(f"⛔ wave {args.wave_n} already started in this run",
                      file=sys.stderr)
                return 1
        except Exception:
            continue

    db.append_event(
        run_id=current["run_id"],
        event_type="wave.started",
        phase=current["phase"],
        command=current["command"],
        actor="orchestrator",
        outcome="INFO",
        payload={"wave": args.wave_n},
    )
    print(f"wave {args.wave_n} started")
    return 0


def cmd_wave_complete(args) -> int:
    """Read evidence_json from stdin or --evidence-file. Validate schema.
    Run wave-attribution validator. Emit wave.completed or wave.blocked.
    Same-wave re-complete with different evidence = BLOCK (integrity)."""
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run", file=sys.stderr)
        return 1

    # Load evidence
    if args.evidence_file:
        try:
            raw = Path(args.evidence_file).read_text(encoding="utf-8")
        except Exception as e:
            print(f"⛔ evidence file read error: {e}", file=sys.stderr)
            return 1
    else:
        raw = sys.stdin.read()

    try:
        evidence_data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⛔ evidence_json parse error: {e}", file=sys.stderr)
        return 1

    if evidence_data.get("wave") != args.wave_n:
        print(f"⛔ evidence.wave ({evidence_data.get('wave')}) != "
              f"--wave ({args.wave_n})", file=sys.stderr)
        return 1

    # Idempotency: re-complete with identical evidence = no-op PASS
    prior_completes = db.query_events(
        run_id=current["run_id"], event_type="wave.completed",
    )
    for e in prior_completes:
        pl = json.loads(e["payload_json"])
        if pl.get("wave") == args.wave_n:
            if pl.get("evidence_hash") == _hash_evidence(raw):
                print(f"wave {args.wave_n} already completed (idempotent)")
                return 0
            else:
                print(f"⛔ wave {args.wave_n} re-complete with DIFFERENT "
                      f"evidence → integrity violation", file=sys.stderr)
                db.append_event(
                    run_id=current["run_id"],
                    event_type="integrity.compromised",
                    phase=current["phase"],
                    command=current["command"],
                    actor="orchestrator",
                    outcome="BLOCK",
                    payload={"wave": args.wave_n,
                             "reason": "wave-complete evidence diverged"},
                )
                return 2

    # Invoke wave-attribution validator
    import subprocess
    validator = (Path(__file__).parent.parent / "validators" /
                 "wave-attribution.py")
    if not validator.exists():
        print("⛔ wave-attribution validator missing", file=sys.stderr)
        return 1

    r = subprocess.run(
        [sys.executable, str(validator),
         "--phase", current["phase"], "--wave", str(args.wave_n)],
        input=raw, capture_output=True, text=True, timeout=60,
    )

    if r.returncode != 0:
        # Validator BLOCKED — emit wave.blocked with violations
        try:
            verdict = json.loads(r.stdout)
        except Exception:
            verdict = {"verdict": "BLOCK",
                       "evidence": [{"message": r.stdout[:200]}]}

        db.append_event(
            run_id=current["run_id"],
            event_type="wave.blocked",
            phase=current["phase"],
            command=current["command"],
            actor="validator",
            outcome="BLOCK",
            payload={"wave": args.wave_n,
                     "evidence_hash": _hash_evidence(raw),
                     "violations": verdict.get("evidence", [])},
        )
        print(f"⛔ wave {args.wave_n} BLOCK — wave-attribution rejected evidence",
              file=sys.stderr)
        print(r.stdout, file=sys.stderr)
        return 2

    # PASS
    db.append_event(
        run_id=current["run_id"],
        event_type="wave.completed",
        phase=current["phase"],
        command=current["command"],
        actor="orchestrator",
        outcome="PASS",
        payload={"wave": args.wave_n,
                 "evidence_hash": _hash_evidence(raw),
                 "task_count": len(evidence_data.get("tasks", [])),
                 "commit_count": len(evidence_data.get("commits", []))},
    )
    print(f"✓ wave {args.wave_n} PASS")
    return 0


def _hash_evidence(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cmd_validate(args) -> int:
    """Run a named validator standalone (not at run-complete).
    Useful for skill-MD to check a gate mid-flow."""
    import subprocess
    validator = (Path(__file__).parent.parent / "validators" /
                 f"{args.validator_name}.py")
    if not validator.exists():
        print(f"⛔ validator not found: {args.validator_name}",
              file=sys.stderr)
        return 1

    current = state_mod.read_current_run()
    phase = args.phase or (current["phase"] if current else "")
    if not phase:
        print("⛔ --phase required when no active run", file=sys.stderr)
        return 1

    call_args = [sys.executable, str(validator), "--phase", phase]
    call_args.extend(args.forward or [])

    stdin_data = sys.stdin.read() if args.stdin else None
    r = subprocess.run(call_args, input=stdin_data, capture_output=True,
                       text=True, timeout=60)
    # Forward validator output verbatim
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip(), file=sys.stderr)
    return r.returncode


def cmd_override(args) -> int:
    """Log override.used event for this run + append to OVERRIDE-DEBT.md.
    Satisfies forbidden_without_override contract check at run-complete."""
    current = state_mod.read_current_run()
    if not current:
        print("⛔ No active run", file=sys.stderr)
        return 1

    if len(args.reason.strip()) < 4:
        print("⛔ reason must be ≥4 chars", file=sys.stderr)
        return 1

    ev = db.append_event(
        run_id=current["run_id"],
        event_type="override.used",
        phase=current["phase"],
        command=current["command"],
        actor="user",
        outcome="INFO",
        payload={"flag": args.flag, "reason": args.reason},
    )

    # Append human-readable entry to OVERRIDE-DEBT.md
    register = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()) / \
               ".vg" / "OVERRIDE-DEBT.md"
    try:
        register.parent.mkdir(parents=True, exist_ok=True)
        with register.open("a", encoding="utf-8") as f:
            f.write(
                f"\n- id: OD-{ev['id']:03d}\n"
                f"  logged_at: {ev['ts']}\n"
                f"  command: {current['command']}\n"
                f"  phase: \"{current['phase']}\"\n"
                f"  flag: {args.flag}\n"
                f"  reason: \"{args.reason}\"\n"
                f"  git_sha: {_git_sha() or 'unknown'}\n"
                f"  status: active\n"
            )
    except Exception:
        pass

    print(f"OD-{ev['id']:03d} logged: {args.flag}")
    return 0


def cmd_run_resume(args) -> int:
    """Resume interrupted run. Reads current-run.json, verifies runs table
    row is incomplete, re-prints status. No destructive actions."""
    current = state_mod.read_current_run()
    if not current:
        print("no-active-run")
        return 0

    run = db.get_run(current["run_id"])
    if not run:
        print("⛔ current-run.json refs run_id not in runs table — "
              "state corrupted. Use run-repair.", file=sys.stderr)
        return 2

    if run.get("completed_at"):
        print(f"⛔ run {current['run_id'][:8]} already completed at "
              f"{run['completed_at']}. Current-run.json stale.",
              file=sys.stderr)
        return 2

    # Count events + last event type for context
    events = db.query_events(run_id=current["run_id"])
    last_event = events[-1] if events else None
    print(f"resumed: {current['command']} phase={current['phase']} "
          f"events={len(events)}")
    if last_event:
        print(f"last event: {last_event['event_type']} @ {last_event['ts']}")

    db.append_event(
        run_id=current["run_id"], event_type="run.resumed",
        phase=current["phase"], command=current["command"],
        actor="user", outcome="INFO",
        payload={"events_replayed": len(events)},
    )
    return 0


def cmd_run_repair(args) -> int:
    """Reconcile inconsistent state. Default: report + ask. With --force:
    - If current-run.json refs run_id not in runs table → clear current-run
    - If runs table has orphaned active runs → mark them aborted
    Integrity checks remain manual (hash chain tamper requires human)."""
    current = state_mod.read_current_run()
    issues = []

    if current:
        run = db.get_run(current["run_id"])
        if not run:
            issues.append({
                "type": "current-run-no-db-row",
                "detail": f"run_id {current['run_id']} not in runs table",
                "fix": "clear current-run.json",
            })
        elif run.get("completed_at"):
            issues.append({
                "type": "current-run-stale",
                "detail": f"run completed at {run['completed_at']}",
                "fix": "clear current-run.json",
            })

    # Orphaned active runs older than 1 day
    import sqlite3
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        orphans = conn.execute(
            "SELECT run_id, command, phase, started_at FROM runs "
            "WHERE completed_at IS NULL AND "
            "started_at < datetime('now', '-1 day')"
        ).fetchall()
        for o in orphans:
            issues.append({
                "type": "orphaned-run",
                "detail": (f"{o['command']} phase={o['phase']} "
                           f"started {o['started_at']}"),
                "fix": "mark aborted",
                "run_id": o["run_id"],
            })
    finally:
        conn.close()

    if not issues:
        print("no-repairs-needed")
        return 0

    print(f"{len(issues)} issue(s) detected:")
    for i in issues:
        print(f"  [{i['type']}] {i['detail']} → fix: {i['fix']}")

    if not args.force:
        print("\nRe-run with --force to apply fixes.")
        return 1

    # Apply fixes
    for i in issues:
        if i["type"] in ("current-run-no-db-row", "current-run-stale"):
            state_mod.clear_current_run()
            print(f"  ✓ cleared current-run.json")
        elif i["type"] == "orphaned-run":
            db.complete_run(i["run_id"], outcome="ABORTED_STALE")
            db.append_event(
                run_id=i["run_id"], event_type="run.aborted",
                phase="", command="", actor="orchestrator",
                outcome="INFO", payload={"reason": "orphaned by repair"},
            )
            print(f"  ✓ marked {i['run_id'][:8]} aborted")

    print("\nrepair complete")
    return 0


def cmd_query_events(args) -> int:
    events = db.query_events(
        run_id=args.run_id,
        event_type=args.event_type,
        phase=args.phase,
        command=args.command,
        since=args.since,
        limit=args.limit,
    )
    print(json.dumps(events, indent=2, default=str))
    return 0


def _record_rule_outcomes(run_id: str, command: str, phase: str,
                          run_passed: bool) -> None:
    """Emit bootstrap.outcome_recorded for every rule that fired this run.
    outcome=success if run passed, fail if run blocked.
    Closes the learning loop that never closed in v1."""
    rule_fires = db.query_events(run_id=run_id,
                                 event_type="bootstrap.rule_fired")
    if not rule_fires:
        return

    seen_rules = set()
    for fire in rule_fires:
        try:
            pl = json.loads(fire["payload_json"])
        except Exception:
            continue
        rule_id = pl.get("rule_id")
        if not rule_id or rule_id in seen_rules:
            continue
        seen_rules.add(rule_id)

        db.append_event(
            run_id=run_id,
            event_type="bootstrap.outcome_recorded",
            phase=phase,
            command=command,
            actor="orchestrator",
            outcome="PASS" if run_passed else "BLOCK",
            payload={
                "rule_id": rule_id,
                "outcome": "success" if run_passed else "fail",
                "run_id": run_id,
            },
        )


COMMAND_VALIDATORS = {
    "vg:scope": ["phase-exists", "context-structure"],
    "vg:blueprint": ["phase-exists", "context-structure", "plan-granularity",
                     "task-goal-binding"],
    "vg:build": ["phase-exists"],  # wave-attribution runs per wave-complete
    # Review doesn't enforce goal-coverage — tests land in /vg:test, so review
    # always fails before tests exist. Enforcement moved to /vg:test + /vg:accept
    # where tests MUST exist. Review's in-skill 0b gate warns advisory only.
    # runtime-evidence: BLOCK if Playwright specs exist but not executed
    # (anti-rationalization — prevents AI from certifying "code evidence only").
    "vg:review": ["phase-exists", "runtime-evidence"],
    "vg:test": ["phase-exists", "goal-coverage", "runtime-evidence"],
    "vg:accept": ["phase-exists", "event-reconciliation",
                  "override-debt-balance", "runtime-evidence"],
}


QUARANTINE_FILE = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()
                       ) / ".vg" / "validator-quarantine.json"
QUARANTINE_THRESHOLD = 3  # consecutive crashes OR BLOCKs → auto-disable


def _load_quarantine() -> dict:
    if not QUARANTINE_FILE.exists():
        return {}
    try:
        return json.loads(QUARANTINE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_quarantine(state: dict) -> None:
    try:
        QUARANTINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUARANTINE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _quarantine_record(v_name: str, verdict: str) -> bool:
    """Update quarantine state; return True if validator now quarantined."""
    state = _load_quarantine()
    entry = state.setdefault(v_name, {"consecutive_fails": 0, "disabled": False})
    if verdict in ("BLOCK", "CRASH"):
        entry["consecutive_fails"] = entry.get("consecutive_fails", 0) + 1
        entry["last_fail_at"] = _now_iso()
        if entry["consecutive_fails"] >= QUARANTINE_THRESHOLD and not entry["disabled"]:
            entry["disabled"] = True
            entry["disabled_at"] = _now_iso()
    else:  # PASS / WARN — reset counter AND re-enable (validator proved healthy)
        entry["consecutive_fails"] = 0
        if entry.get("disabled"):
            entry["disabled"] = False
            entry["re_enabled_at"] = _now_iso()
    _save_quarantine(state)
    return entry["disabled"]


def _run_validators(command: str, phase: str, run_id: str,
                    run_args: str) -> list[dict]:
    """Dispatch applicable validators for this command.
    Returns list of BLOCK violations (WARN gets logged as events, doesn't block).

    Quarantine: a validator that BLOCKs 3 times in a row gets auto-disabled to
    prevent a single broken validator stalling the whole pipeline. Reset with
    manual edit of .vg/validator-quarantine.json or one PASS/WARN verdict."""
    import subprocess
    validator_dir = Path(__file__).parent.parent / "validators"
    validators = COMMAND_VALIDATORS.get(command, [])
    block_results = []
    quarantine = _load_quarantine()

    for v_name in validators:
        v_path = validator_dir / f"{v_name}.py"
        if not v_path.exists():
            continue

        # Skip if quarantined
        if quarantine.get(v_name, {}).get("disabled"):
            try:
                db.append_event(
                    run_id=run_id,
                    event_type="validation.warned",
                    phase=phase,
                    command=command,
                    actor="orchestrator",
                    outcome="WARN",
                    payload={"validator": v_name,
                             "evidence_count": 1,
                             "reason": "quarantined"},
                )
            except Exception:
                pass
            continue

        args = [sys.executable, str(v_path), "--phase", phase]
        if v_name == "override-debt-balance":
            args.extend(["--run-id", run_id, "--flags", run_args])

        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if not r.stdout.strip():
                continue
            out = json.loads(r.stdout)
        except Exception as e:
            _quarantine_record(v_name, "CRASH")
            block_results.append({
                "validator": v_name,
                "verdict": "BLOCK",
                "evidence": [{"type": "info",
                              "message": f"validator crash: {e}"}],
            })
            continue

        # Update quarantine state (3 consecutive BLOCKs → auto-disable).
        _quarantine_record(v_name, out["verdict"])

        # Emit validation event for audit trail.
        # Three distinct states: PASS (green), WARN (non-blocking yellow),
        # BLOCK (red, blocks run-complete). Prior code collapsed WARN+BLOCK
        # into validation.failed which misled audits — WARN is informational.
        verdict_to_event = {
            "PASS": "validation.passed",
            "WARN": "validation.warned",
            "BLOCK": "validation.failed",
        }
        event_type = verdict_to_event.get(out["verdict"], "validation.failed")
        try:
            db.append_event(
                run_id=run_id,
                event_type=event_type,
                phase=phase,
                command=command,
                actor="validator",
                outcome=out["verdict"],
                payload={"validator": v_name,
                         "evidence_count": len(out.get("evidence", []))},
            )
        except Exception:
            pass

        if out["verdict"] == "BLOCK":
            block_results.append(out)

    return block_results


def _verify_contract(contract: dict | None, run_id: str, command: str,
                     phase: str, run_args: str) -> tuple[bool, list[dict]]:
    """Check must_write, must_touch_markers, must_emit_telemetry,
    forbidden_without_override + run applicable validators.
    Returns (pass, violations[])."""
    violations = []
    phase_dir = contracts.resolve_phase_dir(phase)

    # Run command-specific validators first (catches semantic issues even
    # when contract frontmatter is thin)
    validator_blocks = _run_validators(command, phase, run_id, run_args)
    for vb in validator_blocks:
        violations.append({
            "type": f"validator:{vb['validator']}",
            "missing": [
                f"[{e.get('type','?')}] {e.get('message','?')}"
                for e in vb.get("evidence", [])
            ],
        })

    if not contract:
        return (len(violations) == 0), violations

    # must_write
    must_write = contracts.normalize_must_write(contract.get("must_write") or [])
    missing_files = []
    for item in must_write:
        p = Path(contracts.substitute(item["path"], phase, phase_dir))
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        result = evidence.check_artifact(
            p, min_bytes=item["content_min_bytes"],
            required_sections=item["content_required_sections"],
        )
        if not result["ok"]:
            missing_files.append({"path": str(p), "reason": result["reason"]})
    if missing_files:
        violations.append({"type": "must_write", "missing": missing_files})

    # --wave N partial-run exemption: when user explicitly runs a single wave
    # (e.g. /vg:build 14 --wave 2), the terminal steps (8_execute_waves,
    # 9_post_execution, 10_postmortem_sanity) + build.completed event are
    # NOT expected. Full pipeline requires a subsequent /vg:build without --wave.
    # Partial-run exemption applies to must_touch_markers + must_emit_telemetry,
    # not to must_write (SUMMARY.md still required — wave work must be logged).
    is_partial_wave = bool(re.search(r"--wave[=\s]+\d+", run_args or ""))
    PARTIAL_EXEMPT_MARKERS = {"8_execute_waves", "9_post_execution",
                              "10_postmortem_sanity", "complete"}
    PARTIAL_EXEMPT_EVENTS = {"build.completed", "review.completed",
                             "test.completed", "accept.completed"}

    # must_touch_markers — fallback check against {command-short} namespace
    # so v1 flat markers + v2 per-command markers both satisfy contract.
    markers = contracts.normalize_markers(contract.get("must_touch_markers") or [])
    if markers and phase_dir:
        if is_partial_wave:
            markers = [m for m in markers
                       if m.get("name") not in PARTIAL_EXEMPT_MARKERS]
        cmd_ns = command.replace("vg:", "")
        missing_markers = state_mod.check_markers(
            phase_dir, markers, fallback_namespaces=[cmd_ns, "shared"],
        )
        if missing_markers:
            violations.append({"type": "must_touch_markers",
                               "missing": missing_markers})

    # must_emit_telemetry
    telemetry_specs = contracts.normalize_telemetry(
        contract.get("must_emit_telemetry") or []
    )
    if telemetry_specs:
        if is_partial_wave:
            telemetry_specs = [t for t in telemetry_specs
                               if t.get("event_type") not in PARTIAL_EXEMPT_EVENTS]
        events = db.query_events(run_id=run_id)
        missing_tel = evidence.check_telemetry(telemetry_specs, events)
        if missing_tel:
            violations.append({"type": "must_emit_telemetry",
                               "missing": missing_tel})

    # forbidden_without_override
    forbidden = contract.get("forbidden_without_override") or []
    unresolved_overrides = []
    for flag in forbidden:
        if flag in run_args:
            # Check if override.used event exists for this flag in this run
            matches = db.query_events(run_id=run_id,
                                      event_type="override.used")
            found = False
            for m in matches:
                pl = json.loads(m["payload_json"])
                if pl.get("flag") == flag:
                    found = True
                    break
            if not found:
                unresolved_overrides.append(flag)
    if unresolved_overrides:
        violations.append({"type": "forbidden_without_override",
                           "missing": unresolved_overrides})

    return (len(violations) == 0), violations


def _format_block_message(command: str, phase: str,
                          violations: list[dict]) -> str:
    lines = [
        "⛔ VG runtime_contract violations — cannot complete run.",
        "",
        f"Command: /{command} {phase}",
        "",
        "Missing evidence:",
    ]
    for v in violations:
        lines.append(f"  [{v['type']}]")
        for m in v["missing"]:
            if isinstance(m, dict):
                lines.append(f"    - {m.get('path', m)} ({m.get('reason', '')})")
            else:
                lines.append(f"    - {m}")
    lines.extend([
        "",
        "Fix options:",
        "  1. Run missing step + produce artifacts + mark + emit",
        "  2. vg-orchestrator override --flag <f> --reason <text> "
        "(logs to OVERRIDE-DEBT.md)",
        "  3. vg-orchestrator run-abort --reason <text> (gives up)",
        "",
        "Log: .vg/events.db",
    ])
    return "\n".join(lines)


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vg-orchestrator",
                                description="VG pipeline state machine")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run-start", help="Register new run")
    s.add_argument("command", help="vg:* command name")
    s.add_argument("phase", help="phase number")
    s.add_argument("extra", nargs=argparse.REMAINDER,
                   help="flags/args (captured verbatim; use -- prefix or quote)")
    s.set_defaults(func=cmd_run_start)

    s = sub.add_parser("run-status", help="Show active run")
    s.set_defaults(func=cmd_run_status)

    s = sub.add_parser("run-complete", help="Verify contract + complete")
    s.add_argument("--outcome", default="PASS")
    s.set_defaults(func=cmd_run_complete)

    s = sub.add_parser("run-abort", help="Abort current run")
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_run_abort)

    s = sub.add_parser("emit-event", help="Append event to active run")
    s.add_argument("event_type")
    s.add_argument("--payload", default=None,
                   help="JSON payload (or use stdin with --stdin)")
    s.add_argument("--step", default=None)
    s.add_argument("--actor", default="orchestrator",
                   choices=["orchestrator", "hook", "validator",
                            "llm-claimed", "user"])
    s.add_argument("--outcome", default="INFO",
                   choices=["PASS", "BLOCK", "WARN", "INFO"])
    s.set_defaults(func=cmd_emit_event)

    s = sub.add_parser("mark-step", help="Touch step marker")
    s.add_argument("namespace", help="e.g. 'build', 'blueprint', 'shared'")
    s.add_argument("step_name")
    s.set_defaults(func=cmd_mark_step)

    s = sub.add_parser("wave-start", help="Register wave in build run")
    s.add_argument("wave_n", type=int)
    s.set_defaults(func=cmd_wave_start)

    s = sub.add_parser("wave-complete", help="Close wave with evidence")
    s.add_argument("wave_n", type=int)
    s.add_argument("--evidence-file", default=None,
                   help="evidence JSON file; omit to read stdin")
    s.set_defaults(func=cmd_wave_complete)

    s = sub.add_parser("validate", help="Run named validator standalone")
    s.add_argument("validator_name")
    s.add_argument("--phase", default=None,
                   help="override phase (else uses active run)")
    s.add_argument("--stdin", action="store_true",
                   help="forward stdin to validator")
    s.add_argument("forward", nargs=argparse.REMAINDER,
                   help="args forwarded to validator")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("override", help="Log override.used event + debt entry")
    s.add_argument("--flag", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(func=cmd_override)

    s = sub.add_parser("run-resume", help="Resume interrupted run")
    s.set_defaults(func=cmd_run_resume)

    s = sub.add_parser("run-repair", help="Reconcile inconsistent state")
    s.add_argument("--force", action="store_true",
                   help="apply fixes; default is dry-run report")
    s.set_defaults(func=cmd_run_repair)

    s = sub.add_parser("verify-hash-chain", help="Integrity check")
    s.add_argument("--since-id", type=int, default=0)
    s.set_defaults(func=cmd_verify_hash_chain)

    s = sub.add_parser("query-events", help="Read events")
    s.add_argument("--run-id", default=None)
    s.add_argument("--event-type", default=None)
    s.add_argument("--phase", default=None)
    s.add_argument("--command", default=None)
    s.add_argument("--since", default=None)
    s.add_argument("--limit", type=int, default=1000)
    s.set_defaults(func=cmd_query_events)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as e:
        print(f"⛔ orchestrator error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
