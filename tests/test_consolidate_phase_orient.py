"""Stage 5 task 2/6 of meta-memory v1.1 — Phase 1 Orient.

The Orient phase (Anthropic Auto Dream step 1, design Section 13.1) is a
read-only snapshot of `.vg/bootstrap/`. It never mutates anything; later
phases consume its JSON output as the "where are we starting from?" baseline.

Tests cover:
  * empty state dir is safe (rc=0, sane defaults)
  * rule_count reflects rules/*.md
  * memory_md_lines counts lines in MEMORY.md
  * oversized_files flags any file > 50KB anywhere under state_dir
  * orphan_files flags unknown top-level entries
  * existence flags for ACCEPTED/REJECTED/RETRACTED/CANDIDATES
  * state.json values surface as last_consolidation_ts + sessions_since_last
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CONSOLIDATE = ".claude/scripts/bootstrap-consolidate.py"


def _run_orient(state_dir: Path, json_out: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["VG_BOOTSTRAP_STATE_DIR"] = str(state_dir)
    argv = [sys.executable, CONSOLIDATE, "--phase", "orient"]
    if json_out:
        argv.append("--json")
    return subprocess.run(argv, capture_output=True, text=True, env=env)


def test_orient_empty_state_dir_safe(tmp_path):
    """No .vg/bootstrap/ files -> orient returns empty snapshot, rc=0."""
    # tmp_path exists but is empty - simulating a brand new repo.
    result = _run_orient(tmp_path)
    assert result.returncode == 0, result.stderr
    snap = json.loads(result.stdout)
    assert snap["phase"] == "orient"
    assert snap["rule_count"] == 0
    assert snap["accepted_md_exists"] is False
    assert snap["rejected_md_exists"] is False
    assert snap["retracted_md_exists"] is False
    assert snap["candidates_md_exists"] is False
    assert snap["memory_md_lines"] == 0
    assert snap["oversized_files"] == []
    assert snap["orphan_files"] == []


def test_orient_with_existing_rules(tmp_path):
    """rule_count reflects len(rules/*.md)."""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "r1.md").write_text("---\nslug: r1\n---\nbody\n", encoding="utf-8")
    (rules / "r2.md").write_text("---\nslug: r2\n---\nbody\n", encoding="utf-8")
    (rules / "r3.md").write_text("---\nslug: r3\n---\nbody\n", encoding="utf-8")
    # Non-md file in rules/ must not count.
    (rules / "README.txt").write_text("not a rule", encoding="utf-8")

    result = _run_orient(tmp_path)
    assert result.returncode == 0, result.stderr
    snap = json.loads(result.stdout)
    assert snap["rule_count"] == 3


def test_orient_detects_memory_md_size(tmp_path):
    """memory_md_lines counts lines (with or without trailing newline)."""
    body = "\n".join(f"line {i}" for i in range(150))
    (tmp_path / "MEMORY.md").write_text(body + "\n", encoding="utf-8")

    result = _run_orient(tmp_path)
    snap = json.loads(result.stdout)
    assert snap["memory_md_exists"] is True
    assert snap["memory_md_lines"] == 150


def test_orient_flags_oversize_files(tmp_path):
    """Any file > 50KB anywhere under state_dir surfaces in oversized_files."""
    rules = tmp_path / "rules"
    rules.mkdir()
    big = rules / "big.md"
    big.write_text("x" * 60_000, encoding="utf-8")  # 60KB > 50KB threshold
    small = rules / "small.md"
    small.write_text("x" * 100, encoding="utf-8")

    result = _run_orient(tmp_path)
    snap = json.loads(result.stdout)
    assert any("big.md" in f for f in snap["oversized_files"]), snap["oversized_files"]
    assert not any("small.md" in f for f in snap["oversized_files"])


def test_orient_existence_flags_for_known_files(tmp_path):
    """ACCEPTED/REJECTED/RETRACTED/CANDIDATES md flags reflect file presence."""
    (tmp_path / "ACCEPTED.md").write_text("# accepted\n", encoding="utf-8")
    (tmp_path / "REJECTED.md").write_text("# rejected\n", encoding="utf-8")
    # RETRACTED + CANDIDATES intentionally absent

    result = _run_orient(tmp_path)
    snap = json.loads(result.stdout)
    assert snap["accepted_md_exists"] is True
    assert snap["rejected_md_exists"] is True
    assert snap["retracted_md_exists"] is False
    assert snap["candidates_md_exists"] is False


def test_orient_orphan_detection(tmp_path):
    """Unknown top-level files (not in KNOWN_TOP_LEVEL) surface as orphans."""
    (tmp_path / "ACCEPTED.md").write_text("# accepted\n", encoding="utf-8")
    (tmp_path / "scratch.txt").write_text("orphan!\n", encoding="utf-8")
    (tmp_path / "weird-dir").mkdir()

    result = _run_orient(tmp_path)
    snap = json.loads(result.stdout)
    assert "scratch.txt" in snap["orphan_files"]
    assert "weird-dir/" in snap["orphan_files"]
    # ACCEPTED.md is recognized -> NOT an orphan
    assert "ACCEPTED.md" not in snap["orphan_files"]


def test_orient_surfaces_state_json_fields(tmp_path):
    """last_run_ts + sessions_since_last from state.json appear in snapshot."""
    state = {"last_run_ts": 1_700_000_000.5, "sessions_since_last": 7}
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")

    result = _run_orient(tmp_path)
    snap = json.loads(result.stdout)
    assert snap["last_consolidation_ts"] == 1_700_000_000.5
    assert snap["sessions_since_last"] == 7


def test_orient_text_output_default_is_human_readable(tmp_path):
    """Without --json, output is human-readable (still rc=0)."""
    result = _run_orient(tmp_path, json_out=False)
    assert result.returncode == 0, result.stderr
    assert "phase=orient" in result.stdout
    assert "rules:" in result.stdout
