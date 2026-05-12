"""v2.70.0 T8 — review fix-loop-and-goals section moved to _shared/test/fix-loop-and-verdict.md.

v4.0 BREAKING: commands/vg/_shared/review/fix-loop-and-goals.md was moved to
commands/vg/_shared/test/fix-loop-and-verdict.md (commit e8bf98d).
Tests updated to reference new location.
"""
from pathlib import Path


def test_fix_loop_verdict_subfile_exists():
    p = Path("commands/vg/_shared/test/fix-loop-and-verdict.md")
    assert p.exists(), "v4.0: fix-loop content now lives in _shared/test/fix-loop-and-verdict.md"


def test_fix_loop_verdict_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/test/fix-loop-and-verdict.md").read_text(encoding="utf-8")
    # v4.0: phase3_fix_loop -> step5_fix_loop, phase4_goal_comparison -> step7_matrix_verdict
    expected_steps = [
        "step5_fix_loop",
        "step7_matrix_verdict",
    ]
    for s in expected_steps:
        assert s in body, f"fix-loop-and-verdict.md missing step: {s}"


def test_review_global_paths_file_not_in_review_shared():
    """v4.0: fix-loop-and-goals.md removed from _shared/review/ (moved to _shared/test/)."""
    old_path = Path("commands/vg/_shared/review/fix-loop-and-goals.md")
    assert not old_path.exists(), (
        "v4.0 moved fix-loop to _shared/test/fix-loop-and-verdict.md — "
        "old path must not exist"
    )


def test_fix_loop_verdict_subfile_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/test/fix-loop-and-verdict.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/test/fix-loop-and-verdict.md").read_bytes()
    assert canonical == mirror, "_shared/test/fix-loop-and-verdict.md mirrors must be byte-identical"


def test_review_md_mirror_byte_identity():
    canonical = Path("commands/vg/review.md").read_bytes()
    mirror = Path(".claude/commands/vg/review.md").read_bytes()
    assert canonical == mirror, "commands/vg/review.md mirrors must be byte-identical"
