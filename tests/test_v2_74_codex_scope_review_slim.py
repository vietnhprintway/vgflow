"""v2.74.0 T5 — codex-skills/vg-scope-review/SKILL.md slim verification."""
from pathlib import Path
import re


def test_codex_scope_review_under_slim_ceiling():
    body = Path("codex-skills/vg-scope-review/SKILL.md").read_text(encoding="utf-8")
    assert len(body.splitlines()) <= 400


def test_codex_scope_review_routes_to_subfiles():
    body = Path("codex-skills/vg-scope-review/SKILL.md").read_text(encoding="utf-8")
    expected = ["preflight.md", "cross-ref-review-write.md", "resolve-and-close.md"]
    missing = [s for s in expected if f"_shared/scope-review/{s}" not in body]
    assert not missing


def test_codex_scope_review_preserves_adapter():
    body = Path("codex-skills/vg-scope-review/SKILL.md").read_text(encoding="utf-8")
    assert "codex_skill_adapter" in body or "HARD-GATE-CODEX" in body


def test_codex_scope_review_step_bodies_extracted():
    body = Path("codex-skills/vg-scope-review/SKILL.md").read_text(encoding="utf-8")
    full_step_blocks = re.findall(r'<step name="[^"]+">.*?</step>', body, re.DOTALL)
    long_bodies = [b for b in full_step_blocks if len(b) > 500]
    assert len(long_bodies) <= 5
