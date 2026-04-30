"""Test base_url resolution multi-location + fail-fast guard."""
import importlib.util
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "spawn_crud", REPO_ROOT / "scripts" / "spawn-crud-roundtrip.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_base_url_resolves_from_phase_dir_claude_config(tmp_path, monkeypatch):
    """Phase-local .claude/vg.config.md takes precedence over repo root."""
    phase = tmp_path / "phase"
    (phase / ".claude").mkdir(parents=True)
    (phase / ".claude" / "vg.config.md").write_text(
        "review:\n  auth:\n    base_url: http://phase-local:5555\n"
    )
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "fake-repo")
    base_url = mod.resolve_base_url(phase)
    assert base_url == "http://phase-local:5555"


def test_base_url_resolves_from_phase_dir_root_config(tmp_path, monkeypatch):
    """Phase-local vg.config.md (no .claude prefix) is fallback before repo root."""
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "vg.config.md").write_text("base_url: http://phase-root:6666\n")
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "fake-repo")
    base_url = mod.resolve_base_url(phase)
    assert base_url == "http://phase-root:6666"


def test_base_url_resolves_from_repo_root_claude(tmp_path, monkeypatch):
    """Repo root .claude/vg.config.md is fallback after phase-local."""
    phase = tmp_path / "phase"
    phase.mkdir()
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / ".claude").mkdir(parents=True)
    (fake_repo / ".claude" / "vg.config.md").write_text(
        "base_url: http://repo-root:7777\n"
    )
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    base_url = mod.resolve_base_url(phase)
    assert base_url == "http://repo-root:7777"


def test_base_url_resolves_from_repo_root_no_claude(tmp_path, monkeypatch):
    """Priority 4: REPO_ROOT/vg.config.md (no .claude/ subdir) — last fallback."""
    phase = tmp_path / "phase"
    phase.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    (fake_repo / "vg.config.md").write_text("base_url: http://repo-flat:8888\n")
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    assert mod.resolve_base_url(phase) == "http://repo-flat:8888"


def test_base_url_priority_phase_dir_wins_over_repo_root(tmp_path, monkeypatch):
    """When both phase-local AND repo root have base_url, phase-local wins."""
    phase = tmp_path / "phase"
    (phase / ".claude").mkdir(parents=True)
    (phase / ".claude" / "vg.config.md").write_text(
        "base_url: http://phase-wins:1111\n"
    )
    fake_repo = tmp_path / "fake-repo"
    (fake_repo / ".claude").mkdir(parents=True)
    (fake_repo / ".claude" / "vg.config.md").write_text(
        "base_url: http://repo-loses:2222\n"
    )
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", fake_repo)
    assert mod.resolve_base_url(phase) == "http://phase-wins:1111"


def test_base_url_returns_none_when_no_config_found(tmp_path, monkeypatch):
    phase = tmp_path / "phase"
    phase.mkdir()
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "fake-repo-empty")
    base_url = mod.resolve_base_url(phase)
    assert base_url is None


def test_fail_fast_when_base_url_none_and_crud_kit_present(tmp_path):
    """Spawning workers without base_url for crud-roundtrip kit must fail with exit 1."""
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "CRUD-SURFACES.md").write_text(
        '```json\n{"resources": [{"name": "notes", "kit": "crud-roundtrip", '
        '"scope": "user", "base": {"roles": ["admin"]}, '
        '"expected_behavior": {}, "forbidden_side_effects": []}]}\n```\n'
    )
    (phase / ".review-fixtures").mkdir()
    (phase / ".review-fixtures" / "tokens.local.yaml").write_text(
        "admin:\n  token: t1\n  user_id: u1\n"
    )
    (phase / "runs").mkdir()
    # NOTE: no vg.config.md anywhere reachable. Use real REPO_ROOT as VG_REPO_ROOT
    # so the kit prompt resolves (it lives at REPO_ROOT/commands/...) but base_url
    # cannot resolve because neither REPO_ROOT/.claude/vg.config.md nor
    # REPO_ROOT/vg.config.md exist (only vg.config.template.md exists).
    import os as _os
    env = dict(_os.environ)
    env["VG_REPO_ROOT"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "scripts/spawn-crud-roundtrip.py",
         "--phase-dir", str(phase), "--dry-run"],
        capture_output=True, text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1, (
        f"Expected fail-fast exit 1, got {result.returncode}\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "base_url" in (result.stderr + result.stdout).lower()
