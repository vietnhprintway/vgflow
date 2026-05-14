"""tests/test_f5_reviewer_writes_verdict.py — F5 reviewer verdict contract."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
FINAL = REPO / ".claude" / "agents" / "vg-build-final-reviewer" / "SKILL.md"
SPEC = REPO / ".claude" / "agents" / "vg-build-spec-reviewer" / "SKILL.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_final_reviewer_allows_write():
    body = _read(FINAL)
    # allowed-tools must include Write
    fm_end = body.find("\n---\n", 4)
    fm = body[:fm_end] if fm_end > 0 else body[:2000]
    assert "Write" in fm, (
        "F5: vg-build-final-reviewer must have Write in allowed-tools so it "
        "can persist verdict to disk (Batch 15 gate expects file on disk)"
    )


def test_final_reviewer_documents_verdict_file_write():
    body = _read(FINAL)
    assert ".final-review/verdict.md" in body, (
        "F5: vg-build-final-reviewer SKILL.md must instruct the agent to "
        "write verdict to ${PHASE_DIR}/.final-review/verdict.md (matches "
        "Batch 15 gate in build/close.md)"
    )


def test_spec_reviewer_allows_write():
    body = _read(SPEC)
    fm_end = body.find("\n---\n", 4)
    fm = body[:fm_end] if fm_end > 0 else body[:2000]
    assert "Write" in fm, "F5: vg-build-spec-reviewer must have Write in allowed-tools"


def test_spec_reviewer_documents_verdict_file_write():
    body = _read(SPEC)
    assert ".spec-review/" in body and "verdict" in body.lower(), (
        "F5: vg-build-spec-reviewer must instruct agent to write verdict to "
        "${PHASE_DIR}/.spec-review/{task_id}.md (matches Batch 15 gate in "
        "build/post-execution-overview.md)"
    )


def test_final_reviewer_strict_rules_no_longer_read_only():
    body = _read(FINAL)
    # The old "READ-ONLY agent. You MUST NOT modify any files" must be removed
    # or qualified. Allow if there's an explicit exception for the verdict file.
    if "READ-ONLY agent" in body or "MUST NOT modify any files" in body:
        # Acceptable if explicitly excepted for verdict file
        assert "except" in body.lower() or "verdict" in body.lower(), (
            "F5: SKILL.md must remove or qualify the 'READ-ONLY / MUST NOT "
            "modify any files' rule — agent now writes verdict file"
        )
