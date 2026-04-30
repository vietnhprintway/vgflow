"""Verify discover-iteration.py extends iterate-state.json schema with
recursion_depth per view (v2.40 Task 25). Existing schema parsers must
keep working — `iteration` int field stays canonical.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "discover-iteration.py"


def _build_phase(tmp_path: Path) -> Path:
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "nav-discovery.json").write_text(json.dumps({
        "views": {"/admin": {"url": "/admin", "visible_to": []}},
    }), encoding="utf-8")
    # Scan exposes a sub-view that nav doesn't know about.
    (phase / "scan-admin.json").write_text(json.dumps({
        "view": "/admin",
        "sub_views_discovered": ["/admin/orders"],
    }), encoding="utf-8")
    return phase


def test_existing_iteration_field_preserved(tmp_path: Path) -> None:
    """Existing schema readers (iter_now = state['iteration']) keep working."""
    phase = _build_phase(tmp_path)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase), "--quiet"],
        capture_output=True, text=True, check=True,
    )
    state = json.loads((phase / "iteration-state.json").read_text(encoding="utf-8"))
    assert state["iteration"] == 1, r.stdout + r.stderr


def test_recursion_depth_field_present(tmp_path: Path) -> None:
    """After Task 25, state file carries recursion_depth map keyed by view."""
    phase = _build_phase(tmp_path)
    subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase),
         "--recursion-depth", "2", "--quiet"],
        capture_output=True, text=True, check=True,
    )
    state = json.loads((phase / "iteration-state.json").read_text(encoding="utf-8"))
    assert "recursion_depth" in state
    rd = state["recursion_depth"]
    assert isinstance(rd, dict)
    # Newly queued view should be tagged with the supplied depth.
    assert rd.get("/admin/orders") == 2


def test_recursion_depth_default_one(tmp_path: Path) -> None:
    """Without --recursion-depth flag, depth defaults to 1 per queued view."""
    phase = _build_phase(tmp_path)
    subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase), "--quiet"],
        capture_output=True, text=True, check=True,
    )
    state = json.loads((phase / "iteration-state.json").read_text(encoding="utf-8"))
    assert state.get("recursion_depth", {}).get("/admin/orders") == 1


def test_check_mode_no_state_mutation(tmp_path: Path) -> None:
    """--check must not write iteration-state.json."""
    phase = _build_phase(tmp_path)
    subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase),
         "--check", "--quiet"],
        capture_output=True, text=True, check=True,
    )
    assert not (phase / "iteration-state.json").exists()
