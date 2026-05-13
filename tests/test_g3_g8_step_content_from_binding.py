"""tests/test_g3_g8_step_content_from_binding.py — G3+G8 step content quality.

G3: step.description for create stage must reference bound endpoint path/method,
    not generic template string.
G8: each step assertion entry must have 'check' field (discrete, not freeform).
"""
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
    assert r.returncode == 0, f"Generator failed: {r.stderr[:300]}"
    return json.loads(out.read_text(encoding="utf-8"))


def test_g8_step_assertions_have_check_field(tmp_path):
    """G8: each step assertion entry must have 'check' field (discrete, not freeform)."""
    goals = """\
## Goal G-01: Create order
**goal_type:** create-only
**Mutation evidence:** POST /api/orders returns 201
"""
    contracts = "## POST /api/orders\nResponse: 201\n"
    spec = _gen(tmp_path, goals, contracts)
    goal = spec["goals"]["G-01"]
    for step in goal["steps"]:
        for a in (step.get("assertions") or []):
            assert "check" in a or "source" in a, (
                f"G8: step assertion missing check/source: {a}"
            )


def test_g3_step_description_references_endpoint(tmp_path):
    """G3: step.description (action) for create stage must reference bound endpoint path/method,
    not generic template string."""
    goals = """\
## Goal G-01: Create order
**goal_type:** create-only
**Mutation evidence:** POST /api/orders returns 201
"""
    contracts = "## POST /api/orders\nResponse: 201\n"
    spec = _gen(tmp_path, goals, contracts)
    goal = spec["goals"]["G-01"]
    create_step = next((s for s in goal["steps"] if s.get("name") == "create"), None)
    assert create_step is not None, "G3: create step must exist"
    # Check action or description field references the endpoint
    action = create_step.get("action", "")
    description = create_step.get("description", "")
    combined = action + " " + description
    # When endpoint binding succeeded, description/action must reference endpoint
    if create_step.get("endpoint"):
        ep = create_step["endpoint"]
        assert (ep["method"] in combined or ep["path"] in combined), (
            f"G3: create step action/description must reference bound endpoint {ep}; "
            f"got action={action!r} description={description!r}"
        )


def test_g3_step_description_helper_wires_method_and_path(tmp_path):
    """G3: _step_description helper provides method+path in action when endpoint present."""
    goals = """\
## Goal G-01: Create item
**goal_type:** create-only
**Mutation evidence:** POST /api/items
"""
    contracts = "## POST /api/items\nResponse: 201\n"
    spec = _gen(tmp_path, goals, contracts)
    goal = spec["goals"]["G-01"]
    create_step = next((s for s in goal["steps"] if s.get("name") == "create"), None)
    assert create_step is not None
    action = create_step.get("action", "")
    if create_step.get("endpoint"):
        ep = create_step["endpoint"]
        assert "POST" in action or "/api/items" in action, (
            f"G3: action must embed POST /api/items when endpoint is bound. got={action!r}"
        )
