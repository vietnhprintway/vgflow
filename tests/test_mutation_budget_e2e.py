"""Mutation budget E2E (Task 30, v2.40.0).

Generates a synthetic phase with ≥80 mutation_button clickables, runs the
manager in sandbox mode (mutation_budget=50 per env_policy), and verifies
the plan is truncated to 50 entries with the rest dropped on the floor.

Telemetry assertion:
  recursion.mutation_budget_exhausted is the contract counter — emission
  is deferred to v2.41 because spawn_recursive_probe.apply_env_policy
  currently truncates silently. Marked pytest.skip; kept as a regression
  hook.

No real Gemini subprocess: the test runs --dry-run --json and inspects
``planned_spawns`` count.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"
SMOKE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def _build_phase_with_n_mutation_buttons(tmp_path: Path, n: int) -> Path:
    """Clone the smoke fixture and overwrite scan-admin.json with N mutation buttons."""
    dst = tmp_path / "phase"
    shutil.copytree(SMOKE_FIXTURE, dst)
    # Replace scan-admin.json with N mutation buttons (each unique resource so
    # build_plan doesn't dedupe them via the (resource, role, lens) scope key).
    results = []
    for i in range(n):
        results.append({
            "selector": f"button#mutate-{i}",
            "network": [{"method": "DELETE", "path": f"/api/resource{i}/{i}"}],
        })
    (dst / "scan-admin.json").write_text(
        json.dumps({
            "view": "/admin/big-view",
            "results": results,
            "forms": [],
            "modal_triggers": [],
            "sub_views_discovered": [],
        }), encoding="utf-8",
    )
    # Drop conflicting touched_resources so eligibility passes lazily.
    (dst / "SUMMARY.md").write_text(
        "```yaml\ntouched_resources: []\n```\n", encoding="utf-8",
    )
    # CRUD-SURFACES already lists topup_requests; keep it (rule 4 lenient when
    # touched_resources is empty).
    return dst


def _run_dry(phase: Path, *extra: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase),
         "--dry-run", "--json", "--non-interactive", *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# Test 1: 80 mutation buttons in sandbox → plan truncates to mutation_budget=50
# ---------------------------------------------------------------------------
def test_80_mutation_buttons_truncate_to_sandbox_budget(tmp_path: Path) -> None:
    phase = _build_phase_with_n_mutation_buttons(tmp_path, 80)
    out = _run_dry(phase, "--mode", "exhaustive", "--target-env", "sandbox")
    spawns = out["planned_spawns"]
    # Sandbox mutation_budget = 50; even though exhaustive cap allows 100,
    # apply_env_policy clips the plan to 50.
    assert len(spawns) == 50, (
        f"expected 50 spawns under sandbox budget, got {len(spawns)}"
    )
    assert out["env_policy"]["mutation_budget"] == 50
    assert out["env_policy"]["env"] == "sandbox"


# ---------------------------------------------------------------------------
# Test 2: prod env → mutation_budget=0 + only safe lenses survive
# ---------------------------------------------------------------------------
def test_prod_env_budget_zero_strips_all_mutation_lenses(tmp_path: Path) -> None:
    """Prod policy allows only lens-info-disclosure + lens-auth-jwt; mutation_button
    fans out to authz-negative + duplicate-submit + bfla — all stripped.
    Expect 0 planned spawns."""
    phase = _build_phase_with_n_mutation_buttons(tmp_path, 80)
    out = _run_dry(
        phase, "--mode", "exhaustive",
        "--target-env", "prod",
        "--i-know-this-is-prod", "test fixture",
    )
    spawns = out["planned_spawns"]
    assert len(spawns) == 0, f"prod must allow zero mutation spawns, got {len(spawns)}"
    assert out["env_policy"]["mutation_budget"] == 0
    assert out["env_policy"]["env"] == "prod"


# ---------------------------------------------------------------------------
# Test 3: local env → unlimited budget keeps the full mode-cap envelope
# ---------------------------------------------------------------------------
def test_local_env_unlimited_budget_keeps_full_plan(tmp_path: Path) -> None:
    """Local policy mutation_budget=-1 (unlimited). 80 buttons × 3 lenses = 240
    pre-cap → exhaustive cap=100 keeps 100. Local policy then keeps all 100."""
    phase = _build_phase_with_n_mutation_buttons(tmp_path, 80)
    out = _run_dry(phase, "--mode", "exhaustive", "--target-env", "local")
    spawns = out["planned_spawns"]
    # exhaustive cap is 100; local doesn't trim further.
    assert len(spawns) == 100, f"expected 100 spawns under local + exhaustive, got {len(spawns)}"
    assert out["env_policy"]["mutation_budget"] == -1


# ---------------------------------------------------------------------------
# Test 4: telemetry recursion.mutation_budget_exhausted — DEFERRED to v2.41
# ---------------------------------------------------------------------------
def test_mutation_budget_exhausted_telemetry_emitted(tmp_path: Path) -> None:
    """Future contract: when plan_pre_budget > kept_post_budget, emit a
    ``recursion.mutation_budget_exhausted`` event. Currently apply_env_policy
    truncates silently — the telemetry hook lands in v2.41.
    """
    pytest.skip(
        "recursion.mutation_budget_exhausted telemetry not yet wired — "
        "see scripts/spawn_recursive_probe.py:apply_env_policy."
    )
