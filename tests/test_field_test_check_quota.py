"""tests/test_field_test_check_quota.py — quota enforcement helper."""
from __future__ import annotations

import json, subprocess, sys, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_QUOTA = REPO_ROOT / "scripts" / "field-test" / "check-quota.py"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "check-quota.py"


def test_scripts_exist():
    assert CHECK_QUOTA.is_file()


def test_mirror_byte_identity():
    assert CHECK_QUOTA.read_bytes() == MIRROR.read_bytes()


def test_check_quota_passes_under_caps(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test",
        "started_at": time.time(),
        "session_max_size_mb": 100,
        "max_session_hours": 2,
    }), encoding="utf-8")
    (session / "small.log").write_text("a" * 1024)
    r = subprocess.run([sys.executable, str(CHECK_QUOTA), "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_check_quota_fails_on_size_cap(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test", "started_at": time.time(),
        "session_max_size_mb": 0,  # any size > 0 trips
        "max_session_hours": 24,
    }), encoding="utf-8")
    (session / "blob.bin").write_bytes(b"x" * (2 * 1024))
    r = subprocess.run([sys.executable, str(CHECK_QUOTA), "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    combined = (r.stdout + r.stderr).lower()
    assert "size" in combined


def test_check_quota_fails_on_wall_clock(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test",
        "started_at": time.time() - 3 * 3600,
        "session_max_size_mb": 1024,
        "max_session_hours": 1,
    }), encoding="utf-8")
    r = subprocess.run([sys.executable, str(CHECK_QUOTA), "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    combined = (r.stdout + r.stderr).lower()
    assert "wall" in combined or "hours" in combined or "clock" in combined
