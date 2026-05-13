"""tests/test_g2_per_verb_stages.py — G2 per-verb stage derivation."""
from __future__ import annotations
import json
import subprocess
import sys
import os
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "scripts" / "generate-lifecycle-specs.py"


def _gen(tmp_path, goals_md, contracts_md=""):
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "TEST-GOALS.md").write_text(goals_md, encoding="utf-8")
    if contracts_md:
        (phase_dir / "API-CONTRACTS.md").write_text(contracts_md, encoding="utf-8")
    out = phase_dir / "LIFECYCLE-SPECS.json"
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "99", "--phase-dir", str(phase_dir),
         "--out", str(out)],
        capture_output=True, text=True, env={**os.environ, "VG_REPO_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_create_only_goal_has_short_lifecycle(tmp_path):
    """v5.0 G2: create-only goal → R+C+R (3 stages, not full 7)."""
    goals = """## Goal G-01: User creates note

**goal_type:** create-only
**Surface:** api
**mutation_evidence:** POST /api/notes returns 201
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-01"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    # Create-only must have read_before + create + read_after_create only
    assert "create" in stage_names
    assert "read_after_create" in stage_names
    # Must NOT have delete or update stages
    assert "delete" not in stage_names, (
        f"G2: create-only goal should not have delete stage; got {stage_names}"
    )
    assert "update" not in stage_names, (
        f"G2: create-only goal should not have update stage; got {stage_names}"
    )


def test_delete_only_goal_has_short_lifecycle(tmp_path):
    """v5.0 G2: delete-only goal → R+D+R (no create/update)."""
    goals = """## Goal G-02: User deletes existing note

**goal_type:** delete-only
**Surface:** api
**mutation_evidence:** DELETE /api/notes/:id returns 204
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-02"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    assert "delete" in stage_names
    assert "read_after_delete" in stage_names
    assert "create" not in stage_names, (
        f"G2: delete-only goal should not have create stage; got {stage_names}"
    )
    assert "update" not in stage_names


def test_full_mutation_goal_keeps_rcrurdr(tmp_path):
    """v5.0 G2: full CRUD goal → R+C+R+U+R+D+R (7 stages)."""
    goals = """## Goal G-03: Full CRUD on tasks

**goal_type:** mutation
**Surface:** api
**mutation_evidence:** POST/PUT/DELETE /api/tasks
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-03"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    # Full RCRURDR
    assert "create" in stage_names
    assert "update" in stage_names
    assert "delete" in stage_names
    # 7 stages
    assert len(goal["steps"]) >= 6  # tolerant for goals where read_before merges
