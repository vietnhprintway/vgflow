"""v2.73.0 T6 — update.md preflight section split."""
from pathlib import Path


def test_preflight_subfile_exists():
    p = Path("commands/vg/_shared/update/preflight.md")
    assert p.exists(), "v2.73.0 T6 must create _shared/update/preflight.md"


def test_preflight_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/update/preflight.md").read_text(encoding="utf-8")
    expected_steps = [
        "0_preflight",
        "1_check_only_mode",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, f"preflight.md missing step tag: {s}"


def test_update_md_routes_to_preflight_subfile():
    body = Path("commands/vg/update.md").read_text(encoding="utf-8")
    assert "_shared/update/preflight.md" in body, \
        "update.md must reference _shared/update/preflight.md after T6 split"


def test_update_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted preflight step <step name=...> tags are gone from update.md."""
    body = Path("commands/vg/update.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="0_preflight">',
        '<step name="1_check_only_mode">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"update.md still contains extracted step tag {tag} (should live in _shared/update/preflight.md)"


def test_preflight_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/update/preflight.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/update/preflight.md").read_bytes()
    assert canonical == mirror, "_shared/update/preflight.md mirrors must be byte-identical"


def test_update_md_mirror_byte_identity():
    canonical = Path("commands/vg/update.md").read_bytes()
    mirror = Path(".claude/commands/vg/update.md").read_bytes()
    assert canonical == mirror, "commands/vg/update.md mirrors must be byte-identical"
