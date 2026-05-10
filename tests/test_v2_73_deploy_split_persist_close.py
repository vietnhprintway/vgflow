"""v2.73.0 T3 — deploy.md persist-and-close section split."""
from pathlib import Path


def test_persist_close_subfile_exists():
    p = Path("commands/vg/_shared/deploy/persist-and-close.md")
    assert p.exists(), "v2.73.0 T3 must create _shared/deploy/persist-and-close.md"


def test_persist_close_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/deploy/persist-and-close.md").read_text(encoding="utf-8")
    expected_steps = [
        "2_persist_summary",
        "complete",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, f"persist-and-close.md missing step tag: {s}"


def test_deploy_md_routes_to_persist_close_subfile():
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    assert "_shared/deploy/persist-and-close.md" in body, \
        "deploy.md must reference _shared/deploy/persist-and-close.md after T3 split"


def test_deploy_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted persist-close step <step name=...> tags are gone from deploy.md."""
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="2_persist_summary">',
        '<step name="complete">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"deploy.md still contains extracted step tag {tag} (should live in _shared/deploy/persist-and-close.md)"


def test_persist_close_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/deploy/persist-and-close.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/deploy/persist-and-close.md").read_bytes()
    assert canonical == mirror, "_shared/deploy/persist-and-close.md mirrors must be byte-identical"


def test_deploy_md_mirror_byte_identity():
    canonical = Path("commands/vg/deploy.md").read_bytes()
    mirror = Path(".claude/commands/vg/deploy.md").read_bytes()
    assert canonical == mirror, "commands/vg/deploy.md mirrors must be byte-identical"
