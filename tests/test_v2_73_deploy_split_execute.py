"""v2.73.0 T2 — deploy.md execute section split."""
from pathlib import Path


def test_execute_subfile_exists():
    p = Path("commands/vg/_shared/deploy/execute.md")
    assert p.exists(), "v2.73.0 T2 must create _shared/deploy/execute.md"


def test_execute_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/deploy/execute.md").read_text(encoding="utf-8")
    expected_steps = [
        "1_deploy_per_env",
    ]
    for s in expected_steps:
        assert f'<step name="{s}">' in body, f"execute.md missing step tag: {s}"


def test_deploy_md_routes_to_execute_subfile():
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    assert "_shared/deploy/execute.md" in body, \
        "deploy.md must reference _shared/deploy/execute.md after T2 split"


def test_deploy_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted execute step <step name=...> tags are gone from deploy.md."""
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="1_deploy_per_env">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"deploy.md still contains extracted step tag {tag} (should live in _shared/deploy/execute.md)"


def test_execute_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/deploy/execute.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/deploy/execute.md").read_bytes()
    assert canonical == mirror, "_shared/deploy/execute.md mirrors must be byte-identical"


def test_deploy_md_mirror_byte_identity():
    canonical = Path("commands/vg/deploy.md").read_bytes()
    mirror = Path(".claude/commands/vg/deploy.md").read_bytes()
    assert canonical == mirror, "commands/vg/deploy.md mirrors must be byte-identical"
