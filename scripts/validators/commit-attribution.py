#!/usr/bin/env python3
"""
Validator: commit-attribution.py

Purpose: Enforce commit discipline from vg-executor-rules. Every commit in
phase range MUST:
  1. Match subject regex: ^(feat|fix|refactor|test|chore|docs)\\({phase}[-.\\d]*-\\d+\\):
     Example: feat(7.6-04): add POST /api/sites handler
  2. Cite decision / contract / goal in body (MANDATORY for apps/**/src/**,
     packages/**/src/**):
     - "Per API-CONTRACTS.md" OR "Per CONTEXT.md D-XX" OR "Covers goal: G-XX"
     - OR explicit "no-goal-impact" declaration
  3. Body must NOT contain `--no-verify` or `--amend` flags (AI sometimes
     bypasses hooks when pre-commit fails).

Prior state: commit-msg hook was supposed to enforce but (a) not installed on
every clone, (b) --no-verify bypasses it anyway. This validator runs at
run-complete post-wave + at /vg:accept final check — failing commits can't be
"silently amended away" because git log is immutable ground truth.

Skip (PASS):
- Phase has 0 commits in its ref range → not started, not our job
- Non-code phase (docs/migration) where bodies don't need contract citations

Checks (BLOCK):
- Subject regex mismatch (missing `feat(phase-NN):` prefix)
- Body missing citation for code-touching commit

Usage: commit-attribution.py --phase <N> [--ref-range <git-range>]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import Evidence, Output, timer, emit_and_exit, find_phase_dir  # noqa: E402

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
PHASES_DIR = REPO_ROOT / ".vg" / "phases"

# Commit subject regex — phase-NN task ID
SUBJECT_RE = re.compile(
    r"^(feat|fix|refactor|test|chore|docs)\(([\d.]+)-(\d+)\):",
    re.MULTILINE,
)

# Citations accepted (any ONE sufficient for code-touching commit)
CITATION_PATTERNS = [
    re.compile(r"Per\s+API-CONTRACTS\.md", re.IGNORECASE),
    re.compile(r"Per\s+CONTEXT\.md\s+D-\d+", re.IGNORECASE),
    re.compile(r"Covers?\s+goal:?\s+G-\d+", re.IGNORECASE),
    re.compile(r"\bno-goal-impact\b", re.IGNORECASE),
    re.compile(r"\bno-impact\b", re.IGNORECASE),  # shorter variant
]

# OHOK-6 (Codex/Gemini P1): semantic ghosting detection.
# Extract the specific decision/goal ID being claimed, so we can verify
# the artifact actually exists. Shape-match of "Per CONTEXT.md D-15" was
# previously accepted even if D-15 doesn't exist in CONTEXT.md — AI could
# fabricate a plausible-looking citation to satisfy the commit-msg hook.
DECISION_EXTRACT_RE = re.compile(
    r"Per\s+CONTEXT\.md\s+(?:P[\d.]+\.)?D-(\d+)", re.IGNORECASE,
)
GOAL_EXTRACT_RE = re.compile(
    r"Covers?\s+goal:?\s+G-(\d+)", re.IGNORECASE,
)


def _decision_exists(phase_dir: Path, decision_num: str) -> bool:
    """Check phase's CONTEXT.md has this decision header. Accepts both
    bare D-XX and P{phase}.D-XX formats.
    """
    ctx = phase_dir / "CONTEXT.md"
    if not ctx.exists():
        return False
    try:
        text = ctx.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    # Match ### D-15 or ### P7.6.D-15 headers
    pattern = re.compile(
        rf"^###\s+(?:P[\d.]+\.)?D-{int(decision_num):02d}\b"
        rf"|^###\s+(?:P[\d.]+\.)?D-{int(decision_num)}\b",
        re.MULTILINE,
    )
    return bool(pattern.search(text))


def _goal_exists(phase_dir: Path, goal_num: str) -> bool:
    """Check phase's TEST-GOALS.md has this goal ID.

    Accepts multiple header formats observed across phases:
      - `### G-01:` or `### G-01 ` (standard)
      - `### Goal G-01:` (phase 14 format, with "Goal" prefix)
      - Table row `| G-01 | ...`

    Both zero-padded (G-01) and unpadded (G-1) accepted.
    """
    goals = phase_dir / "TEST-GOALS.md"
    if not goals.exists():
        return False
    try:
        text = goals.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    n = int(goal_num)
    # Build both zero-padded + unpadded forms
    ids = {f"G-{n:02d}", f"G-{n}"}
    for gid in ids:
        # `### <maybe "Goal ">G-XX[:|\s]` or `| G-XX |`
        if re.search(rf"^###\s+(?:Goal\s+)?{re.escape(gid)}\b", text, re.MULTILINE):
            return True
        if re.search(rf"^\|\s*{re.escape(gid)}\s*\|", text, re.MULTILINE):
            return True
    return False

# Code paths that require citation (skip for pure planning/docs commits)
CODE_PATH_RE = re.compile(
    r"^(apps/[^/]+/src/|packages/[^/]+/src/|infra/|apps/[^/]+/e2e/)",
    re.MULTILINE,
)

# Anti-pattern: --no-verify or --amend in body is a red flag
BYPASS_RE = re.compile(r"(?:--no-verify|git commit --amend)", re.IGNORECASE)


def git_log_subjects(phase_num: str, since_ref: str | None = None) -> list[dict]:
    """Return list of {sha, subject, body, files} for commits in phase range.
    Strategy: grep subject for phase number pattern + exclude planning-only changes.
    """
    # We use git log with a grep pattern on commit subject — phase tag
    # Pattern covers 7, 07, 7.1, 07.12 etc.
    phase_variants = [phase_num]
    # Zero-pad for 1-digit and 2-digit phases
    if "." in phase_num:
        base, sub = phase_num.split(".", 1)
        if len(base) == 1:
            phase_variants.append(f"0{base}.{sub}")
    elif len(phase_num) == 1:
        phase_variants.append(f"0{phase_num}")

    # Build alternation regex for git log --grep
    grep_pattern = "|".join(
        f"\\({v}[-.0-9]*-[0-9]+\\):" for v in phase_variants
    )

    try:
        r = subprocess.run(
            ["git", "log", "--no-merges",
             "-E", f"--grep={grep_pattern}",
             "--pretty=format:%H%x00%s%x00%b%x01"],
            capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
        )
    except Exception:
        return []

    if r.returncode != 0:
        return []

    commits = []
    for entry in r.stdout.split("\x01"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x00")
        if len(parts) < 2:
            continue
        sha = parts[0].strip()
        subject = parts[1].strip() if len(parts) > 1 else ""
        body = parts[2].strip() if len(parts) > 2 else ""

        # Get files changed for citation requirement
        try:
            fr = subprocess.run(
                ["git", "show", "--pretty=", "--name-only", sha],
                capture_output=True, text=True, timeout=10, cwd=REPO_ROOT,
            )
            files = [f for f in fr.stdout.strip().split("\n") if f.strip()]
        except Exception:
            files = []

        commits.append({
            "sha": sha[:12],
            "subject": subject,
            "body": body,
            "files": files,
        })

    return commits


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--ref-range", default=None,
                    help="Git ref range (default: auto-detect from phase commits)")
    args = ap.parse_args()

    out = Output(validator="commit-attribution")
    with timer(out):
        phase_dir = find_phase_dir(args.phase)
        phase_dirs = [phase_dir] if phase_dir else []
        if not phase_dirs:
            # No phase dir = can't validate; treat as skip (PASS)
            emit_and_exit(out)

        commits = git_log_subjects(args.phase, args.ref_range)

        if not commits:
            # No commits in phase range — either not started or pure-docs phase.
            # Emit WARN so audit sees "0 commits claimed for phase" but don't BLOCK.
            out.warn(Evidence(
                type="count_below_threshold",
                message=f"0 commits found with phase {args.phase} tag in git log",
                fix_hint=(
                    "If phase has code changes, commits must use subject pattern "
                    "feat({phase}-NN): ... so phase attribution is traceable. "
                    "If phase is planning-only, this warn is expected."
                ),
            ))
            emit_and_exit(out)

        violations_subject = []
        violations_citation = []
        violations_bypass = []
        violations_phantom_citation = []  # OHOK-6: cited but doesn't resolve

        for c in commits:
            sha = c["sha"]
            subject = c["subject"]
            body = c["body"]
            files = c["files"]

            # CHECK 1: subject regex
            if not SUBJECT_RE.match(subject):
                violations_subject.append((sha, subject))

            # CHECK 2: body citation (only if commit touches code)
            touches_code = any(CODE_PATH_RE.match(f + "\n") for f in files)
            # Also allow: commit touches .vg/ only (planning) → skip citation requirement
            planning_only = all(
                f.startswith(".vg/") or f.startswith(".claude/")
                or f.startswith(".codex/") or f.startswith(".github/")
                or f.endswith(".md")
                for f in files
            ) if files else True

            if touches_code and not planning_only:
                has_citation = any(p.search(body) for p in CITATION_PATTERNS)
                if not has_citation:
                    violations_citation.append((sha, subject[:60], files[:3]))
                else:
                    # OHOK-6 (Codex/Gemini P1) — semantic ghosting detection.
                    # Citation matched regex; verify the cited D-XX / G-XX
                    # actually exists in the phase's artifact files.
                    phantom_refs = []
                    for m in DECISION_EXTRACT_RE.finditer(body):
                        d_num = m.group(1)
                        if not _decision_exists(phase_dir, d_num):
                            phantom_refs.append(f"D-{d_num}")
                    for m in GOAL_EXTRACT_RE.finditer(body):
                        g_num = m.group(1)
                        if not _goal_exists(phase_dir, g_num):
                            phantom_refs.append(f"G-{g_num}")
                    if phantom_refs:
                        violations_phantom_citation.append(
                            (sha, subject[:60], phantom_refs)
                        )

            # CHECK 3: --no-verify / --amend in body (bypass red flag)
            if BYPASS_RE.search(body):
                violations_bypass.append((sha, subject[:60]))

        # Emit evidence by severity
        if violations_subject:
            sample = violations_subject[:5]
            out.add(Evidence(
                type="subject_format_violation",
                message=(
                    f"{len(violations_subject)}/{len(commits)} commit(s) have "
                    f"malformed subject (expected `feat({args.phase}-NN): ...`)"
                ),
                expected=r"^(feat|fix|refactor|test|chore|docs)\(\d+[-.\d]*-\d+\):",
                actual="; ".join(f"{sha}: {subj[:50]}" for sha, subj in sample),
                fix_hint=(
                    "Rewrite commit subjects via `git commit --amend` OR squash + rebase. "
                    "If commits are already merged, add a follow-up commit documenting "
                    "the attribution and log as override-debt."
                ),
            ))

        if violations_citation:
            sample = violations_citation[:5]
            evidence_str = "; ".join(
                f"{sha}: {subj} (files: {', '.join(files)})"
                for sha, subj, files in sample
            )
            out.add(Evidence(
                type="missing_citation",
                message=(
                    f"{len(violations_citation)} code-touching commit(s) missing "
                    f"body citation (require 'Per API-CONTRACTS.md', "
                    f"'Per CONTEXT.md D-XX', 'Covers goal: G-XX', or 'no-goal-impact')"
                ),
                actual=evidence_str,
                fix_hint=(
                    "Every commit touching apps/**/src, packages/**/src, or infra/ "
                    "MUST cite the decision/contract/goal it implements. This is R2 "
                    "from vg-executor-rules. Amend body OR log override-debt."
                ),
            ))

        if violations_bypass:
            sample = violations_bypass[:3]
            out.add(Evidence(
                type="bypass_red_flag",
                message=(
                    f"{len(violations_bypass)} commit(s) mention --no-verify or "
                    "--amend in body — investigate for hook bypass"
                ),
                actual="; ".join(f"{sha}: {subj}" for sha, subj in sample),
                fix_hint=(
                    "--no-verify bypasses pre-commit hooks (typecheck, lint, citation). "
                    "Verify the commits actually pass hooks when run manually; if not, "
                    "fix underlying issue rather than bypassing."
                ),
            ))

        if violations_phantom_citation:
            # OHOK-6 (Codex/Gemini P1): semantic ghosting. Citation matched
            # regex but cited D-XX/G-XX doesn't exist in the phase artifacts.
            sample = violations_phantom_citation[:5]
            evidence_str = "; ".join(
                f"{sha} {subj} → missing: {', '.join(refs)}"
                for sha, subj, refs in sample
            )
            out.add(Evidence(
                type="phantom_citation",
                message=(
                    f"{len(violations_phantom_citation)} commit(s) cite "
                    f"decisions/goals that DON'T EXIST in phase artifacts. "
                    f"Semantic ghosting — audit-looking breadcrumbs without "
                    f"real reference."
                ),
                actual=evidence_str,
                fix_hint=(
                    "Either (a) amend commit body to cite a real D-XX/G-XX "
                    "from CONTEXT.md/TEST-GOALS.md, (b) add the missing "
                    "decision/goal to the artifact (run /vg:scope or "
                    "/vg:amend), or (c) change citation to 'no-goal-impact' "
                    "if truly orthogonal."
                ),
            ))

    emit_and_exit(out)


if __name__ == "__main__":
    main()
