"""v2.75.0 T8 — debug.md verify-and-close section split."""
from pathlib import Path


def test_verify_and_close_subfile_exists():
    p = Path("commands/vg/_shared/debug/verify-and-close.md")
    assert p.exists(), "v2.75.0 T8 must create _shared/debug/verify-and-close.md"


def test_verify_and_close_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/debug/verify-and-close.md").read_text(encoding="utf-8")
    expected_steps = [
        "3_verify_and_loop",
        "4_complete",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, f"verify-and-close.md missing step tag: {s}"


def test_debug_md_routes_to_verify_and_close_subfile():
    body = Path("commands/vg/debug.md").read_text(encoding="utf-8")
    assert "_shared/debug/verify-and-close.md" in body, \
        "debug.md must reference _shared/debug/verify-and-close.md after T8 split"


def test_debug_md_no_longer_contains_extracted_step_bodies():
    body = Path("commands/vg/debug.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="3_verify_and_loop">',
        '<step name="4_complete">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"debug.md still contains extracted step tag {tag} (should live in _shared/debug/verify-and-close.md)"


def test_verify_and_close_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/debug/verify-and-close.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/debug/verify-and-close.md").read_bytes()
    assert canonical == mirror, "_shared/debug/verify-and-close.md mirrors must be byte-identical"


def test_debug_md_mirror_byte_identity():
    canonical = Path("commands/vg/debug.md").read_bytes()
    mirror = Path(".claude/commands/vg/debug.md").read_bytes()
    assert canonical == mirror, "commands/vg/debug.md mirrors must be byte-identical"
