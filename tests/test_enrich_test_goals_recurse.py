"""Verify enrich-test-goals.py optionally merges G-RECURSE-* stubs from
runs/goals-*.partial.yaml without overwriting Haiku-discovered G-AUTO-*
goals.

Task 24 (Phase 1.D core wiring).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ENRICH = REPO_ROOT / "scripts" / "enrich-test-goals.py"


def _build_phase(tmp_path: Path) -> Path:
    """Minimal phase dir with one scan + one runs/goals partial."""
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "TEST-GOALS.md").write_text(
        "# Existing\n---\nid: G-001\ntitle: existing goal\n---\n",
        encoding="utf-8",
    )
    # RUNTIME-MAP.json minimal shape — required by load_runtime_map.
    (phase / "RUNTIME-MAP.json").write_text(json.dumps({
        "views": {
            "/admin/orders": {
                "elements": [
                    {"name": "Add Order", "type": "button"},
                    {"name": "Filter", "type": "filter"},
                    {"name": "Sort", "type": "sort"},
                ],
            },
        },
    }), encoding="utf-8")
    (phase / "scan-admin-orders.json").write_text(json.dumps({
        "view": "/admin/orders",
        "elements_total": 5,
        "actions": [
            {"name": "Add Order", "selector": "#add"},
            {"name": "Bulk Delete", "selector": "#bulk"},
        ],
        "forms": [],
        "modals": [],
    }), encoding="utf-8")
    runs = phase / "runs"
    runs.mkdir()
    # G-RECURSE partial that aggregator will pick up.
    (runs / "goals-worker1.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/admin/orders",
        "selector_hash": "ab12cd",
        "action_semantic": "delete",
        "lens": "lens-authz-negative",
        "resource": "orders",
        "assertion_type": "forbidden",
        "depth": 1,
        "element_class": "row_action",
    }]), encoding="utf-8")
    return phase


def test_enrich_emits_auto_goals(tmp_path: Path) -> None:
    phase = _build_phase(tmp_path)
    r = subprocess.run(
        [sys.executable, str(ENRICH), "--phase-dir", str(phase), "--quiet"],
        capture_output=True, text=True, check=True,
    )
    out = phase / "TEST-GOALS-DISCOVERED.md"
    assert out.is_file(), r.stderr
    body = out.read_text(encoding="utf-8")
    assert "G-AUTO-" in body, "auto goals must be present"


def test_enrich_merge_recursive_keeps_auto_goals(tmp_path: Path) -> None:
    """--merge-recursive must add G-RECURSE-* without dropping G-AUTO-*."""
    phase = _build_phase(tmp_path)
    r = subprocess.run(
        [sys.executable, str(ENRICH), "--phase-dir", str(phase),
         "--merge-recursive", "--quiet"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body = (phase / "TEST-GOALS-DISCOVERED.md").read_text(encoding="utf-8")
    assert "G-AUTO-" in body, "Haiku-discovered G-AUTO-* lost after merge"
    assert "G-RECURSE-" in body, "recursive goals not merged"
    # Both source markers present
    assert "review.runtime_discovery" in body or "source: review" in body
    assert "review.recursive_probe" in body


def test_enrich_no_merge_default(tmp_path: Path) -> None:
    """Default invocation (no --merge-recursive) does NOT call aggregator."""
    phase = _build_phase(tmp_path)
    subprocess.run(
        [sys.executable, str(ENRICH), "--phase-dir", str(phase), "--quiet"],
        capture_output=True, text=True, check=True,
    )
    body = (phase / "TEST-GOALS-DISCOVERED.md").read_text(encoding="utf-8")
    assert "G-RECURSE-" not in body, "merge must be opt-in"
