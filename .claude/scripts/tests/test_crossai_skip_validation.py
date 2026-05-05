"""Anti-rationalization validator for skip-*-crossai* overrides.

PV3 build 4.2 dogfood (2026-05-05) revealed AI emitting:
  vg-orchestrator override --flag=skip-build-crossai \\
    --reason="...no Codex CLI configured per .claude/vg.config.md..."

while:
  - vg.config.md `crossai_clis:` lists Codex
  - `which codex` returns /usr/.../bin/codex
  - crossai-build-verify/codex-iter1.md was actually written with PASS verdict

Override-debt logged with FALSE claim. The fact-checker rejects this
class of bypass.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from crossai_skip_validation import (  # noqa: E402
    validate_skip_legitimate,
    format_rejection,
    _parse_crossai_clis,
)


def test_parse_crossai_clis_extracts_names():
    """Markdown YAML-ish block parsed correctly."""
    cfg = """# vg.config.md

crossai_clis:
  - name: "Codex"
    command: 'cat {context} | codex exec'
  - name: "Gemini"
    command: 'cat {context} | gemini'
  - name: "Claude"

other_section:
  enabled: true
"""
    names = _parse_crossai_clis(cfg)
    assert names == ["codex", "gemini", "claude"]


def test_legitimate_skip_when_no_cli_installed(tmp_path):
    """Config has CLIs but none installed → skip legitimate."""
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude/vg.config.md").write_text(
        'crossai_clis:\n  - name: "NonExistentCli12345"\n'
    )
    result = validate_skip_legitimate(
        tmp_path,
        "skip-build-crossai because no NonExistentCli12345 CLI installed "
        "https://github.com/foo/bar/issues/42 commit abc1234",
    )
    assert result.legitimate is True
    assert result.installed_clis == []


def test_rationalization_rejected_when_cli_actually_installed(tmp_path):
    """Config has python3 (always installed) — skip MUST be rejected."""
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude/vg.config.md").write_text(
        'crossai_clis:\n  - name: "python3"\n    command: foo\n'
    )
    result = validate_skip_legitimate(
        tmp_path,
        "skip-build-crossai because no python3 CLI configured per vg.config.md "
        "ref https://github.com/foo/bar/pull/1 commit deadbeef",
    )
    assert result.legitimate is False
    assert "python3" in result.installed_clis
    assert len(result.false_claims) >= 1
    # Rejection message should expose the false claim
    msg = format_rejection(result)
    assert "python3" in msg
    assert "REJECTED" in msg


def test_false_claim_detected_in_reason_text(tmp_path):
    """Reason text claims 'no X CLI configured' but X IS configured."""
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude/vg.config.md").write_text(
        'crossai_clis:\n  - name: "Codex"\n  - name: "Gemini"\n'
    )
    # Use a fake CLI name not on PATH to isolate false-claim detection
    result = validate_skip_legitimate(
        tmp_path,
        "Skipping because no Codex CLI configured locally — "
        "ref commit abc1234 https://github.com/x/y/pull/1",
    )
    # Codex IS in vg.config.md → claim "no Codex CLI configured" is false
    has_codex_false_claim = any(
        "Codex" in fc or "codex" in fc.lower() for fc in result.false_claims
    )
    assert has_codex_false_claim, (
        f"Expected false-claim detection for 'no Codex CLI configured'. "
        f"Got: {result.false_claims}"
    )


def test_no_config_file_passes_with_warn(tmp_path):
    """Project without vg.config.md → cannot prove rationalization → allow."""
    result = validate_skip_legitimate(tmp_path, "any reason")
    assert result.legitimate is True
    assert "No vg.config.md found" in result.reasoning


def test_format_rejection_includes_actionable_fix(tmp_path):
    """Rejection message guides operator to actual fix."""
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude/vg.config.md").write_text(
        'crossai_clis:\n  - name: "python3"\n'
    )
    result = validate_skip_legitimate(tmp_path, "no python3 cli installed abc1234")
    msg = format_rejection(result)
    assert "vg-build-crossai-loop.py" in msg
    assert "--iteration 1" in msg
