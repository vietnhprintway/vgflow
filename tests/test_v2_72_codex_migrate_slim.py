"""v2.72.0 T8 — codex-skills/vg-migrate/SKILL.md slim."""
from pathlib import Path
import re


def test_codex_migrate_under_slim_ceiling():
    body = Path("codex-skills/vg-migrate/SKILL.md").read_text(encoding="utf-8")
    line_count = len(body.splitlines())
    # Original 1440 → split target ≤ 600 (~58% reduction)
    assert line_count <= 600, \
        f"v2.72.0 codex-migrate slim target: ≤600 lines (got {line_count})"


def test_codex_migrate_routes_to_all_4_subfiles():
    body = Path("codex-skills/vg-migrate/SKILL.md").read_text(encoding="utf-8")
    expected = [
        "preflight.md",
        "enrich.md",
        "goals-plans.md",
        "pipeline-and-validate.md",
    ]
    missing = [s for s in expected if f"_shared/migrate/{s}" not in body]
    assert not missing, f"codex-migrate missing routes: {missing}"


def test_codex_migrate_preserves_hardgate_codex():
    body = Path("codex-skills/vg-migrate/SKILL.md").read_text(encoding="utf-8")
    # vg-migrate does not currently carry the HARD-GATE-CODEX block, but the
    # codex_skill_adapter envelope (frontmatter + Codex runtime contract) MUST
    # remain intact.
    assert "HARD-GATE-CODEX" in body or "codex_skill_adapter" in body, \
        "codex_skill_adapter (or HARD-GATE-CODEX) block must be preserved"


def test_codex_migrate_step_bodies_extracted():
    """Verify ≤ 5 inline <step name=...> bodies remain (slim entries are routing only)."""
    body = Path("codex-skills/vg-migrate/SKILL.md").read_text(encoding="utf-8")
    full_step_blocks = re.findall(r'<step name="[^"]+">.*?</step>', body, re.DOTALL)
    long_bodies = [b for b in full_step_blocks if len(b) > 500]
    assert len(long_bodies) <= 5, \
        f"Too many long step bodies remain ({len(long_bodies)}); expected ≤5 after slim"
