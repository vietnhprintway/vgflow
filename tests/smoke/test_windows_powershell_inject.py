"""Stage 6 task 4/5 — cross-platform smoke for meta-memory v1.1 scripts.

The bootstrap-loader and bootstrap-consolidate scripts run inside Windows
PowerShell-shell hooks for VG users on Windows. These smoke tests assert
the Python entry points launch cleanly under the current OS without
crashing — independent of project state. Empty rules dirs / fresh state
dirs MUST yield rc=0 (well-formed empty output, not a traceback).

Per-platform skipif markers keep the suite green on either OS.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
LOADER = str(REPO / ".claude" / "scripts" / "bootstrap-loader.py")
CONSOLIDATE = str(REPO / ".claude" / "scripts" / "bootstrap-consolidate.py")


@pytest.mark.skipif(os.name != "nt", reason="Windows-only smoke")
def test_bootstrap_loader_runs_under_windows(tmp_path):
    """Loader runs under Windows Python without crash. Point at an empty
    rules dir so output is the empty-rules JSON envelope, not whatever the
    repo's own .vg/bootstrap/ happens to hold."""
    env = os.environ.copy()
    env["VG_BOOTSTRAP_RULES_DIR"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable, LOADER,
            "--target-step", "build",
            "--emit", "rules",
        ],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"loader crashed under Windows; rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only smoke")
def test_bootstrap_consolidate_check_gate_under_windows(tmp_path):
    """consolidate --check-gate runs under Windows Python without crash.
    First run on a fresh state dir → gate open → rc=0."""
    env = os.environ.copy()
    env["VG_BOOTSTRAP_STATE_DIR"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable, CONSOLIDATE,
            "--check-gate", "--json",
        ],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"consolidate --check-gate crashed under Windows; rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only smoke")
def test_bootstrap_loader_runs_under_posix(tmp_path):
    """Symmetric: same loader smoke on POSIX (Mac/Linux). Empty rules dir
    via VG_BOOTSTRAP_RULES_DIR keeps the test hermetic."""
    env = os.environ.copy()
    env["VG_BOOTSTRAP_RULES_DIR"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable, LOADER,
            "--target-step", "build",
            "--emit", "rules",
        ],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"loader crashed under POSIX; rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
