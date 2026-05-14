"""tests/test_batch27_security_audit_fail.py — G3 security audit FAIL on findings."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
RS = REPO / "commands" / "vg" / "_shared" / "test" / "regression-security.md"


def test_security_status_default_not_unconditional_pass():
    body = RS.read_text(encoding="utf-8")
    # Use step-active marker to find the actual 5f_security_audit execution block
    sec_idx = body.find("step-active 5f_security_audit")
    if sec_idx < 0:
        sec_idx = body.find("5f_security_audit")
    assert sec_idx > 0
    # Search the full body from sec_idx to end of 5f section
    # (section ends at next ## STEP header)
    import re
    next_step = re.search(r'\n## STEP 7\.3', body[sec_idx:])
    end_idx = sec_idx + next_step.start() if next_step else len(body)
    block = body[sec_idx:end_idx]
    # Must NOT have unconditional 'SECURITY_STATUS=PASS' as default after Tier check
    # Must set status based on findings count
    assert ("SECURITY_STATUS=FAIL" in block or 'SECURITY_STATUS="FAIL"' in block or
            "security_audit.failed" in block or "test.security_audit_failed" in block), (
        "G3 Batch 27: 5f_security_audit must set SECURITY_STATUS=FAIL when "
        "Tier 0/1/2 finds critical/high severity issues. Currently default "
        "PASS regardless of findings."
    )
