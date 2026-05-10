"""v2.74.0 T3 — scope-review.md resolve-and-close section split (final)."""
from pathlib import Path


def test_resolve_and_close_subfile_exists():
    p = Path("commands/vg/_shared/scope-review/resolve-and-close.md")
    assert p.exists(), \
        "v2.74.0 T3 must create _shared/scope-review/resolve-and-close.md"


def test_resolve_and_close_subfile_contains_extracted_steps():
    body = Path(
        "commands/vg/_shared/scope-review/resolve-and-close.md"
    ).read_text(encoding="utf-8")
    expected_steps = [
        "4_resolution",
        "4.5_baseline_write_and_telemetry",
        "5_commit_and_next",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, \
            f"resolve-and-close.md missing step tag: {s}"


def test_scope_review_md_routes_to_resolve_and_close_subfile():
    body = Path("commands/vg/scope-review.md").read_text(encoding="utf-8")
    assert "_shared/scope-review/resolve-and-close.md" in body, \
        "scope-review.md must reference _shared/scope-review/resolve-and-close.md after T3 split"


def test_scope_review_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted resolve-and-close step <step name=...> tags are gone from scope-review.md."""
    body = Path("commands/vg/scope-review.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="4_resolution">',
        '<step name="4.5_baseline_write_and_telemetry">',
        '<step name="5_commit_and_next">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"scope-review.md still contains extracted step tag {tag} (should live in _shared/scope-review/resolve-and-close.md)"


def test_resolve_and_close_mirror_byte_identity():
    canonical = Path(
        "commands/vg/_shared/scope-review/resolve-and-close.md"
    ).read_bytes()
    mirror = Path(
        ".claude/commands/vg/_shared/scope-review/resolve-and-close.md"
    ).read_bytes()
    assert canonical == mirror, \
        "_shared/scope-review/resolve-and-close.md mirrors must be byte-identical"


def test_scope_review_md_mirror_byte_identity():
    canonical = Path("commands/vg/scope-review.md").read_bytes()
    mirror = Path(".claude/commands/vg/scope-review.md").read_bytes()
    assert canonical == mirror, "commands/vg/scope-review.md mirrors must be byte-identical"
