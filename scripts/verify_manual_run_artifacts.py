#!/usr/bin/env python3
"""verify_manual_run_artifacts.py — Phase 2b-2.5 manual-run sanity gate (Task 21).

Reads ``<phase_dir>/recursive-prompts/EXPECTED-OUTPUTS.md`` (produced by
``scripts/generate_recursive_prompts.py``) and confirms every expected
``runs/<tool>/recursive-*.json`` artifact:

  1. exists,
  2. parses as JSON, and
  3. carries the v3 run-artifact skeleton (``lens``, ``steps[]`` with
     ``evidence_ref`` on each step, non-empty ``network_log``, ``verdict``).

Severity is BLOCK on any miss — exit code 1 with a structured stderr report.
On success the script prints a summary to stdout and exits 0.

Output file shape (printed when ``--json`` is passed):

    {
      "phase_dir": "<abs path>",
      "expected": [<rel path>, ...],
      "missing":  [<rel path>, ...],
      "invalid":  [{"path": <rel>, "reason": "..."}, ...],
      "ok":       [<rel path>, ...]
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# v3 run-artifact required fields. Mirrors the inline skeleton documented in
# commands/vg/_shared/transition-kits/_TEMPLATE.md.
REQUIRED_TOP_KEYS: set[str] = {"lens", "steps", "network_log", "verdict"}


# ---------------------------------------------------------------------------
# EXPECTED-OUTPUTS.md parsing
# ---------------------------------------------------------------------------
# Match a backtick-quoted relative path on each list line. Format produced by
# generate_recursive_prompts.py is:
#     - 1. lens=`...` element_class=`...` selector=`...` → `runs/.../foo.json`
_PATH_RE = re.compile(r"`([^`]+\.json)`\s*$", re.M)


def parse_expected_outputs(md_path: Path) -> list[str]:
    """Extract the trailing JSON path from each line of EXPECTED-OUTPUTS.md."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    paths: list[str] = []
    for line in text.splitlines():
        m = _PATH_RE.search(line)
        if m:
            paths.append(m.group(1).strip())
    return paths


# ---------------------------------------------------------------------------
# Artifact validation
# ---------------------------------------------------------------------------
def validate_artifact(path: Path) -> tuple[bool, str]:
    """Return (ok, reason). ``reason`` is empty when ``ok`` is True."""
    if not path.is_file():
        return False, "missing file"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"unreadable: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc.msg}"
    if not isinstance(data, dict):
        return False, "schema: top-level value is not an object"

    missing = REQUIRED_TOP_KEYS - data.keys()
    if missing:
        return False, f"schema: missing required keys {sorted(missing)}"

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return False, "schema: steps[] missing or empty"
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"schema: steps[{i}] is not an object"
        if "evidence_ref" not in step:
            return False, f"schema: steps[{i}].evidence_ref missing"

    network_log = data.get("network_log")
    if not isinstance(network_log, list) or not network_log:
        return False, "schema: network_log empty"

    verdict = data.get("verdict")
    if verdict not in {"pass", "fail", "inconclusive"}:
        return False, f"schema: verdict must be pass|fail|inconclusive, got {verdict!r}"

    return True, ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="verify_manual_run_artifacts.py",
        description="BLOCK gate: every EXPECTED-OUTPUTS.md path must exist + be v3-valid.",
    )
    ap.add_argument("--phase-dir", required=True)
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON report on stdout.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    phase_dir = Path(args.phase_dir).resolve()
    if not phase_dir.is_dir():
        sys.stderr.write(f"phase dir not found: {phase_dir}\n")
        return 2

    expected_md = phase_dir / "recursive-prompts" / "EXPECTED-OUTPUTS.md"
    if not expected_md.is_file():
        msg = (
            f"BLOCK: EXPECTED-OUTPUTS.md not found at {expected_md}\n"
            "Run `scripts/generate_recursive_prompts.py` first (Task 20).\n"
        )
        sys.stderr.write(msg)
        if args.json:
            print(json.dumps({
                "phase_dir": str(phase_dir),
                "blocked": True,
                "reason": "EXPECTED-OUTPUTS.md not found",
            }, indent=2))
        return 1

    expected_paths = parse_expected_outputs(expected_md)
    report: dict[str, Any] = {
        "phase_dir": str(phase_dir),
        "expected": expected_paths,
        "missing": [],
        "invalid": [],
        "ok": [],
    }

    for rel in expected_paths:
        full = phase_dir / rel
        if not full.is_file():
            report["missing"].append(rel)
            continue
        ok, reason = validate_artifact(full)
        if ok:
            report["ok"].append(rel)
        else:
            report["invalid"].append({"path": rel, "reason": reason})

    blocked = bool(report["missing"] or report["invalid"])
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if blocked:
            print(
                f"BLOCK: {len(report['missing'])} missing, "
                f"{len(report['invalid'])} invalid, "
                f"{len(report['ok'])} OK out of {len(expected_paths)} expected."
            )
            for rel in report["missing"]:
                print(f"  missing: {rel}")
            for entry in report["invalid"]:
                print(f"  invalid: {entry['path']} — {entry['reason']}")
        else:
            print(
                f"OK: all {len(expected_paths)} manual-run artifacts present "
                "and v3-valid (verifier passed)."
            )

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
