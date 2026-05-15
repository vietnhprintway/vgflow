"""tests/test_batch45_codex_f6_f9.py — Batch 45.

F6 CRITICAL: edge-case gate at delegation.md:404-434 depends on
EDGE_CASES_AVAILABLE / GOALS_LIST / ALLOW_SKIP env vars that no
orchestrator step sets → gate is dead code.

F9 HIGH: NOT_SCANNED blocked only in /vg:test preflight, not in
test-spec. Test-spec generates artifacts based on stale review.
"""
from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEL = REPO / "commands" / "vg" / "_shared" / "test" / "codegen" / "delegation.md"
DEL_MIRROR = REPO / ".claude" / "commands" / "vg" / "_shared" / "test" / "codegen" / "delegation.md"
TEST_SPEC = REPO / "commands" / "vg" / "test-spec.md"
TEST_SPEC_MIRROR = REPO / ".claude" / "commands" / "vg" / "test-spec.md"


def test_f6_edge_case_gate_uses_deterministic_check():
    """Edge case gate must NOT rely on EDGE_CASES_AVAILABLE env var.
    Must check directory presence directly."""
    body = DEL.read_text(encoding="utf-8")
    f25_idx = body.find("### F.2.5")
    assert f25_idx > 0
    block = body[f25_idx:f25_idx + 2500]
    # Must do directory existence check, not env var
    assert '[ -d "${PHASE_DIR}/EDGE-CASES" ]' in block or \
           '-d "${PHASE_DIR}/EDGE-CASES/"' in block, (
        "Batch 45 F6: edge-case gate must check directory existence "
        "deterministically, not depend on unset env var EDGE_CASES_AVAILABLE"
    )


def test_f6_goals_list_derived_inline():
    """GOALS_LIST must be derived inline (e.g., from EDGE-CASES/*.md) or
    via existing vg-load pattern. Not depend on caller setting it."""
    body = DEL.read_text(encoding="utf-8")
    f25_idx = body.find("### F.2.5")
    block = body[f25_idx:f25_idx + 2500]
    # Must iterate EDGE-CASES/*.md or call vg-load --list
    has_inline = (
        'EDGE-CASES/G-' in block
        or 'EDGE-CASES/*.md' in block
        or 'vg-load' in block.lower() and '--list' in block.lower()
        or 'find "${PHASE_DIR}/EDGE-CASES"' in block
    )
    assert has_inline, (
        "Batch 45 F6: goal list must be derived inline from EDGE-CASES dir, "
        "not depend on unset GOALS_LIST env"
    )


def test_f6_skip_via_arguments_flag():
    """ALLOW_SKIP must be replaced with explicit --skip-edge-coverage
    flag check via ARGUMENTS pattern."""
    body = DEL.read_text(encoding="utf-8")
    f25_idx = body.find("### F.2.5")
    block = body[f25_idx:f25_idx + 2500]
    assert "--skip-edge-coverage" in block or "--allow-edge-shortfall" in block, (
        "Batch 45 F6: gate must use --skip-edge-coverage flag via ARGUMENTS, "
        "not unset ALLOW_SKIP env"
    )


def test_f9_test_spec_blocks_not_scanned():
    """test-spec.md must check GOAL-COVERAGE-MATRIX for NOT_SCANNED rows
    before generating specs. Currently NOT_SCANNED only blocked at /vg:test."""
    body = TEST_SPEC.read_text(encoding="utf-8")
    assert "NOT_SCANNED" in body, (
        "Batch 45 F9: test-spec.md must check NOT_SCANNED in matrix"
    )
    # Must block / exit on shortfall
    spec_block_idx = body.find("NOT_SCANNED")
    assert spec_block_idx > 0
    block = body[max(0, spec_block_idx - 500):spec_block_idx + 1500]
    assert "exit 1" in block, (
        "Batch 45 F9: test-spec NOT_SCANNED detection must exit 1"
    )


def test_mirrors_in_sync():
    assert DEL.read_text(encoding="utf-8") == DEL_MIRROR.read_text(encoding="utf-8")
    assert TEST_SPEC.read_text(encoding="utf-8") == TEST_SPEC_MIRROR.read_text(encoding="utf-8")
