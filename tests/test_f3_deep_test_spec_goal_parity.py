"""tests/test_f3_deep_test_spec_goal_parity.py — F3 goal parity gate."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VAL = REPO / "scripts" / "validators" / "verify-deep-test-specs.py"


def test_validator_fails_on_omitted_automatable_goals(tmp_path):
    phase_dir = tmp_path / ".vg" / "phases" / "07"
    phase_dir.mkdir(parents=True)
    # TEST-GOALS.md declares G-01, G-02, G-03 (all automatable)
    (phase_dir / "TEST-GOALS.md").write_text(
        "# Test Goals\n\n"
        "## G-01 — Login flow\n- automation: yes\n\n"
        "## G-02 — Create order\n- automation: yes\n\n"
        "## G-03 — Cancel order\n- automation: yes\n",
        encoding="utf-8"
    )
    # LIFECYCLE-SPECS.json only emits G-01 (G-02, G-03 silently dropped)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "phase": "07",
        "goals": {"G-01": {"stages": [{"name": "auth"}, {"name": "verify"}]}}
    }), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(VAL), "--phase-dir", str(phase_dir), "--check-goal-parity"],
        capture_output=True, text=True,
    )
    combined = r.stdout + r.stderr
    assert r.returncode != 0, (
        f"F3: validator must fail when LIFECYCLE-SPECS omits automatable goals "
        f"from TEST-GOALS. rc={r.returncode}, out={combined[:300]}"
    )
    assert ("G-02" in combined or "G-03" in combined or "parity" in combined.lower()), (
        f"F3: failure message must name omitted goals. Got: {combined[:300]}"
    )
