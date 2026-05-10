"""v2.71.0 T2 — project.md routing section split."""
from pathlib import Path


def test_routing_subfile_exists():
    p = Path("commands/vg/_shared/project/routing.md")
    assert p.exists(), "v2.71.0 T2 must create _shared/project/routing.md"


def test_routing_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/project/routing.md").read_text(encoding="utf-8")
    expected_steps = [
        "1_route_mode",
        "2a_resume_check",
        "2b_mode_menu",
        "3_mode_view",
    ]
    for s in expected_steps:
        assert s in body, f"routing.md missing step: {s}"


def test_project_md_routes_to_routing_subfile():
    body = Path("commands/vg/project.md").read_text(encoding="utf-8")
    assert "_shared/project/routing.md" in body, \
        "project.md must reference _shared/project/routing.md after T2 split"


def test_project_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted routing step <step name=...> tags are gone from project.md."""
    body = Path("commands/vg/project.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="1_route_mode">',
        '<step name="2a_resume_check">',
        '<step name="2b_mode_menu">',
        '<step name="3_mode_view">',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"project.md still contains extracted step tag {tag} (should live in _shared/project/routing.md)"


def test_routing_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/project/routing.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/project/routing.md").read_bytes()
    assert canonical == mirror, "_shared/project/routing.md mirrors must be byte-identical"


def test_project_md_mirror_byte_identity():
    canonical = Path("commands/vg/project.md").read_bytes()
    mirror = Path(".claude/commands/vg/project.md").read_bytes()
    assert canonical == mirror, "commands/vg/project.md mirrors must be byte-identical"
