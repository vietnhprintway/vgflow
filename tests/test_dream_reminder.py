"""Stop hook soft reminder for meta-memory consolidation gate (Hướng C v2.59.0)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "vg-dream-reminder.py"


def _stub_consolidate(tmp_path: Path, exit_code: int) -> Path:
    """Write a fake bootstrap-consolidate.py that exits with given code."""
    stub = tmp_path / "bootstrap-consolidate.py"
    stub.write_text(
        f"#!/usr/bin/env python3\nimport sys\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _run(tmp_path: Path, mode: str | None, gate_exit: int, *,
         state_exists: bool = False, reset: bool = False) -> subprocess.CompletedProcess:
    cfg = tmp_path / "vg.config.md"
    if mode is not None:
        cfg.write_text(f"meta_memory_mode: {mode}\n", encoding="utf-8")
    state = tmp_path / "dream-state"
    if state_exists:
        state.touch()
    stub = _stub_consolidate(tmp_path, gate_exit)
    env = {
        **os.environ,
        "VG_REPO_ROOT": str(tmp_path),
        "VG_CONFIG_PATH": str(cfg),
        "VG_DREAM_STATE_PATH": str(state),
        "VG_CONSOLIDATE_HELPER": str(stub),
    }
    args = [sys.executable, str(HELPER)]
    if reset:
        args.append("--reset")
    return subprocess.run(args, capture_output=True, text=True, env=env)


def test_disabled_silent(tmp_path):
    r = _run(tmp_path, "disabled", 0)
    assert r.returncode == 0
    assert "Meta-memory" not in (r.stdout + r.stderr)


def test_no_config_silent(tmp_path):
    r = _run(tmp_path, None, 0)
    assert r.returncode == 0
    assert "Meta-memory" not in (r.stdout + r.stderr)


def test_gate_not_met_silent(tmp_path):
    r = _run(tmp_path, "inject-as-advice", 1)
    assert r.returncode == 0
    assert "Meta-memory" not in (r.stdout + r.stderr)


def test_gate_met_emits_reminder(tmp_path):
    r = _run(tmp_path, "inject-as-advice", 0)
    assert r.returncode == 0
    output = r.stdout + r.stderr
    assert "Meta-memory" in output
    assert "/vg:learn --consolidate --apply" in output


def test_already_shown_silent(tmp_path):
    r = _run(tmp_path, "inject-as-advice", 0, state_exists=True)
    assert r.returncode == 0
    assert "Meta-memory" not in (r.stdout + r.stderr)


def test_state_file_created_on_emit(tmp_path):
    r = _run(tmp_path, "inject-as-advice", 0)
    assert r.returncode == 0
    state = tmp_path / "dream-state"
    assert state.exists(), "state file should be touched after emit"


def test_reset_clears_state(tmp_path):
    r = _run(tmp_path, "inject-as-advice", 0)
    assert r.returncode == 0
    state = tmp_path / "dream-state"
    assert state.exists()
    r2 = _run(tmp_path, "inject-as-advice", 0, state_exists=True, reset=True)
    assert r2.returncode == 0
    assert not state.exists()


def test_helper_mirror_byte_identical():
    canonical = REPO_ROOT / "scripts" / "vg-dream-reminder.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "vg-dream-reminder.py"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()


def test_stop_hook_mirror_byte_identical():
    canonical = REPO_ROOT / "scripts" / "hooks" / "vg-stop.sh"
    mirror = REPO_ROOT / ".claude" / "scripts" / "hooks" / "vg-stop.sh"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()


def test_stop_hook_invokes_dream_reminder():
    body = (REPO_ROOT / "scripts" / "hooks" / "vg-stop.sh").read_text(encoding="utf-8")
    assert "vg-dream-reminder.py" in body, (
        "vg-stop.sh must invoke vg-dream-reminder.py at end-of-stop"
    )
