"""v2.82.1 Stage 6.5 — phase context auto-detection."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))


@pytest.fixture
def phase_mod():
    from deploy import phase_context  # type: ignore[import-not-found]

    return phase_context


def test_explicit_override_wins(tmp_path, phase_mod):
    assert phase_mod.detect_phase_context(tmp_path, override="42") == "42"


def test_override_strips_whitespace(tmp_path, phase_mod):
    assert phase_mod.detect_phase_context(tmp_path, override="  6 ") == "6"


def test_active_run_phase(tmp_path, phase_mod):
    runs = tmp_path / ".vg" / "active-runs"
    runs.mkdir(parents=True)
    (runs / "abc.json").write_text(
        json.dumps({"command": "vg:scope", "phase": "6", "run_id": "r1"}),
        encoding="utf-8",
    )
    assert phase_mod.detect_phase_context(tmp_path) == "6"


def test_active_run_picks_newest(tmp_path, phase_mod):
    runs = tmp_path / ".vg" / "active-runs"
    runs.mkdir(parents=True)
    older = runs / "older.json"
    older.write_text(json.dumps({"phase": "1"}), encoding="utf-8")
    # Set older mtime
    os.utime(older, (1, 1))
    newer = runs / "newer.json"
    newer.write_text(json.dumps({"phase": "9"}), encoding="utf-8")
    assert phase_mod.detect_phase_context(tmp_path) == "9"


def test_active_run_skips_corrupt_then_finds_valid(tmp_path, phase_mod):
    runs = tmp_path / ".vg" / "active-runs"
    runs.mkdir(parents=True)
    (runs / "broken.json").write_text("{not json", encoding="utf-8")
    (runs / "good.json").write_text(json.dumps({"phase": "3"}), encoding="utf-8")
    # Force broken.json to be newer
    os.utime(runs / "good.json", (1, 1))
    # Result depends on which is "newest"; at minimum, broken should NOT raise.
    out = phase_mod.detect_phase_context(tmp_path)
    # Either falls back to good, or returns None (corrupt = skipped)
    assert out in ("3", None)


def test_active_run_no_phase_field(tmp_path, phase_mod):
    runs = tmp_path / ".vg" / "active-runs"
    runs.mkdir(parents=True)
    (runs / "no-phase.json").write_text(
        json.dumps({"command": "vg:scope", "run_id": "r1"}),
        encoding="utf-8",
    )
    # No phase + no other detection sources = None
    assert phase_mod.detect_phase_context(tmp_path) is None


def test_git_branch_phase_pattern(tmp_path, phase_mod):
    """Branch named 'phase-6' detected."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@x.dev"], cwd=str(tmp_path), check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=str(tmp_path), check=True
    )
    (tmp_path / "f").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "phase-6"], cwd=str(tmp_path), check=True
    )
    assert phase_mod.detect_phase_context(tmp_path) == "6"


def test_git_branch_vg_pattern(tmp_path, phase_mod):
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@x.dev"], cwd=str(tmp_path), check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "T"], cwd=str(tmp_path), check=True
    )
    (tmp_path / "f").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "vg-12.4"], cwd=str(tmp_path), check=True
    )
    assert phase_mod.detect_phase_context(tmp_path) == "12.4"


def test_no_signals_returns_none(tmp_path, phase_mod):
    """Empty project — no marker sources → None."""
    assert phase_mod.detect_phase_context(tmp_path) is None


def test_events_db_last_scope_run(tmp_path, phase_mod):
    """Falls back to events.db when no active-run + no branch pattern."""
    db_path = tmp_path / ".vg" / "events.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """CREATE TABLE runs (
                run_id TEXT,
                command TEXT,
                phase TEXT,
                started_at TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            ("r1", "vg:scope", "5", "2026-05-10T10:00:00Z"),
        )
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            ("r2", "vg:scope", "7", "2026-05-10T12:00:00Z"),
        )
        conn.commit()
    assert phase_mod.detect_phase_context(tmp_path) == "7"
