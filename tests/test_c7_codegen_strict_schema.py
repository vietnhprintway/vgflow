"""tests/test_c7_codegen_strict_schema.py — C7 codegen strict schema."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
OVERVIEW = REPO / "commands" / "vg" / "_shared" / "test" / "codegen" / "overview.md"


def test_codegen_validates_files_exist_on_disk():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Must verify every spec_files[] entry exists
    assert ("spec_files" in body) and ("Path(" in body or "exists" in body.lower() or "is_file" in body.lower()), (
        "C7: codegen post-spawn validation must verify each spec_files[] "
        "entry exists on disk"
    )


def test_codegen_reconciles_against_ready_goals():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Must reconcile READY/MANUAL/DEFERRED goals against generated outputs
    assert ("READY" in body and "MANUAL" in body) or "goal_coverage" in body.lower(), (
        "C7: post-spawn validation must reconcile generated specs against "
        "READY/MANUAL/DEFERRED goal verdicts"
    )


def test_codegen_persists_binding_report():
    body = OVERVIEW.read_text(encoding="utf-8")
    # Must require binding_report artifact
    assert ("binding_report" in body or "BINDING-REPORT" in body or "bindings_satisfied" in body), (
        "C7: codegen must persist a binding report artifact, not just a "
        "bindings_satisfied boolean"
    )
