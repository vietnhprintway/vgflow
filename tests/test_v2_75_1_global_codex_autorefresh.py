"""v2.75.1 hotfix — auto-refresh global ~/.codex on /vg:update.

Bug: /vg:update only refreshed project-local .codex/. If user previously ran
`install.sh --global-codex`, ~/.codex/skills/ stayed stale. Codex CLI loads
BOTH locations → each flow registered twice = duplicate-flow bug.

Fix: step 8_sync_codex auto-detects ~/.codex/skills/vg-update and refreshes
global without requiring VG_UPDATE_GLOBAL_CODEX=1 manual flag.
"""
from pathlib import Path


SYNC_FILE = Path("commands/vg/_shared/update/sync-and-report.md")
SYNC_MIRROR = Path(".claude/commands/vg/_shared/update/sync-and-report.md")


def test_sync_file_has_autodetect_block():
    body = SYNC_FILE.read_text(encoding="utf-8")
    assert "GLOBAL_CODEX_HAS_VGFLOW" in body, \
        "8_sync_codex must declare GLOBAL_CODEX_HAS_VGFLOW for auto-detect"
    assert '[ -d "$HOME/.codex/skills/vg-update" ]' in body, \
        "auto-detect must probe ~/.codex/skills/vg-update existence"


def test_sync_file_has_tristate_decision():
    body = SYNC_FILE.read_text(encoding="utf-8")
    expected_states = [
        "refresh-explicit",
        "refresh-auto",
        "skip-explicit",
        "skip-auto",
    ]
    for state in expected_states:
        assert state in body, f"tri-state decision missing: {state}"


def test_sync_file_handles_auto_default():
    body = SYNC_FILE.read_text(encoding="utf-8")
    assert '${VG_UPDATE_GLOBAL_CODEX:-auto}' in body, \
        "VG_UPDATE_GLOBAL_CODEX default must be 'auto' (not '0')"


def test_sync_file_warns_on_explicit_optout_with_stale_global():
    body = SYNC_FILE.read_text(encoding="utf-8")
    assert "Stale vgflow detected at ~/.codex/skills" in body, \
        "skip-explicit branch must warn when stale global vgflow present"
    assert "rm -rf ~/.codex/skills/vg-*" in body, \
        "warning must include manual cleanup command"


def test_sync_file_message_for_auto_refresh():
    body = SYNC_FILE.read_text(encoding="utf-8")
    assert "auto-detected prior global vgflow install" in body, \
        "refresh-auto branch must announce auto-detection"
    assert "prevents duplicate-flow bug" in body, \
        "refresh-auto message must explain rationale"


def test_sync_file_mirror_byte_identity():
    src = SYNC_FILE.read_bytes()
    dst = SYNC_MIRROR.read_bytes()
    assert src == dst, \
        f"commands/.../sync-and-report.md and .claude mirror differ ({len(src)} vs {len(dst)} bytes)"


def test_codex_skill_routes_to_sync_subfile():
    """codex-skills/vg-update/SKILL.md slim routes to _shared/update/sync-and-report.md."""
    body = Path("codex-skills/vg-update/SKILL.md").read_text(encoding="utf-8")
    assert "_shared/update/sync-and-report.md" in body, \
        "codex vg-update slim must route to _shared/update/sync-and-report.md (no separate codex copy)"


def test_legacy_optin_still_supported():
    """VG_UPDATE_GLOBAL_CODEX=1 still forces global refresh."""
    body = SYNC_FILE.read_text(encoding="utf-8")
    assert "VG_UPDATE_GLOBAL_CODEX=1 — refreshed" in body, \
        "explicit opt-in (VG_UPDATE_GLOBAL_CODEX=1) message must remain"
