"""Hybrid-mode E2E (Task 30, v2.40.0 + v2.40.2 hard-fail).

Hybrid contract per design doc:
  - lenses listed in vg.config recursive_probe.hybrid_routing.auto_lenses →
    spawn worker (auto)
  - lenses in hybrid_routing.manual_lenses → render prompt file (manual)
  - both groups merge in goal back-flow

State of the implementation as of v2.40.2:
  spawn_recursive_probe.py main() detects --probe-mode=hybrid and HARD-FAILS
  with exit 1 + a clear "ship in v2.41" message. The pre-v2.40.2 silent
  auto-fallback was hiding the limitation. Tests below lock in the new
  fail-loud contract; the auto/manual split assertions remain pytest.skip'd
  until v2.41.

We exercise dry-run paths with --dry-run so no real Gemini fires.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"
SMOKE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def _copy_fixture(tmp_path: Path) -> Path:
    dst = tmp_path / "phase"
    shutil.copytree(SMOKE_FIXTURE, dst)
    return dst


def _run_dry_hybrid(phase: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--phase-dir", str(phase),
         "--mode", "light",
         "--probe-mode", "hybrid",
         "--non-interactive",
         "--target-env", "sandbox",
         "--dry-run", "--json"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# Test 1: hybrid mode is accepted by the CLI + plan composes
# ---------------------------------------------------------------------------
def test_hybrid_mode_dry_run_composes_plan(tmp_path: Path) -> None:
    phase = _copy_fixture(tmp_path)
    out = _run_dry_hybrid(phase)
    assert out["probe_mode"] == "hybrid"
    spawns = out["planned_spawns"]
    assert spawns, f"hybrid mode should still produce a plan, got: {out}"
    # Light cap = 15.
    assert 1 <= len(spawns) <= 15


# ---------------------------------------------------------------------------
# Test 2: hybrid_routing config defines disjoint auto/manual lens sets
# ---------------------------------------------------------------------------
def test_hybrid_routing_config_disjoint() -> None:
    """Sanity gate against a regression where someone adds a lens to BOTH lists."""
    template = REPO_ROOT / "vg.config.template.md"
    text = template.read_text(encoding="utf-8")
    # Quick parse: find lines under hybrid_routing: until the next top-level key.
    # We rely on the existing hybrid_routing block in vg.config.template.md.
    assert "hybrid_routing:" in text
    auto_idx = text.index("auto_lenses:")
    manual_idx = text.index("manual_lenses:")
    auto_block = text[auto_idx:manual_idx]
    # Crude: find next top-level key after manual_lenses.
    after = text[manual_idx:]
    end = after.find("\n  # ")
    manual_block = after[:end] if end > 0 else after[:600]

    auto_lenses = {
        line.strip().strip('-').strip().strip('"').strip("'")
        for line in auto_block.splitlines()
        if line.strip().startswith('- "lens-')
    }
    manual_lenses = {
        line.strip().strip('-').strip().strip('"').strip("'")
        for line in manual_block.splitlines()
        if line.strip().startswith('- "lens-')
    }
    assert auto_lenses, f"could not parse auto_lenses; first 200 chars: {auto_block[:200]}"
    assert manual_lenses, f"could not parse manual_lenses"
    overlap = auto_lenses & manual_lenses
    assert not overlap, f"hybrid routing lists must be disjoint, overlap={overlap}"


# ---------------------------------------------------------------------------
# Test 3: hybrid hard-fails with a clear v2.41-deferred message (v2.40.2)
# ---------------------------------------------------------------------------
def test_hybrid_mode_hard_fails(tmp_path: Path) -> None:
    """v2.40.2 — hybrid is no longer silently routed to auto. Real run with
    --probe-mode=hybrid must exit 1 with a message naming v2.41 as the
    landing release.

    We patch _classify_phase so the eligibility + plan-build short-circuits
    without invoking identify_interesting_clickables.py. subprocess.run is
    patched defensively to ensure no Gemini binary is fired even on regress.
    """
    phase = _copy_fixture(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location("spawn_recursive_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class _FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    fake_classification = [{
        "element_class": "mutation_button",
        "selector": "button#x",
        "view": "/admin",
        "resource": "topup",
        "selector_hash": "h1",
    }]

    import io
    import contextlib
    captured_err = io.StringIO()
    captured_out = io.StringIO()
    rc: int | None = None
    with patch.object(mod, "_classify_phase", return_value=fake_classification), \
         patch.object(mod.subprocess, "run", return_value=_FakeCompleted()):
        with contextlib.redirect_stderr(captured_err), \
             contextlib.redirect_stdout(captured_out):
            try:
                rc = mod.main([
                    "--phase-dir", str(phase),
                    "--mode", "light",
                    "--probe-mode", "hybrid",
                    "--non-interactive",
                    "--target-env", "sandbox",
                ])
            except SystemExit as exc:
                rc = int(exc.code) if exc.code is not None else 0

    err = captured_err.getvalue()
    assert rc == 1, f"expected exit 1, got {rc}; stderr={err}"
    assert "Hybrid mode is not yet implemented" in err, (
        f"expected hard-fail message, stderr was: {err}"
    )
    assert "v2.41" in err, (
        f"hard-fail message must point to v2.41 landing release, stderr was: {err}"
    )


# ---------------------------------------------------------------------------
# Test 4: actual auto/manual split — DEFERRED to v2.41 (fallback is a stub)
# ---------------------------------------------------------------------------
def test_hybrid_splits_auto_lenses_from_manual_lenses(tmp_path: Path) -> None:
    """Future: hybrid spawns auto_lenses workers + writes manual_lenses prompts.

    Currently hybrid runs full auto. Skipped until the per-lens router lands
    in v2.41; the test stays in tree as a regression hook.
    """
    pytest.skip(
        "hybrid per-lens routing (auto vs manual) not yet wired — see "
        "scripts/spawn_recursive_probe.py:main hybrid branch."
    )


# ---------------------------------------------------------------------------
# Test 5: goal back-flow merges both groups — DEFERRED (depends on Test 4)
# ---------------------------------------------------------------------------
def test_hybrid_goal_back_flow_merges_auto_and_manual_partials(tmp_path: Path) -> None:
    pytest.skip(
        "merge contract assertion deferred — gated on Test 4 hybrid router."
    )
