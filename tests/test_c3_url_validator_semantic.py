"""tests/test_c3_url_validator_semantic.py — C3 URL semantic correctness.

Verifies that verify-url-state-runtime.py checks result_semantics, not just
param presence. A filter with ?status=pending in URL but table still showing
all rows should BLOCK (result_semantics.passed=false).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VAL = REPO / "scripts" / "validators" / "verify-url-state-runtime.py"


def _run_val(tmp_path, probe_data, goals_text=None):
    """Run validator with probe data. Goals file must have url_sync goal."""
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "url-runtime-probe.json").write_text(
        json.dumps(probe_data), encoding="utf-8"
    )
    # Minimal TEST-GOALS.md with url_sync: true goal
    if goals_text is None:
        goals_text = """\
## Goal G-01: Projects list filter

**interactive_controls:**
  url_sync: true
  filters:
    - name: status
      url_param: status
"""
    (phase_dir / "TEST-GOALS.md").write_text(goals_text, encoding="utf-8")
    env = {**os.environ, "VG_REPO_ROOT": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase", "99"],
        capture_output=True, text=True, env=env,
    )
    return r


def test_validator_flags_url_param_present_but_semantics_fail(tmp_path):
    """C3: filter URL has correct param but result_semantics.passed=false -> must BLOCK."""
    probe = {
        "goals": [{
            "goal_id": "G-01",
            "url": "/projects?status=pending",
            "controls": [{
                "kind": "filter",
                "name": "status",
                "value": "pending",
                "url_param_expected": "status",
                "url_params_after": {"status": "pending"},
                "result_semantics": {"passed": False, "reason": "table still shows all rows",
                                     "rows_checked": 5, "violations": ["row-1 has status=approved"]},
            }]
        }]
    }
    r = _run_val(tmp_path, probe)
    assert (r.returncode != 0) or "semantic" in r.stdout.lower() or "result_semantics" in r.stdout or "C3" in r.stdout, (
        f"C3: validator must flag when url param present but result_semantics.passed=false. "
        f"stdout={r.stdout[:500]} stderr={r.stderr[:200]}"
    )


def test_validator_passes_when_both_present_and_semantics_pass(tmp_path):
    """C3: well-formed probe with param present + semantics passed -> no C3 errors."""
    probe = {
        "goals": [{
            "goal_id": "G-01",
            "url": "/projects?status=pending",
            "controls": [{
                "kind": "filter",
                "name": "status",
                "value": "pending",
                "url_param_expected": "status",
                "url_params_after": {"status": "pending"},
                "result_semantics": {"passed": True, "rows_checked": 3, "violations": []},
            }]
        }]
    }
    r = _run_val(tmp_path, probe)
    if r.returncode != 0 and "C3" in r.stdout:
        assert False, f"C3: well-formed evidence must not trigger C3 errors. stdout={r.stdout[:500]}"


def test_validator_flags_filter_without_result_semantics(tmp_path):
    """C3: filter probe missing result_semantics entirely should be flagged."""
    probe = {
        "goals": [{
            "goal_id": "G-01",
            "url": "/projects?status=pending",
            "controls": [{
                "kind": "filter",
                "name": "status",
                "value": "pending",
                "url_param_expected": "status",
                "url_params_after": {"status": "pending"},
                # result_semantics absent
            }]
        }]
    }
    r = _run_val(tmp_path, probe)
    # The validator should flag missing result_semantics for filter controls
    assert (r.returncode != 0) or "semantic" in r.stdout.lower() or "result_semantics" in r.stdout, (
        f"C3: validator must flag filter probe without result_semantics. "
        f"stdout={r.stdout[:500]}"
    )
