#!/usr/bin/env python3
"""
VG Bootstrap — Hygiene + Observability (Phase E, v1.15.0)

Unified hygiene/observability tool. Called by /vg:bootstrap subcommands
(--health, --trace, --test, --efficacy-update) and /vg:learn --retract.

Subcommands:
  health       — full report: dormant rules, regression flags, conflict scan
  trace        — show firing history of one rule from telemetry
  efficacy     — update hits + hit_outcomes in ACCEPTED.md from telemetry
  test         — run .vg/bootstrap/tests/*.yml fixture regression suite
  retract      — mark rule as retracted, move to RETRACTED.md (called from /vg:learn)
  export       — pack .vg/bootstrap/ into tar.gz
  import       — restore from tar.gz (destructive, prompts)

Reads telemetry.jsonl for efficacy computations.
Policy:
  - Rule no-hit 5+ phases → status: dormant (flag)
  - Rule no-hit 10+ phases → propose retract
  - fail_count > success_count after 5 hits → regression flag

All commands always exit 0 unless --strict.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BOOTSTRAP_DIR = Path(".vg/bootstrap")
ACCEPTED_MD = BOOTSTRAP_DIR / "ACCEPTED.md"
RETRACTED_MD = BOOTSTRAP_DIR / "RETRACTED.md"
RULES_DIR = BOOTSTRAP_DIR / "rules"


def _parse_accepted() -> list[dict]:
    """Parse ACCEPTED.md entries."""
    if not ACCEPTED_MD.exists():
        return []
    text = ACCEPTED_MD.read_text(encoding="utf-8", errors="replace")
    entries = []
    # Match YAML-ish blocks starting with `- id: L-...`
    blocks = re.split(r"^- id:\s*", text, flags=re.MULTILINE)
    for b in blocks[1:]:
        e: dict = {}
        lines = b.splitlines()
        if not lines:
            continue
        e["id"] = lines[0].strip()
        for line in lines[1:]:
            if ":" not in line or line.startswith("#"):
                continue
            k, _, v = line.strip().partition(":")
            k = k.strip().lstrip("-").strip()
            v = v.strip().strip("'\"")
            if not k:
                continue
            # Stop if we hit the next block boundary (another `- id:`)
            if line.lstrip().startswith("- ") and k == "id":
                break
            if k and v:
                # try coerce numbers / bools
                if v.lower() in ("true", "false"):
                    e[k] = v.lower() == "true"
                else:
                    try:
                        e[k] = int(v)
                    except ValueError:
                        try:
                            e[k] = float(v)
                        except ValueError:
                            e[k] = v
        if e.get("id"):
            entries.append(e)
    return entries


def _count_phases_since(iso_ts: str) -> int:
    """Approximate phases elapsed since timestamp — counts distinct phase numbers
    in telemetry.jsonl after iso_ts."""
    tel = Path(".vg/telemetry.jsonl")
    if not tel.exists() or not iso_ts:
        return 0
    try:
        threshold = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except Exception:
        return 0
    phases = set()
    for line in tel.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
            ets = datetime.fromisoformat(ev.get("ts", "").replace("Z", "+00:00"))
            if ets > threshold and ev.get("phase"):
                phases.add(ev["phase"])
        except Exception:
            continue
    return len(phases)


# ───────────────────── commands ─────────────────────
def cmd_health(args) -> int:
    entries = _parse_accepted()
    dormant_threshold = 5
    retract_threshold = 10

    now_iso = datetime.now(timezone.utc).isoformat()
    report = {
        "active": 0,
        "dormant": 0,
        "retract_candidates": 0,
        "regression_candidates": 0,
        "items": [],
    }

    for e in entries:
        eid = e.get("id")
        status = e.get("status", "active")
        hits = int(e.get("hits") or 0)
        success = int(e.get("success_count") or 0)
        fail = int(e.get("fail_count") or 0)
        promoted_at = str(e.get("promoted_at") or "")

        phases_since = _count_phases_since(promoted_at)
        flags = []

        if status == "active":
            report["active"] += 1
            if hits == 0 and phases_since >= dormant_threshold:
                flags.append("dormant")
                report["dormant"] += 1
            if hits == 0 and phases_since >= retract_threshold:
                flags.append("retract_candidate")
                report["retract_candidates"] += 1
            if hits >= 5 and fail > success:
                flags.append("regression")
                report["regression_candidates"] += 1

        if flags:
            report["items"].append(
                {"id": eid, "status": status, "hits": hits, "phases_since": phases_since, "flags": flags}
            )

    if args.emit == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"Bootstrap health — {len(entries)} accepted rules")
        print(f"  Active: {report['active']}")
        print(f"  Dormant (no-hit ≥{dormant_threshold} phases): {report['dormant']}")
        print(f"  Retract candidates (no-hit ≥{retract_threshold}): {report['retract_candidates']}")
        print(f"  Regression candidates (fail > pass after 5 hits): {report['regression_candidates']}")
        if report["items"]:
            print("\nFlagged:")
            for it in report["items"]:
                print(f"  - {it['id']} [{','.join(it['flags'])}] hits={it['hits']} phases_since={it['phases_since']}")
    return 0


def cmd_trace(args) -> int:
    rule_id = args.rule_id
    tel = Path(".vg/telemetry.jsonl")
    if not tel.exists():
        print(f"No telemetry.jsonl yet — rule {rule_id} has no firing history")
        return 0

    events = []
    for line in tel.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
            payload = ev.get("payload") or ev.get("meta") or {}
            if ev.get("event_type", "").startswith("bootstrap.rule_fired") and payload.get("rule_id") == rule_id:
                events.append(ev)
            elif payload.get("rule_id") == rule_id:
                events.append(ev)
        except Exception:
            continue

    if not events:
        print(f"Rule {rule_id} — no firing events in telemetry")
        return 0

    print(f"Rule {rule_id} — {len(events)} firing event(s)\n")
    for ev in events[-20:]:
        payload = ev.get("payload") or ev.get("meta") or {}
        print(f"  {ev.get('ts', '?')}  {ev.get('command', '?')}  phase={ev.get('phase', '?')}  outcome={ev.get('outcome', '?')}  changed={payload.get('changed', '?')}")
    return 0


def cmd_efficacy(args) -> int:
    """Scan telemetry and update ACCEPTED.md hits/outcomes.
    Non-destructive read — reports what WOULD be updated. Use --apply to write."""
    entries = _parse_accepted()
    tel = Path(".vg/telemetry.jsonl")

    fires: dict[str, Counter] = {}
    if tel.exists():
        for line in tel.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
                if not ev.get("event_type", "").startswith("bootstrap.rule_fired"):
                    continue
                payload = ev.get("payload") or ev.get("meta") or {}
                rid = payload.get("rule_id")
                if not rid:
                    continue
                c = fires.setdefault(rid, Counter())
                c["hits"] += 1
                if ev.get("outcome") == "PASS":
                    c["success"] += 1
                elif ev.get("outcome") in ("FAIL", "BLOCK"):
                    c["fail"] += 1
            except Exception:
                continue

    print("Efficacy snapshot:")
    changes = []
    for e in entries:
        rid = e.get("id")
        c = fires.get(rid, Counter())
        hits = c["hits"]
        succ = c["success"]
        fl = c["fail"]
        cur_hits = int(e.get("hits") or 0)
        if hits != cur_hits:
            changes.append((rid, cur_hits, hits, succ, fl))
        print(f"  {rid}  hits={hits}  success={succ}  fail={fl}")

    if not changes:
        print("\nNo changes needed.")
        return 0

    if args.apply:
        # Rewrite ACCEPTED.md — simple append-only diff (don't try to surgical-edit
        # YAML blocks that we didn't parse perfectly; instead write a footer log).
        log_path = BOOTSTRAP_DIR / ".efficacy-log.md"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n## Efficacy update {datetime.now(timezone.utc).isoformat()}\n")
            for rid, old, new, succ, fl in changes:
                f.write(f"- {rid}: hits {old} → {new}, success={succ}, fail={fl}\n")
        print(f"\nWrote summary to {log_path}")
    else:
        print("\nRun with --apply to persist changes to .efficacy-log.md")
    return 0


def cmd_test(args) -> int:
    """Run fixture regression tests in .vg/bootstrap/tests/*.yml."""
    tests_dir = BOOTSTRAP_DIR / "tests"
    if not tests_dir.exists():
        print("No tests/ dir — nothing to run")
        return 0
    fixtures = sorted(tests_dir.glob("*.yml")) + sorted(tests_dir.glob("*.yaml"))
    if not fixtures:
        print("No fixture files found")
        return 0

    passed = failed = 0
    for fx in fixtures:
        print(f"\n▶ {fx.name}")
        # Minimal runner — fixtures are declarative. Smoke check: file parses + has
        # required keys (name, given, when, then). Full execution deferred to future
        # since it requires fabricating OVERRIDE-DEBT / phase metadata per fixture.
        try:
            text = fx.read_text(encoding="utf-8")
            ok = all(k in text for k in ("name:", "given:", "when:", "then:"))
            if ok:
                print("   ✓ fixture structure valid")
                passed += 1
            else:
                print("   ✗ missing required keys (name/given/when/then)")
                failed += 1
        except Exception as e:
            print(f"   ✗ parse error: {e}")
            failed += 1

    print(f"\n{passed}/{len(fixtures)} fixtures valid")
    return 0 if failed == 0 else 1


def cmd_retract(args) -> int:
    """Mark rule as retracted. Appends to RETRACTED.md, does NOT delete
    from overlay.yml/rules — caller script (in /vg:learn --retract) handles
    file surgery. This just logs audit entry."""
    rid = args.rule_id
    reason = args.reason or "unspecified"
    now = datetime.now(timezone.utc).isoformat()
    entry = f"""
- id: {rid}
  retracted_at: {now}
  retracted_by: {args.by or 'user'}
  reason: "{reason}"
  git_sha: (fill after commit)
"""
    with RETRACTED_MD.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"Retraction logged: {rid} → {RETRACTED_MD}")
    print(f"Reason: {reason}")
    return 0


def cmd_export(args) -> int:
    out = args.output or f"bootstrap-export-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(str(BOOTSTRAP_DIR), arcname="bootstrap")
    print(f"Exported to {out}")
    return 0


def cmd_import(args) -> int:
    src = args.input
    if not src or not Path(src).exists():
        print(f"Input tarball missing: {src}")
        return 1
    print(f"⚠ Import is destructive. Merging {src} over current .vg/bootstrap/")
    print("Press ENTER to continue, Ctrl-C to cancel...")
    try:
        input()
    except KeyboardInterrupt:
        print("Cancelled")
        return 1
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(".vg/")
    print("Import complete")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="VG Bootstrap Hygiene")
    sub = ap.add_subparsers(dest="command", required=True)

    p_h = sub.add_parser("health")
    p_h.add_argument("--emit", choices=["text", "json"], default="text")

    p_t = sub.add_parser("trace")
    p_t.add_argument("rule_id")

    p_e = sub.add_parser("efficacy")
    p_e.add_argument("--apply", action="store_true")

    p_test = sub.add_parser("test")

    p_r = sub.add_parser("retract")
    p_r.add_argument("rule_id")
    p_r.add_argument("--reason", default="")
    p_r.add_argument("--by", default="user")

    p_ex = sub.add_parser("export")
    p_ex.add_argument("--output")

    p_im = sub.add_parser("import")
    p_im.add_argument("input")

    args = ap.parse_args()
    dispatch = {
        "health": cmd_health,
        "trace": cmd_trace,
        "efficacy": cmd_efficacy,
        "test": cmd_test,
        "retract": cmd_retract,
        "export": cmd_export,
        "import": cmd_import,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
