"""tests/test_c6_goal_verifier_strict_schema.py — C6 strict schema validation."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OVERVIEW = REPO / "commands" / "vg" / "_shared" / "test" / "goal-verification" / "overview.md"


def test_post_spawn_validates_goal_ids_against_index():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Must reference vg-load index reconciliation
    assert ("vg-load" in body or "GOAL_INDEX" in body or "goal_id_set" in body), (
        "C6: post-spawn validation must reconcile goals_verified[].goal_id "
        "against vg-load index (or equivalent goal ID source)"
    )


def test_post_spawn_validates_status_enum():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Status must be in enum {PASSED, FAILED, BLOCKED, UNREACHABLE, SKIPPED}
    enum_present = all(s in body for s in ["PASSED", "FAILED"])
    assert enum_present, (
        "C6: post-spawn validation must enforce status enum"
    )
    # New: explicit STATUS_ENUM check
    assert ("STATUS_ENUM" in body or "valid_statuses" in body or "status_enum" in body), (
        "C6: must check status against an explicit enum, not just shape"
    )


def test_post_spawn_validates_evidence_ref_exists():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Evidence ref path must be verified
    assert "evidence_ref" in body
    assert ("exists" in body.lower() and "evidence" in body.lower()) or "evidence_ref_missing" in body, (
        "C6: post-spawn validation must check evidence_ref file existence"
    )
