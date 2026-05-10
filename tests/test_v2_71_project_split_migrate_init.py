"""v2.71.0 T5 — migrate-and-init split (FINAL extraction)."""
from pathlib import Path
import re


def test_migrate_init_subfile_exists():
    p = Path("commands/vg/_shared/project/migrate-and-init.md")
    assert p.exists()


def test_migrate_init_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/project/migrate-and-init.md").read_text(encoding="utf-8")
    assert '<step name="8_mode_migrate">' in body
    assert '<step name="9_mode_init_only">' in body
    assert '<step name="10_complete">' in body


def test_project_md_routes_to_migrate_init_subfile():
    body = Path("commands/vg/project.md").read_text(encoding="utf-8")
    assert "_shared/project/migrate-and-init.md" in body


def test_migrate_init_subfile_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/project/migrate-and-init.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/project/migrate-and-init.md").read_bytes()
    assert canonical == mirror


def test_project_md_mirror_byte_identity():
    canonical = Path("commands/vg/project.md").read_bytes()
    mirror = Path(".claude/commands/vg/project.md").read_bytes()
    assert canonical == mirror


def test_extracted_steps_no_longer_in_project_md_body():
    body = Path("commands/vg/project.md").read_text(encoding="utf-8")
    # Step XML bodies should be gone (slim routing reference only)
    for step_name in ("8_mode_migrate", "9_mode_init_only", "10_complete"):
        pattern = rf'<step name="{step_name}">.*?</step>'
        matches = re.findall(pattern, body, re.DOTALL)
        for m in matches:
            assert len(m) < 500, (
                f"step {step_name} body should be replaced by slim routing reference"
            )
