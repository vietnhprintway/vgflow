#!/usr/bin/env python3
"""step-status-ledger.py — Batch 9 C5

Per-step outcome ledger so test verdict can override goal-only PASS when
non-goal steps BLOCK/FAIL (contract verify, deploy, security, regression).

Schema:
{
  "steps": {
    "<step_name>": {
      "status": "PASS|BLOCK|FAIL|WARN|SKIP",
      "reason": "<text>",
      "ts": "<ISO timestamp>",
      "evidence_ref": "<optional path>"
    }
  }
}

Atomic write — read existing, merge, write tmp + rename.
"""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--step", required=True)
    ap.add_argument("--status", required=True,
                    choices=["PASS", "BLOCK", "FAIL", "WARN", "SKIP"])
    ap.add_argument("--reason", default="")
    ap.add_argument("--evidence-ref", default="")
    ap.add_argument("--ledger", default=".test-step-status.json",
                    help="Output ledger filename (default: .test-step-status.json)")
    args = ap.parse_args()

    ledger = args.phase_dir / args.ledger
    data = {"steps": {}}
    if ledger.is_file():
        try:
            data = json.loads(ledger.read_text(encoding="utf-8"))
            data.setdefault("steps", {})
        except Exception:
            pass

    entry = {
        "status": args.status,
        "reason": args.reason,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if args.evidence_ref:
        entry["evidence_ref"] = args.evidence_ref
    data["steps"][args.step] = entry

    # Atomic write
    args.phase_dir.mkdir(parents=True, exist_ok=True)
    ledger_stem = Path(args.ledger).stem
    fd, tmp_path = tempfile.mkstemp(dir=str(args.phase_dir), prefix=f"{ledger_stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, ledger)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    print(f"ledger updated: {args.step}={args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
