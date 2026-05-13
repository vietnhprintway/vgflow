"""tests/test_f11_review_step_status_ledger.py — F11 review lane ledger."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

REVIEW_STEP_FILES = [
    "commands/vg/_shared/review/preflight.md",
    "commands/vg/_shared/review/api-and-discovery.md",
    "commands/vg/_shared/review/code-scan.md",
    "commands/vg/_shared/review/lens-and-findings.md",
    "commands/vg/_shared/review/url-and-error.md",
    "commands/vg/_shared/review/matrix-intent.md",
]


def test_at_least_one_review_step_emits_ledger():
    """Review lane must have at least 2 step ledger emits — symmetry with test C5."""
    emits = 0
    for rel in REVIEW_STEP_FILES:
        body = (REPO / rel).read_text(encoding="utf-8")
        if "step-status-ledger.py" in body or "review-step-status" in body:
            emits += 1
    assert emits >= 2, (
        f"F11: at least 2 review sub-steps must emit step-status ledger entries "
        f"(symmetric with C5 test lane). Got {emits}."
    )


def test_review_close_reads_ledger():
    body = (REPO / "commands/vg/_shared/review/close.md").read_text(encoding="utf-8")
    assert ".review-step-status.json" in body or "step-status-ledger" in body or "REVIEW_STEP_LEDGER" in body, (
        "F11: review/close.md must read review step-status ledger for "
        "verdict computation (symmetric with test/close.md from C5 Batch 9)"
    )
