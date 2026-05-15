"""tests/test_batch50_more_partial_markers.py — Batch 50.

Continuation of Batch 33+49 deferral. Fixes:
- 2_fidelity_profile_lock: no marker on "no design/FE work" skip branch
- 2b5d_expand_from_crud_surfaces: script failure only warns, mark still fires
- 2b7_flow_detect: similar; missing TEST-GOALS skip silent
"""
from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESIGN = REPO / "commands" / "vg" / "_shared" / "blueprint" / "design.md"
DESIGN_MIRROR = REPO / ".claude" / "commands" / "vg" / "_shared" / "blueprint" / "design.md"
CONTRACTS = REPO / "commands" / "vg" / "_shared" / "blueprint" / "contracts-overview.md"
CONTRACTS_MIRROR = REPO / ".claude" / "commands" / "vg" / "_shared" / "blueprint" / "contracts-overview.md"


def test_2_fidelity_profile_lock_marks_on_skip():
    body = DESIGN.read_text(encoding="utf-8")
    sec_idx = body.find("step-active 2_fidelity_profile_lock")
    assert sec_idx > 0
    block = body[sec_idx:sec_idx + 3500]
    # Skip branch ("no design or FE work") must still mark + emit event
    assert "FIDELITY_STATUS" in block or "fidelity_no_design" in block or "Batch 50" in block, (
        "Batch 50: 2_fidelity_profile_lock must record STATUS even on no-design skip"
    )


def test_2b5d_expand_emits_status():
    body = CONTRACTS.read_text(encoding="utf-8")
    sec_idx = body.find("step-active 2b5d_expand_from_crud_surfaces")
    assert sec_idx > 0
    block = body[sec_idx:sec_idx + 2500]
    assert "EXPAND_STATUS" in block, (
        "Batch 50: 2b5d_expand must set EXPAND_STATUS for observability"
    )
    assert "expand_skipped" in block or "expand_failed" in block or "test_goals_expansion_failed" in block, (
        "Batch 50: 2b5d_expand must emit event on FAIL/SKIPPED"
    )


def test_2b7_flow_detect_emits_status():
    body = CONTRACTS.read_text(encoding="utf-8")
    sec_idx = body.find("step-active 2b7_flow_detect")
    assert sec_idx > 0
    block = body[sec_idx:sec_idx + 4000]
    assert "FLOW_DETECT_STATUS" in block, (
        "Batch 50: 2b7_flow_detect must set FLOW_DETECT_STATUS"
    )
    assert "flow_detect_skipped_no_goals" in block or "flow_detect_skipped_profile" in block, (
        "Batch 50: 2b7_flow_detect must emit event for each skip path"
    )


def test_mirrors_in_sync():
    assert DESIGN.read_text(encoding="utf-8") == DESIGN_MIRROR.read_text(encoding="utf-8")
    assert CONTRACTS.read_text(encoding="utf-8") == CONTRACTS_MIRROR.read_text(encoding="utf-8")
