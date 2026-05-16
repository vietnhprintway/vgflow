#!/usr/bin/env python3
"""B66 (codex MAJOR — advisory classifier): heuristic test-failure
classifier with confidence threshold + UNKNOWN class.

Prior fix-loop classification was prose-only (CODE_BUG | INFRA_ISSUE |
SPEC_GAP | PRE_EXISTING). Heuristic-based classifier risks misrouting
infra outages → code fixes. Codex audit MAJOR concern: add UNKNOWN
class + confidence threshold so fix-loop routes high-confidence
matches only.

Input — failure report JSON:
  {
    "spec": "tests/sites.spec.ts",
    "test_id": "G-01-b1",
    "goal_id": "G-01",
    "sha": "<commit-sha>",
    "error": "<test runner error message>",
    "stack": "<stack trace>",
    "console": ["console msg 1", ...],
    "network": [{"url": "...", "status": 500}],
    "previous_runs": [{"sha": "<sha>", "status": "fail|pass"}]
  }

Output JSON (stdout):
  {
    "class": "CODE_BUG | INFRA_ISSUE | SPEC_GAP | PRE_EXISTING | FLAKY | UNKNOWN",
    "confidence": 0.0-1.0,
    "reasons": [...],
    "evidence_refs": {"console_idx": [0,1], "network_idx": [2]}
  }

Confidence rule: if no rule matches with > 0.6 confidence → UNKNOWN.
Fix-loop dispatcher SHOULD only auto-spawn fixer for class in
{CODE_BUG, SPEC_GAP} with confidence ≥ 0.7. UNKNOWN → escalate to
human or retry-only mode.

Usage:
  classify-test-failure.py --input <failure-report.json>
  classify-test-failure.py --input - --pretty
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from typing import Any


# Heuristic patterns. Each entry: (class, regex, confidence_contribution).
# Multiple matches stack confidence up to 1.0.
CLASS_PATTERNS = [
    # INFRA_ISSUE signals (deterministic env failure — highly specific patterns
    # are weighted high enough that single match crosses UNKNOWN_CEILING).
    ("INFRA_ISSUE", r"\b(ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|EHOSTUNREACH|ENOTFOUND)\b", 0.75),
    ("INFRA_ISSUE", r"\b(503\s+Service Unavailable|502\s+Bad Gateway|504\s+Gateway Timeout)\b", 0.7),
    ("INFRA_ISSUE", r"\b(connect to.*refused|database.*unavailable|redis.*connection)\b", 0.65),
    ("INFRA_ISSUE", r"\b(port\s+\d+\s+already in use|address already in use)\b", 0.7),
    ("INFRA_ISSUE", r"\b(net::ERR_CONNECTION_REFUSED|net::ERR_NAME_NOT_RESOLVED)\b", 0.75),
    # CODE_BUG signals
    ("CODE_BUG", r"\bTypeError:|ReferenceError:|SyntaxError:", 0.45),
    ("CODE_BUG", r"\bCannot read propert(y|ies) of (undefined|null)\b", 0.5),
    ("CODE_BUG", r"\bAssertionError\b|\bexpect\(.*\)\.to\w+\(\) failed\b", 0.45),
    ("CODE_BUG", r"\bexpected.*received|expected.*to (equal|be|contain|have)\b", 0.3),
    ("CODE_BUG", r"\b40[0-4]\s+(Bad Request|Unauthorized|Forbidden|Not Found)\b", 0.3),
    # SPEC_GAP signals
    ("SPEC_GAP", r"\b(locator|selector|getByTestId|getByRole|getByLabel)\b.*\b(not found|did not find|0 elements)\b", 0.45),
    ("SPEC_GAP", r"\bdata-testid=\"[\w-]+\".*not in DOM\b", 0.5),
    ("SPEC_GAP", r"\b(button|link|input|form) .* not (visible|rendered|attached)\b", 0.3),
    # FLAKY signals (same test passed before with same SHA → likely env flake)
    # Computed separately by _check_flaky_signal
    # PRE_EXISTING signals
    ("PRE_EXISTING", r"\bvg-pre-existing\b|\bknown-issue:", 0.7),
]

CONFIDENCE_THRESHOLD = 0.7  # codex MAJOR: only route auto-fix on ≥0.7
UNKNOWN_CEILING = 0.6  # below this → UNKNOWN


def _classify_text(text: str) -> dict[str, Any]:
    """Aggregate signals across all classes. Pick highest-confidence.

    Returns {class, confidence, reasons[]}. Class is UNKNOWN if highest
    confidence < UNKNOWN_CEILING.
    """
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for cls, pattern, weight in CLASS_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            scores[cls] = min(1.0, scores.get(cls, 0.0) + weight)
            reasons.setdefault(cls, []).append(f"{pattern} → {m.group(0)[:80]}")
    if not scores:
        return {"class": "UNKNOWN", "confidence": 0.0, "reasons": ["no heuristic match"]}
    best_class = max(scores, key=scores.get)
    best_conf = scores[best_class]
    if best_conf < UNKNOWN_CEILING:
        return {
            "class": "UNKNOWN",
            "confidence": best_conf,
            "reasons": reasons.get(best_class, []) + [
                f"top class {best_class} below UNKNOWN_CEILING={UNKNOWN_CEILING}"
            ],
        }
    return {
        "class": best_class,
        "confidence": best_conf,
        "reasons": reasons.get(best_class, []),
    }


def _check_flaky_signal(report: dict[str, Any]) -> tuple[bool, str]:
    """Returns (is_flaky, reason). Heuristic: same SHA previously passed,
    or 2-of-3 same-SHA retries passed → FLAKY."""
    sha = report.get("sha")
    previous = report.get("previous_runs") or []
    if not sha or not previous:
        return False, ""
    same_sha = [r for r in previous if r.get("sha") == sha]
    if not same_sha:
        return False, ""
    pass_count = sum(1 for r in same_sha if r.get("status") == "pass")
    fail_count = sum(1 for r in same_sha if r.get("status") == "fail")
    if pass_count >= 1 and (pass_count + fail_count) >= 2:
        return True, f"same SHA passed {pass_count}/{pass_count + fail_count} previous attempts"
    return False, ""


def classify(report: dict[str, Any]) -> dict[str, Any]:
    """Top-level classifier — aggregates text signals + flaky detection."""
    # Build searchable text from error + stack + console + network
    parts: list[str] = []
    if report.get("error"):
        parts.append(str(report["error"]))
    if report.get("stack"):
        parts.append(str(report["stack"]))
    for c in report.get("console") or []:
        parts.append(str(c))
    for n in report.get("network") or []:
        if isinstance(n, dict):
            parts.append(f"{n.get('status')} {n.get('url', '')}")
    full_text = "\n".join(parts)

    # Flaky check takes precedence — same-SHA retry pass = environmental
    is_flaky, flaky_reason = _check_flaky_signal(report)
    if is_flaky:
        return {
            "class": "FLAKY",
            "confidence": 0.85,
            "reasons": [flaky_reason],
            "evidence_refs": {},
        }

    result = _classify_text(full_text)
    # Add evidence_refs
    evidence: dict[str, list[int]] = {}
    console = report.get("console") or []
    for i, c in enumerate(console):
        for cls, pattern, _ in CLASS_PATTERNS:
            if cls == result["class"] and re.search(pattern, str(c), re.IGNORECASE):
                evidence.setdefault("console_idx", []).append(i)
                break
    network = report.get("network") or []
    for i, n in enumerate(network):
        if isinstance(n, dict):
            n_text = f"{n.get('status')} {n.get('url', '')}"
            for cls, pattern, _ in CLASS_PATTERNS:
                if cls == result["class"] and re.search(pattern, n_text, re.IGNORECASE):
                    evidence.setdefault("network_idx", []).append(i)
                    break
    result["evidence_refs"] = evidence
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="failure-report JSON file path OR '-' for stdin")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            raw = f.read()
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⛔ classify-test-failure: invalid JSON input: {e}", file=sys.stderr)
        return 1

    result = classify(report)
    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
