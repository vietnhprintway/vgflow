"""v2.70.0 T9 — review.md close section split (final extraction)."""
from pathlib import Path


def test_close_subfile_exists():
    p = Path("commands/vg/_shared/review/close.md")
    assert p.exists(), "v2.70.0 T9 must create _shared/review/close.md"


def test_close_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/review/close.md").read_text(encoding="utf-8")
    expected_steps = [
        "unreachable_triage",
        "crossai_review",
        "write_artifacts",
        "bootstrap_reflection",
        "complete",
    ]
    for s in expected_steps:
        assert s in body, f"close.md missing step: {s}"


def test_review_md_routes_to_close_subfile():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    assert "_shared/review/close.md" in body, \
        "review.md must reference _shared/review/close.md after T9 split"


def test_review_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted close step <step name=...> tags are gone from review.md."""
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="unreachable_triage"',
        '<step name="crossai_review"',
        '<step name="write_artifacts"',
        '<step name="bootstrap_reflection"',
        '<step name="complete"',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"review.md still contains extracted step tag {tag} (should live in _shared/review/close.md)"


def test_close_subfile_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/review/close.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/review/close.md").read_bytes()
    assert canonical == mirror, "_shared/review/close.md mirrors must be byte-identical"


def test_review_md_mirror_byte_identity():
    canonical = Path("commands/vg/review.md").read_bytes()
    mirror = Path(".claude/commands/vg/review.md").read_bytes()
    assert canonical == mirror, "commands/vg/review.md mirrors must be byte-identical"
