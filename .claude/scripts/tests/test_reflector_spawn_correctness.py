"""Reflector spawn syntax — never use subagent_type=vg-reflector.

PV3 blueprint 4.3 dogfood (2026-05-05) error:
  Agent type 'vg-reflector' not found. Available agents: ...

`vg-reflector` is defined as a Skill in `.claude/skills/vg-reflector/SKILL.md`,
NOT a registered subagent type. Spawning via Agent must use
`subagent_type="general-purpose"` with the skill instruction inlined in
the prompt body. This test enforces all close.md / crossai.md spawn
sites follow that pattern.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REFLECTOR_SPAWN_SITES = [
    "commands/vg/_shared/blueprint/close.md",
    "commands/vg/_shared/test/close.md",
    "commands/vg/_shared/review/close.md",
    "commands/vg/_shared/scope/crossai.md",
    "commands/vg/_shared/reflection-trigger.md",
]

# Pattern that explicitly passes vg-reflector as subagent_type — forbidden.
FORBIDDEN_PATTERN = re.compile(
    r'subagent_type\s*[=:]\s*[\'"]vg-reflector[\'"]'
)
# Anti-warning markers — context where the forbidden pattern is being
# DOCUMENTED as wrong (not actually executed).
WARNING_MARKERS = (
    "previous version used",
    "but no `agents/",
    "WILL ERROR",
    "will error",
    "NOT a registered",
    "NOT a Claude subagent",
    "instead of vg-reflector",
)


def test_no_site_spawns_vg_reflector_as_subagent_type():
    """Forbidden pattern: subagent_type="vg-reflector" in actual spawn code.
    Warning comments that mention the pattern as wrong are allowed."""
    failures = []
    for rel in REFLECTOR_SPAWN_SITES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text()
        # Check each occurrence — if surrounded by warning context, allow.
        for m in FORBIDDEN_PATTERN.finditer(text):
            window = text[max(0, m.start() - 200):m.end() + 200]
            if any(marker in window for marker in WARNING_MARKERS):
                continue  # documented warning, not actual call
            failures.append(f"{rel}:{text[:m.start()].count(chr(10))+1}")
    assert not failures, (
        f"These files spawn `vg-reflector` as subagent_type in actual code "
        f"(will error with 'Agent type not found'): {failures}\n"
        f"Use `subagent_type=\"general-purpose\"` + 'Use skill: vg-reflector' "
        f"in prompt body instead."
    )


def test_blueprint_close_has_concrete_spawn_block():
    """blueprint/close.md must have an Agent() spawn block (not just comment).

    Pre-fix it had only a `# Skill(skill=...)` comment which AI interpreted
    inconsistently — some attempts used wrong subagent_type leading to
    'Agent type not found' errors at PV3 blueprint 4.3.
    """
    path = REPO_ROOT / "commands/vg/_shared/blueprint/close.md"
    text = path.read_text()
    # Must have an Agent( block referencing general-purpose subagent
    assert re.search(
        r'Agent\(.*?subagent_type=["\']general-purpose["\']',
        text, re.DOTALL,
    ), "blueprint/close.md must have explicit Agent(subagent_type='general-purpose') block"
    # Must inline the skill instruction
    assert "Use skill: vg-reflector" in text, (
        "blueprint/close.md must inline 'Use skill: vg-reflector' in prompt body"
    )


def test_close_files_warn_about_subagent_type_pitfall():
    """At least one site should explicitly call out the subagent_type pitfall
    so future authors don't reintroduce the bug."""
    found_warning = False
    for rel in REFLECTOR_SPAWN_SITES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text()
        # Various phrasings of the warning
        if any(p in text for p in [
            "NOT a registered subagent type",
            "NOT a Claude subagent type",
            "Agent type not found",
            "subagent_type=\"vg-reflector\" but",
        ]):
            found_warning = True
            break
    assert found_warning, (
        "At least one reflector-spawn site must document the subagent_type "
        "pitfall. Without this comment, future authors will repeat the bug."
    )


def test_mirror_parity_blueprint_close():
    src = REPO_ROOT / "commands/vg/_shared/blueprint/close.md"
    mirror = REPO_ROOT / ".claude/commands/vg/_shared/blueprint/close.md"
    assert mirror.is_file()
    assert src.read_bytes() == mirror.read_bytes(), "blueprint/close.md mirror drift"
