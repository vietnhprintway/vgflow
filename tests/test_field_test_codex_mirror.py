"""tests/test_field_test_codex_mirror.py — Codex mirror generation invariants."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "commands" / "vg" / "field-test.md"
CODEX_MIRROR = REPO_ROOT / "codex-skills" / "vg-field-test" / "SKILL.md"
PROJECT_CODEX = REPO_ROOT / ".codex" / "skills" / "vg-field-test"


def _parse_frontmatter(body: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", body, re.DOTALL)
    if not m:
        raise AssertionError("no frontmatter")
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def test_codex_mirror_exists():
    assert CODEX_MIRROR.exists(), (
        "generator must produce codex-skills/vg-field-test/SKILL.md — "
        "run: bash scripts/generate-codex-skills.sh"
    )


def test_codex_mirror_yaml_valid():
    body = CODEX_MIRROR.read_text(encoding="utf-8")
    fm = _parse_frontmatter(body)
    assert "name" in fm
    assert fm["name"] == '"vg-field-test"', (
        f"Codex mirror name must be 'vg-field-test', got {fm['name']!r}"
    )
    assert "description" in fm
    assert fm["description"], "description must be non-empty"


def test_codex_mirror_not_present_in_project_codex_dir():
    """v2.1 + PR #177: project-local .codex/skills no longer committed."""
    assert not PROJECT_CODEX.exists(), (
        "After PR #177, vg-field-test must NOT be committed under project-local "
        ".codex/skills — global-only install via codex-skills/* -> ~/.codex/skills/*."
    )


def test_codex_mirror_byte_identical_to_canonical_invariants():
    """Generator must preserve key invariants (allowed-tools, telemetry events,
    SPA reload logic references) between commands/vg/field-test.md and the
    generated codex mirror."""
    canon = CANONICAL.read_text(encoding="utf-8")
    mirror = CODEX_MIRROR.read_text(encoding="utf-8")
    for inv in (
        "mcp__playwright1__browser_evaluate",
        "must_emit_telemetry",
        "field_test.session_started",
        "field_test.mark_recorded",
        "field_test.session_stopped",
        "field_test.analysis_completed",
        "__VG_FT_STATE",
    ):
        assert inv in canon, f"canonical missing invariant {inv}"
        assert inv in mirror, f"codex mirror missing invariant {inv}"


def test_codex_mirror_preserves_hard_gate_warning():
    """The screenshot-not-redacted warning must survive generator transform."""
    body = CODEX_MIRROR.read_text(encoding="utf-8")
    body_lower = body.lower()
    assert "screenshot" in body_lower
    assert "not redacted" in body_lower or "redacted" in body_lower
