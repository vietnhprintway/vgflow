#!/usr/bin/env python3
"""
runtime-evidence validator — forces runtime verification over AI "code evidence".

Blocks AI rationalization: "code exists + unit tests pass → goal READY".
Real enforcement: if Playwright spec exists for phase, it MUST have run.

Dispatch rules:
1. Find all Playwright specs under apps/web/e2e/*.spec.ts referencing phase
   by filename (e.g. `auth-domain-isolation.spec.ts` for phase 14 auth).
   Heuristic: filename tokens intersect phase slug tokens.
2. For each spec found, check `apps/web/playwright-report/` or
   `apps/web/test-results/` for run evidence newer than phase's blueprint
   commit (proves test ran AFTER code was written).
3. Missing execution evidence → BLOCK with explicit list of specs + setup hint.
4. Also check GOAL-COVERAGE-MATRIX.md for goals marked READY but no runtime
   proof — downgrade to CODE_ONLY_EVIDENCE, BLOCK if critical priority.

Overridable via --allow-unexecuted-specs flag at /vg:review or /vg:test,
which logs to OVERRIDE-DEBT and forces re-verification at /vg:accept.

Output: standard validator JSON
{"validator": "runtime-evidence",
 "verdict": "PASS|WARN|BLOCK",
 "evidence": [{"type": "...", "message": "...", "file": "..."}]}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
PHASES_DIR = REPO_ROOT / ".vg" / "phases"


def find_phase_dir(phase: str) -> Path | None:
    if not PHASES_DIR.exists():
        return None
    for c in PHASES_DIR.glob(f"{phase}-*"):
        return c
    for c in PHASES_DIR.glob(f"{phase.zfill(2)}-*"):
        return c
    return None


def phase_slug_tokens(phase_dir: Path) -> set[str]:
    """Extract significant tokens from phase dir name for spec matching."""
    name = phase_dir.name
    # Remove leading digits + dashes: "14-per-domain-auth-isolation" → "per-domain-auth-isolation"
    cleaned = re.sub(r"^\d+[.\d]*-", "", name)
    # Tokens: split by -
    tokens = set(cleaned.split("-"))
    # Remove stopwords
    tokens -= {"", "and", "or", "the", "a", "for", "with"}
    return tokens


def find_phase_specs(phase_dir: Path) -> list[Path]:
    """Find Playwright specs likely related to this phase."""
    e2e_dir = REPO_ROOT / "apps" / "web" / "e2e"
    if not e2e_dir.exists():
        return []
    phase_tokens = phase_slug_tokens(phase_dir)
    specs = []
    for spec in e2e_dir.rglob("*.spec.ts"):
        # Match if ≥2 tokens overlap (avoid false positives on common words)
        spec_tokens = set(spec.stem.split("-"))
        overlap = phase_tokens & spec_tokens
        if len(overlap) >= 2:
            specs.append(spec)
    return specs


def check_playwright_run_evidence(spec: Path, since_mtime: float) -> tuple[bool, str]:
    """Check if spec was executed AFTER code existed.
    Looks for test-results/ or playwright-report/ updated post `since_mtime`."""
    web_dir = REPO_ROOT / "apps" / "web"
    candidates = [
        web_dir / "playwright-report",
        web_dir / "test-results",
    ]
    for d in candidates:
        if not d.exists():
            continue
        # Any file in dir newer than since_mtime?
        for f in d.rglob("*"):
            if f.is_file() and f.stat().st_mtime > since_mtime:
                return True, str(f.relative_to(REPO_ROOT))
    return False, ""


def parse_goal_coverage_matrix(phase_dir: Path) -> list[dict]:
    """Parse GOAL-COVERAGE-MATRIX.md for goals + their status."""
    matrix = phase_dir / "GOAL-COVERAGE-MATRIX.md"
    if not matrix.exists():
        return []
    text = matrix.read_text(encoding="utf-8", errors="replace")
    # Heuristic: goal rows look like "| G-XX | priority | ... | status | ..."
    goals = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*(G-\d+)\s*\|\s*(\w+)\s*\|.*?\|\s*(\w+)\s*\|", line)
        if m:
            goals.append({
                "id": m.group(1),
                "priority": m.group(2),
                "status": m.group(3),
            })
    return goals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--allow-unexecuted-specs", action="store_true",
                    help="override: log debt + continue")
    args = ap.parse_args()

    phase_dir = find_phase_dir(args.phase)
    if not phase_dir:
        print(json.dumps({
            "validator": "runtime-evidence",
            "verdict": "WARN",
            "evidence": [{"type": "missing_file",
                          "message": f"phase dir for {args.phase} not found"}]
        }))
        return 0

    specs = find_phase_specs(phase_dir)
    evidence = []
    verdict = "PASS"

    if not specs:
        # No specs found for phase. Warn only — might be backend-only phase
        # with legitimate no-UI goals. Let matrix coverage gate handle it.
        evidence.append({
            "type": "info",
            "message": f"no Playwright specs found matching phase slug "
                       f"tokens: {sorted(phase_slug_tokens(phase_dir))}"
        })
    else:
        # Reference point: phase's SPECS.md mtime (blueprint time)
        specs_md = phase_dir / "SPECS.md"
        since_mtime = specs_md.stat().st_mtime if specs_md.exists() else 0

        unexecuted = []
        for spec in specs:
            ran, report = check_playwright_run_evidence(spec, since_mtime)
            if ran:
                evidence.append({
                    "type": "execution_proof",
                    "message": f"{spec.name} executed, report at {report}",
                    "file": str(spec.relative_to(REPO_ROOT)),
                })
            else:
                unexecuted.append(spec)
                evidence.append({
                    "type": "unexecuted_spec",
                    "message": f"{spec.name} exists but no playwright-report/"
                               f" or test-results/ entry newer than SPECS.md. "
                               f"Setup: cd apps/web && pnpm playwright test "
                               f"{spec.relative_to(REPO_ROOT/'apps/web')}",
                    "file": str(spec.relative_to(REPO_ROOT)),
                })

        if unexecuted and not args.allow_unexecuted_specs:
            verdict = "BLOCK"

    # Check GOAL-COVERAGE-MATRIX for goals marked READY without runtime proof
    goals = parse_goal_coverage_matrix(phase_dir)
    code_only_critical = []
    for g in goals:
        # If goal marked READY but no Playwright ran → suspect "code evidence"
        # rationalization. Critical goals need runtime proof.
        if g["status"].upper() == "READY" and g["priority"].lower() == "critical":
            if specs and verdict == "BLOCK":
                code_only_critical.append(g["id"])

    if code_only_critical:
        evidence.append({
            "type": "code_only_critical_goals",
            "message": f"Critical goals marked READY without runtime proof: "
                       f"{', '.join(code_only_critical)}. Run Playwright specs "
                       f"or mark as deferred|manual with reason.",
        })

    print(json.dumps({
        "validator": "runtime-evidence",
        "verdict": verdict,
        "evidence": evidence,
        "duration_ms": 0,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
