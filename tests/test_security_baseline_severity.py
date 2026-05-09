"""v2.67.0 #163 — security baseline severity field + REVIEW-FINDINGS.json merge.

verify-security-baseline.py emitted Evidence objects without a severity
field, and output went only to a .tmp/ log — never reaching the
AUTO-FIX-TASKS routing pipeline. As a result, 77 cookie files flagged in
the PrintwayV3 dogfood produced 0 fix tasks.

Tests verify:
1. Evidence emissions include a severity field (CRITICAL/HIGH/MEDIUM).
2. TLS issues classify as CRITICAL.
3. HSTS missing classifies as HIGH.
4. Cookie attribute missing classifies as MEDIUM.
5. merge_to_review_findings() writer is wired so security findings reach
   REVIEW-FINDINGS.json (not just .tmp/ log).
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validators" / "verify-security-baseline.py"


def _src() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_security_baseline_emits_severity():
    src = _src()
    # Must populate severity field on Evidence emissions
    assert re.search(r"severity\s*=\s*['\"](?:CRITICAL|HIGH|MEDIUM)", src), (
        "Evidence emissions must include severity field "
        "(CRITICAL/HIGH/MEDIUM)"
    )


def test_tls_critical_severity():
    src = _src()
    # TLS missing/outdated → CRITICAL
    assert re.search(
        r"tls_outdated.{0,400}severity\s*=\s*['\"]CRITICAL",
        src,
        re.DOTALL,
    ), "TLS outdated must classify as CRITICAL"


def test_hsts_high_severity():
    src = _src()
    assert re.search(
        r"hsts_missing.{0,400}severity\s*=\s*['\"]HIGH",
        src,
        re.DOTALL,
    ), "HSTS missing must classify as HIGH"


def test_cookie_medium_severity():
    src = _src()
    assert re.search(
        r"cookie_flags_missing.{0,400}severity\s*=\s*['\"]MEDIUM",
        src,
        re.DOTALL,
    ), "Cookie flags missing must classify as MEDIUM"


def test_findings_written_to_review_findings_json():
    """Security baseline must merge into REVIEW-FINDINGS.json (not just .tmp/)."""
    src = _src()
    assert "REVIEW-FINDINGS.json" in src, (
        "security baseline must write to REVIEW-FINDINGS.json"
    )
    # Helper function must exist
    assert re.search(r"def\s+merge_to_review_findings\s*\(", src), (
        "merge_to_review_findings() helper must be defined"
    )
