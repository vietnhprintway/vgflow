"""v2.74.0 T2 — scope-review.md cross-ref-review-write section split."""
from pathlib import Path


def test_cross_ref_subfile_exists():
    p = Path("commands/vg/_shared/scope-review/cross-ref-review-write.md")
    assert p.exists(), \
        "v2.74.0 T2 must create _shared/scope-review/cross-ref-review-write.md"


def test_cross_ref_subfile_contains_extracted_steps():
    body = Path(
        "commands/vg/_shared/scope-review/cross-ref-review-write.md"
    ).read_text(encoding="utf-8")
    expected_steps = [
        "1_cross_reference",
        "2_crossai_review",
        "3_write_report",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, \
            f"cross-ref-review-write.md missing step tag: {s}"


def test_scope_review_md_routes_to_cross_ref_subfile():
    body = Path("commands/vg/scope-review.md").read_text(encoding="utf-8")
    assert "_shared/scope-review/cross-ref-review-write.md" in body, \
        "scope-review.md must reference _shared/scope-review/cross-ref-review-write.md after T2 split"


def test_scope_review_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted cross-ref step <step name=...> tags are gone from scope-review.md."""
    body = Path("commands/vg/scope-review.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="1_cross_reference">',
        '<step name="2_crossai_review">',
        '<step name="3_write_report">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"scope-review.md still contains extracted step tag {tag} (should live in _shared/scope-review/cross-ref-review-write.md)"


def test_cross_ref_mirror_byte_identity():
    canonical = Path(
        "commands/vg/_shared/scope-review/cross-ref-review-write.md"
    ).read_bytes()
    mirror = Path(
        ".claude/commands/vg/_shared/scope-review/cross-ref-review-write.md"
    ).read_bytes()
    assert canonical == mirror, \
        "_shared/scope-review/cross-ref-review-write.md mirrors must be byte-identical"


def test_scope_review_md_mirror_byte_identity():
    canonical = Path("commands/vg/scope-review.md").read_bytes()
    mirror = Path(".claude/commands/vg/scope-review.md").read_bytes()
    assert canonical == mirror, "commands/vg/scope-review.md mirrors must be byte-identical"
