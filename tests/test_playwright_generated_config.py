"""tests/test_playwright_generated_config.py — Batch 5 generated config template."""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "templates" / "vg" / "playwright.config.generated.template.ts"
MIRROR = REPO_ROOT / ".claude" / "templates" / "vg" / "playwright.config.generated.template.ts"


def test_template_exists():
    assert TEMPLATE.is_file(), "Batch 5: playwright config template must ship in templates/"


def test_template_defaults_headed_when_no_ci():
    body = TEMPLATE.read_text(encoding="utf-8")
    # The headless toggle MUST be env-driven, not hardcoded true/false.
    # Accept either: direct "headless: !!process.env.CI" OR
    # variable pattern "const isCi = !!process.env.CI" + headless derived from it.
    direct_pattern = "headless: !!process.env.CI" in body or "headless: process.env.CI" in body
    variable_pattern = (
        "process.env.CI" in body
        and ("headless:" in body)
        and ("headless: true" not in body)
        and ("headless: false" not in body)
    )
    assert direct_pattern or variable_pattern, (
        "Batch 5: config must derive headless from CI env, not hardcode true/false"
    )


def test_template_has_trace_and_video_on_failure():
    body = TEMPLATE.read_text(encoding="utf-8")
    assert "trace:" in body and "retain-on-failure" in body
    assert "video:" in body
    assert "screenshot:" in body


def test_template_reporter_split():
    body = TEMPLATE.read_text(encoding="utf-8")
    # Interactive mode: list reporter (per-spec progress). CI: dot.
    assert "'list'" in body or '"list"' in body
    assert "'dot'" in body or '"dot"' in body


def test_mirror_byte_identical():
    if not MIRROR.is_file():
        return  # mirror only after installer copies
    assert TEMPLATE.read_text(encoding="utf-8") == MIRROR.read_text(encoding="utf-8")
