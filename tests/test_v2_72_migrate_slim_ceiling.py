"""v2.72.0 T5 — migrate.md slim ceiling."""
from pathlib import Path


def test_migrate_md_under_slim_ceiling():
    body = Path("commands/vg/migrate.md").read_text(encoding="utf-8")
    line_count = len(body.splitlines())
    # Original 1301 → split target ≤ 400 (70%+ reduction)
    assert line_count <= 400, \
        f"v2.72.0 split target: migrate.md ≤ 400 lines (got {line_count})"


def test_shared_migrate_dir_has_4_files():
    migrate_dir = Path("commands/vg/_shared/migrate")
    md_files = sorted(migrate_dir.glob("*.md"))
    assert len(md_files) >= 4, \
        f"v2.72.0 split target: ≥4 sub-files in _shared/migrate/ (got {len(md_files)})"


def test_migrate_md_routes_to_each_subfile():
    body = Path("commands/vg/migrate.md").read_text(encoding="utf-8")
    expected_subfiles = [
        "preflight.md", "enrich.md", "goals-plans.md", "pipeline-and-validate.md",
    ]
    missing = [s for s in expected_subfiles if f"_shared/migrate/{s}" not in body]
    assert not missing, f"migrate.md missing routes: {missing}"
