"""tests/test_batch66_fix_loop_revised.py — B66 (codex MAJOR fixes).

Codex audit MAJORs:
1. Flaky pre-check unsafe — 3x retry-every-failure triples CI cost.
   Same-SHA retry only with historical previous_runs[] evidence.
2. --retry-only flag not wired in test.md args or preflight.
3. Cross-phase ripple via raw grep has high FP — use CROSS-PHASE-DEPS.
4. Classifier must be advisory + UNKNOWN class + confidence threshold.
5. Failure-report schema first (classifier consumes structured data, not raw logs).

Fix:
- classify-test-failure.py advisory classifier:
  * Heuristic patterns with confidence weights
  * UNKNOWN class when top score < 0.6
  * FLAKY detection via previous_runs[] same-SHA passes
  * Output: {class, confidence, reasons[], evidence_refs}
- test.md argument-hint adds --retry-only
- fix-loop-and-verdict.md adds:
  * --retry-only handler at top (skip classify + fix, re-run once)
  * UNKNOWN + FLAKY class in 3b
  * 3b-flaky quarantine section
  * Advisory classifier invocation
  * CROSS-PHASE-DEPS for cross-phase ripple (instead of grep)

Coverage:
  1. test.md argument-hint includes --retry-only
  2. fix-loop-and-verdict.md has --retry-only handler
  3. fix-loop-and-verdict.md mentions UNKNOWN class
  4. fix-loop-and-verdict.md mentions FLAKY class
  5. fix-loop-and-verdict.md cites advisory classifier
  6. fix-loop-and-verdict.md cites CROSS-PHASE-DEPS for ripple
  7. classifier returns CODE_BUG for TypeError + high confidence
  8. classifier returns INFRA_ISSUE for ECONNREFUSED + high confidence
  9. classifier returns SPEC_GAP for locator-not-found
  10. classifier returns FLAKY when previous_runs has same-SHA pass
  11. classifier returns UNKNOWN when no pattern matches
  12. classifier returns UNKNOWN when top confidence < ceiling
  13. classifier emits evidence_refs for matched signals
  14. Mirror parity (test.md, fix-loop-and-verdict.md, classifier)
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEST_MD = REPO / "commands" / "vg" / "test.md"
TEST_MD_MIRROR = REPO / ".claude" / "commands" / "vg" / "test.md"
FIXLOOP = REPO / "commands" / "vg" / "_shared" / "test" / "fix-loop-and-verdict.md"
FIXLOOP_MIRROR = REPO / ".claude" / "commands" / "vg" / "_shared" / "test" / "fix-loop-and-verdict.md"
CLASSIFIER = REPO / "scripts" / "classify-test-failure.py"
CLASSIFIER_MIRROR = REPO / ".claude" / "scripts" / "classify-test-failure.py"


def _read(p): return p.read_text(encoding="utf-8")


def _classify(report: dict) -> dict:
    r = subprocess.run(
        ["python", str(CLASSIFIER), "--input", "-"],
        input=json.dumps(report),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 0, f"classifier failed: {r.stderr}"
    return json.loads(r.stdout)


def test_test_md_argument_hint_has_retry_only():
    body = _read(TEST_MD)
    assert "--retry-only" in body
    # Should appear in argument-hint line
    arg_line = [l for l in body.splitlines() if l.startswith("argument-hint:")][0]
    assert "--retry-only" in arg_line


def test_fix_loop_has_retry_only_handler():
    body = _read(FIXLOOP)
    assert "--retry-only" in body
    assert "B66" in body
    # Must reference re-run without classify + fix
    assert "skip classify" in body.lower() or "skip classify + fix" in body.lower()


def test_fix_loop_mentions_unknown_class():
    body = _read(FIXLOOP)
    assert "UNKNOWN" in body
    # Must explain confidence threshold
    assert "0.6" in body or "0.7" in body or "confidence" in body.lower()


def test_fix_loop_mentions_flaky_class():
    body = _read(FIXLOOP)
    assert "FLAKY" in body
    assert "KNOWN-FLAKY" in body or "flaky" in body.lower()


def test_fix_loop_cites_classifier_script():
    body = _read(FIXLOOP)
    assert "classify-test-failure.py" in body
    assert "advisory" in body.lower()


def test_fix_loop_cites_cross_phase_deps():
    body = _read(FIXLOOP)
    assert "CROSS-PHASE-DEPS" in body
    # Must explain why (vs grep FP). String may span lines — normalize whitespace.
    normalized = " ".join(body.split()).lower()
    assert "grep" in normalized
    assert "false-positive" in normalized or "false positive" in normalized


def test_classifier_code_bug_typeerror():
    result = _classify({
        "sha": "abc", "error": "TypeError: Cannot read properties of undefined",
        "stack": "", "console": [], "network": [],
    })
    assert result["class"] == "CODE_BUG"
    assert result["confidence"] >= 0.7


def test_classifier_infra_econnrefused():
    result = _classify({
        "sha": "abc", "error": "ECONNREFUSED 127.0.0.1:5432",
        "stack": "", "console": [], "network": [],
    })
    assert result["class"] == "INFRA_ISSUE"
    assert result["confidence"] >= 0.7


def test_classifier_spec_gap_locator_strong_signal():
    """Multiple SPEC_GAP signals stack confidence above ceiling."""
    result = _classify({
        "sha": "abc",
        "error": "locator getByTestId('submit-btn') not found in DOM",
        "stack": "data-testid=\"submit-btn\" not in DOM",
        "console": [], "network": [],
    })
    # Two patterns matched → confidence > 0.6 → SPEC_GAP
    assert result["class"] == "SPEC_GAP"


def test_classifier_spec_gap_locator_weak_signal_returns_unknown():
    """Single weak signal below ceiling → UNKNOWN (codex MAJOR contract)."""
    result = _classify({
        "sha": "abc",
        "error": "locator getByTestId('submit-btn') not found in DOM",
        "stack": "", "console": [], "network": [],
    })
    # Single 0.45 weight signal below 0.6 → UNKNOWN
    # This is the safety net: don't auto-dispatch fixer on weak evidence
    assert result["class"] == "UNKNOWN"


def test_classifier_flaky_via_previous_runs():
    result = _classify({
        "sha": "abc", "error": "some intermittent failure",
        "stack": "", "console": [], "network": [],
        "previous_runs": [
            {"sha": "abc", "status": "pass"},
            {"sha": "abc", "status": "fail"},
            {"sha": "abc", "status": "pass"},
        ],
    })
    assert result["class"] == "FLAKY"
    assert result["confidence"] >= 0.7


def test_classifier_unknown_when_no_match():
    result = _classify({
        "sha": "abc", "error": "some completely unrecognized failure",
        "stack": "", "console": [], "network": [],
    })
    assert result["class"] == "UNKNOWN"


def test_classifier_unknown_when_below_ceiling():
    """Single weak signal below 0.6 → UNKNOWN (only one pattern matches)."""
    result = _classify({
        "sha": "abc",
        # Only single 40x signal weighted 0.3, no other patterns hit
        "error": "expected response 404",
        "stack": "", "console": [], "network": [],
    })
    # Below 0.6 ceiling → UNKNOWN safety net
    assert result["class"] == "UNKNOWN"


def test_classifier_emits_evidence_refs():
    result = _classify({
        "sha": "abc",
        "error": "TypeError: x is undefined",
        "stack": "", "console": ["Cannot read properties of undefined (reading 'foo')"],
        "network": [],
    })
    assert result["class"] == "CODE_BUG"
    assert "evidence_refs" in result


def test_mirrors_in_sync():
    assert _read(TEST_MD) == _read(TEST_MD_MIRROR)
    assert _read(FIXLOOP) == _read(FIXLOOP_MIRROR)
    assert _read(CLASSIFIER) == _read(CLASSIFIER_MIRROR)
