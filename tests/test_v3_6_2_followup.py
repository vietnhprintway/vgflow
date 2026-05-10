"""v3.6.2 — generator preserve hardening + /vg:update chmod.

Coverage:
1. generate-codex-skills.sh declares target_has_curated_codex_content
2. write_codex_skill SKIPS targets with curated content unless --force-overwrite-curated
3. --force-overwrite-curated CLI flag accepted
4. /vg:update rotate-and-repair.md chmod +x hooks before install-hooks.sh
5. canonical/mirror byte-identity for rotate-and-repair.md
6. Smoke: running generator with --force on a target with HARD-GATE-CODEX
   does NOT modify the target.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "generate-codex-skills.sh"
ROTATE_CANON = REPO_ROOT / "commands" / "vg" / "_shared" / "update" / "rotate-and-repair.md"
ROTATE_MIRROR = REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "update" / "rotate-and-repair.md"

_BASH_SKIP = pytest.mark.skipif(
    not shutil.which("bash") or sys.platform == "win32",
    reason="bash + POSIX semantics required for generator smoke",
)


# ── content checks ────────────────────────────────────────────────────────


def test_generator_declares_curated_detector():
    body = GENERATOR.read_text(encoding="utf-8")
    assert "target_has_curated_codex_content" in body
    assert "HARD-GATE-CODEX" in body, (
        "detector must look for HARD-GATE-CODEX marker"
    )
    assert "vg-orchestrator mark-step" in body, (
        "detector must look for ≥8 mark-step lines heuristic"
    )


def test_generator_skips_curated_by_default():
    body = GENERATOR.read_text(encoding="utf-8")
    # write_codex_skill should refuse to overwrite curated targets unless override flag
    assert "FORCE_OVERWRITE_CURATED" in body
    # And the skip path SHOULD print "Skipped (curated content detected)"
    assert "Skipped (curated content detected)" in body


def test_generator_cli_accepts_force_overwrite_curated():
    body = GENERATOR.read_text(encoding="utf-8")
    assert "--force-overwrite-curated)" in body
    assert "FORCE_OVERWRITE_CURATED=true" in body


def test_rotate_and_repair_chmods_hooks():
    body = ROTATE_CANON.read_text(encoding="utf-8")
    # chmod block must precede install-hooks invocation
    chmod_pos = body.find('chmod +x "${REPO_ROOT}/.claude/scripts/hooks/"*.sh')
    install_pos = body.find('HOOK_INSTALL=')
    assert chmod_pos > 0, "rotate-and-repair must chmod .claude/scripts/hooks/*.sh"
    assert install_pos > chmod_pos, (
        "chmod must happen BEFORE install-hooks.sh writes settings.json"
    )
    # And cover the other directories that house hook-callable scripts
    for sub in (
        '.claude/scripts/hooks/"*.py',
        '.claude/scripts/"*.sh',
        '.claude/scripts/"*.py',
        '.claude/scripts/validators/"*.py',
        '.claude/scripts/vg-orchestrator/"*.py',
        '.claude/scripts/lib/"*.py',
        '.claude/scripts/blueprint/"*.py',
        '.claude/commands/vg/_shared/lib/"*.sh',
    ):
        assert sub in body, f"rotate-and-repair must chmod {sub}"


def test_rotate_and_repair_mirror_byte_identity():
    assert ROTATE_CANON.read_bytes() == ROTATE_MIRROR.read_bytes()


# ── functional smoke ──────────────────────────────────────────────────────


@_BASH_SKIP
def test_generator_force_does_not_clobber_curated(tmp_path):
    """Create a fake curated SKILL.md and verify --force leaves it untouched."""
    # Stage a minimal source tree: commands/vg/X.md + a curated target.
    fake_repo = tmp_path / "repo"
    (fake_repo / "commands" / "vg").mkdir(parents=True)
    (fake_repo / "skills").mkdir(parents=True)
    (fake_repo / "codex-skills").mkdir(parents=True)
    (fake_repo / "codex-skills" / "vg-curatedtest").mkdir()

    # Source command
    (fake_repo / "commands" / "vg" / "curatedtest.md").write_text(
        "---\nname: vg:curatedtest\ndescription: Curated test source\n---\n\nBody.\n",
        encoding="utf-8",
    )
    # Curated target with HARD-GATE-CODEX marker
    target = fake_repo / "codex-skills" / "vg-curatedtest" / "SKILL.md"
    curated_body = (
        '---\nname: "vg-curatedtest"\ndescription: "curated"\n'
        'metadata:\n  short-description: "curated"\n---\n\n'
        "Curated content here.\n\n"
        "<HARD-GATE-CODEX>\nOperator MUST emit mark-step manually.\n</HARD-GATE-CODEX>\n"
    )
    target.write_text(curated_body, encoding="utf-8")

    # Copy generator into fake repo so its REPO_ROOT resolution finds the
    # right tree (script uses cd $(dirname $0)/.. as REPO_ROOT)
    (fake_repo / "scripts").mkdir()
    shutil.copy(GENERATOR, fake_repo / "scripts" / "generate-codex-skills.sh")
    os.chmod(fake_repo / "scripts" / "generate-codex-skills.sh", 0o755)

    r = subprocess.run(
        ["bash", str(fake_repo / "scripts" / "generate-codex-skills.sh"), "--force"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, f"generator exited {r.returncode}\n{r.stdout}\n{r.stderr}"
    # Target must be unchanged
    after = target.read_text(encoding="utf-8")
    assert after == curated_body, (
        "curated SKILL.md must NOT be modified by --force regen.\n"
        f"stdout={r.stdout}\n"
    )
    # And stdout should mention the skip
    assert "Skipped (curated content detected)" in r.stdout or "vg-curatedtest" in r.stdout
