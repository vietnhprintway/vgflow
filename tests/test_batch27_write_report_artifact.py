"""tests/test_batch27_write_report_artifact.py — G1 write_report SANDBOX-TEST.md."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
CLOSE = REPO / "commands" / "vg" / "_shared" / "test" / "close.md"


def test_close_has_bash_write_sandbox_test():
    body = CLOSE.read_text(encoding="utf-8")
    # Must have actual bash cat > or python Path().write_text writing SANDBOX-TEST.md
    # NOT just a prose template
    sandbox_idx = body.find("SANDBOX-TEST.md")
    assert sandbox_idx > 0
    # Find any bash block that ACTUALLY writes the file
    has_real_write = (
        ('cat > "${PHASE_DIR}/SANDBOX-TEST.md"' in body) or
        ("write_text" in body and "SANDBOX-TEST" in body) or
        ('SANDBOX_TEST="${PHASE_DIR}/SANDBOX-TEST.md"' in body and "EOF" in body)
    )
    assert has_real_write, (
        "G1 Batch 27: close.md must contain BASH that writes "
        "${PHASE_DIR}/SANDBOX-TEST.md (not just prose markdown template). "
        "AI can extend later — bash MUST create the file with at least "
        "frontmatter + verdict so Stop hook must_write passes."
    )


def test_sandbox_test_creation_before_git_add():
    body = CLOSE.read_text(encoding="utf-8")
    git_add_idx = body.find('git add "${PHASE_DIR}/SANDBOX-TEST.md"')
    if git_add_idx < 0:
        git_add_idx = body.find('git add ${PHASE_DIR}/SANDBOX-TEST.md')
    assert git_add_idx > 0
    # Before git add, must have write operation
    pre_add = body[:git_add_idx]
    has_write_before = (
        'cat > "${PHASE_DIR}/SANDBOX-TEST.md"' in pre_add or
        ('SANDBOX_TEST=' in pre_add and 'EOF' in pre_add)
    )
    assert has_write_before, (
        "G1: bash Write op for SANDBOX-TEST.md must come BEFORE git add"
    )
