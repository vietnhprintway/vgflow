"""tests/test_batch61_blueprint_script_fallback.py — Batch 61.

Blueprint command files (close.md, design.md, contracts-overview.md,
verify.md) had 10 hardcoded `.claude/scripts/` paths WITHOUT the
3-tier VG_HOME fallback. Slim-entry projects (no local
`.claude/scripts/`) failed at Phase 8 blueprint with "script missing"
errors.

Fix: all hardcoded blueprint script paths must follow the pattern:
  VAR="${REPO_ROOT:-.}/.claude/scripts/.../script.py"
  [ -f "$VAR" ] || VAR="${REPO_ROOT:-.}/scripts/.../script.py"
  [ -f "$VAR" ] || VAR="${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/.../script.py"

Coverage:
  1. close.md: TRACE_VAL, ORCH_BIN, DTASK_VAL, DGOAL_VAL,
     BLOCK5_VALIDATOR each have 3-tier fallback
  2. contracts-overview.md: CRUD_VALIDATOR
  3. design.md: TR_SCRIPT, UIMAP_PRE_VAL, ORCH_BIN, UIMAP_VAL, EMITTER
  4. verify.md: PATH_CHECKER, UTILITY_CHECKER, GROUNDING_VAL
  5. No bare `.claude/scripts/` without fallback remain in blueprint
  6. Mirror parity (.claude/ matches commands/)
"""
from __future__ import annotations
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = REPO / "commands" / "vg" / "_shared" / "blueprint"
BLUEPRINT_MIRROR = REPO / ".claude" / "commands" / "vg" / "_shared" / "blueprint"


VAR_DECL_RE = re.compile(r'^(\s*)(\w+)="\$\{REPO_ROOT[^}]*\}/\.claude/scripts/([^"]+)"', re.M)
FALLBACK_2_RE_TPL = r'\[ -f "\${var}" \] \|\| {var}="\$\{REPO_ROOT[^}]*\}/scripts/'
FALLBACK_3_RE_TPL = r'\[ -f "\${var}" \] \|\| {var}="\$\{VG_SCRIPT_ROOT:-\$\{VG_HOME[^}]*\}/scripts\}'


def _check_var_has_3tier(body: str, var_name: str) -> bool:
    """Find lines `VAR=...claude/scripts/...` and confirm next 2 lines
    are scripts/ fallback and VG_HOME fallback. Accept `-f` or `-x`."""
    pattern = re.compile(
        rf'{var_name}="\$\{{REPO_ROOT[^}}]*\}}/\.claude/scripts/[^"]+"\s*\n'
        rf'\s*\[ -[fx] "\${var_name}" \] \|\| {var_name}="\$\{{REPO_ROOT[^}}]*\}}/scripts/[^"]+"\s*\n'
        rf'\s*\[ -[fx] "\${var_name}" \] \|\| {var_name}="\$\{{VG_SCRIPT_ROOT:-\$\{{VG_HOME[^}}]*\}}/scripts\}}',
        re.M,
    )
    return bool(pattern.search(body))


def test_close_md_trace_val_3tier():
    body = (BLUEPRINT_DIR / "close.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "TRACE_VAL"), "TRACE_VAL must have 3-tier fallback"


def test_close_md_dtask_val_3tier():
    body = (BLUEPRINT_DIR / "close.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "DTASK_VAL"), "DTASK_VAL must have 3-tier fallback"


def test_close_md_dgoal_val_3tier():
    body = (BLUEPRINT_DIR / "close.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "DGOAL_VAL"), "DGOAL_VAL must have 3-tier fallback"


def test_close_md_block5_validator_3tier():
    body = (BLUEPRINT_DIR / "close.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "BLOCK5_VALIDATOR")


def test_close_md_orch_bin_3tier():
    body = (BLUEPRINT_DIR / "close.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "ORCH_BIN")


def test_contracts_overview_crud_validator_3tier():
    body = (BLUEPRINT_DIR / "contracts-overview.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "CRUD_VALIDATOR")


def test_design_md_tr_script_3tier():
    body = (BLUEPRINT_DIR / "design.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "TR_SCRIPT")


def test_design_md_uimap_pre_val_3tier():
    body = (BLUEPRINT_DIR / "design.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "UIMAP_PRE_VAL")


def test_design_md_uimap_val_3tier():
    body = (BLUEPRINT_DIR / "design.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "UIMAP_VAL")


def test_design_md_orch_bin_3tier():
    body = (BLUEPRINT_DIR / "design.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "ORCH_BIN")


def test_design_md_emitter_3tier():
    """EMITTER uses path-style fallback (different keyword but still 3-tier)."""
    body = (BLUEPRINT_DIR / "design.md").read_text(encoding="utf-8")
    # EMITTER has REPO_ROOT/.claude → REPO_ROOT/scripts → VG_HOME
    pattern = re.compile(
        r'EMITTER="\$\{REPO_ROOT\}/\.claude/scripts/blueprint/[^"]+"\s*\n'
        r'\[ -f "\$EMITTER" \] \|\| EMITTER="\$\{REPO_ROOT\}/scripts/blueprint/[^"]+"\s*\n'
        r'.*\n?'
        r'\[ -f "\$EMITTER" \] \|\| EMITTER="\$\{VG_SCRIPT_ROOT:-\$\{VG_HOME[^}]*\}/scripts\}',
        re.M,
    )
    assert pattern.search(body), "EMITTER must have 3-tier fallback"


def test_verify_md_path_checker_3tier():
    body = (BLUEPRINT_DIR / "verify.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "PATH_CHECKER")


def test_verify_md_utility_checker_3tier():
    body = (BLUEPRINT_DIR / "verify.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "UTILITY_CHECKER")


def test_verify_md_grounding_val_3tier():
    body = (BLUEPRINT_DIR / "verify.md").read_text(encoding="utf-8")
    assert _check_var_has_3tier(body, "GROUNDING_VAL")


def test_no_bare_claude_scripts_in_blueprint():
    """No assignment like `VAR=".claude/scripts/..."` (no $REPO_ROOT prefix
    AND no follow-up fallback) should remain."""
    pattern = re.compile(r'^\s*\w+="\.claude/scripts/', re.M)
    for md in BLUEPRINT_DIR.glob("*.md"):
        body = md.read_text(encoding="utf-8")
        matches = pattern.findall(body)
        assert not matches, f"{md.name}: bare .claude/scripts/ assignment without REPO_ROOT prefix: {matches}"


def test_blueprint_mirrors_in_sync():
    for fname in ("close.md", "contracts-overview.md", "design.md", "verify.md"):
        src = (BLUEPRINT_DIR / fname).read_text(encoding="utf-8")
        mirror = (BLUEPRINT_MIRROR / fname).read_text(encoding="utf-8")
        assert src == mirror, f"{fname} mirror drift"
