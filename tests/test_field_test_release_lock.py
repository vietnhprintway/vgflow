"""tests/test_field_test_release_lock.py — stuck-lock recovery."""
from __future__ import annotations

import os, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_LOCK = REPO_ROOT / "scripts" / "field-test" / "release-lock.py"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "release-lock.py"


def test_scripts_exist():
    assert RELEASE_LOCK.is_file()


def test_mirror_byte_identity():
    assert RELEASE_LOCK.read_bytes() == MIRROR.read_bytes()


def test_release_lock_removes_dead_pid_lock(tmp_path):
    lock_dir = tmp_path / ".vg" / "field-test" / ".active"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner").write_text("ft-deadbeef")
    (lock_dir / "pid").write_text("99999999")  # definitely-dead PID
    r = subprocess.run([sys.executable, str(RELEASE_LOCK), "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"stderr={r.stderr}"
    assert not lock_dir.exists(), "dead-PID lock should be released"


def test_release_lock_refuses_live_pid_lock(tmp_path):
    lock_dir = tmp_path / ".vg" / "field-test" / ".active"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner").write_text("ft-live")
    (lock_dir / "pid").write_text(str(os.getpid()))  # self is alive
    r = subprocess.run([sys.executable, str(RELEASE_LOCK), "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert lock_dir.exists(), "live-PID lock must NOT be released"
    assert "alive" in (r.stdout + r.stderr).lower()


def test_release_lock_idempotent_when_no_lock(tmp_path):
    r = subprocess.run([sys.executable, str(RELEASE_LOCK), "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_release_lock_force_releases_live_pid(tmp_path):
    """--force removes lock even if owner PID is alive."""
    lock_dir = tmp_path / ".vg" / "field-test" / ".active"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner").write_text("ft-live")
    (lock_dir / "pid").write_text(str(os.getpid()))
    r = subprocess.run([sys.executable, str(RELEASE_LOCK), "--root", str(tmp_path), "--force"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert not lock_dir.exists()
