"""tests/test_f4_browser_tour_evidence.py — F4 browser tour per-view evidence."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
AD = REPO / "commands" / "vg" / "_shared" / "review" / "api-and-discovery.md"


def test_per_view_scan_count_match():
    body = AD.read_text(encoding="utf-8")
    # Must have BASH enforcement: compare ASSIGNED_VIEWS to SCAN_COUNT with -ne
    # (not just documentation mentioning scan-*.json or views array)
    assert ("ASSIGNED_VIEWS" in body and "SCAN_COUNT" in body and "-ne" in body), (
        "F4: review browser tour must contain BASH gate comparing ASSIGNED_VIEWS "
        "to SCAN_COUNT using '-ne' (not just prose documentation of the schema)"
    )


def test_provenance_check_current_run():
    body = AD.read_text(encoding="utf-8")
    # Must have BASH enforcement with CURRENT_RUN_ID variable assignment
    # (not just prose/schema mentions of run_id)
    assert "CURRENT_RUN_ID" in body, (
        "F4: must have CURRENT_RUN_ID bash variable to check scan provenance "
        "against current run — cached scans from prior runs must be detected"
    )
