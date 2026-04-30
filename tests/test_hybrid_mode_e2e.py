"""Hybrid-mode E2E (Task 30, v2.40.0).

Hybrid contract per design doc:
  - lenses listed in vg.config recursive_probe.hybrid_routing.auto_lenses →
    spawn worker (auto)
  - lenses in hybrid_routing.manual_lenses → render prompt file (manual)
  - both groups merge in goal back-flow

State of the implementation as of v2.40:
  spawn_recursive_probe.py main() detects --probe-mode=hybrid but currently
  warns "hybrid probe-mode falls back to auto until Phase 1.D vg.config
  wiring lands" and runs the auto dispatcher for everything. The fallback
  path is what we lock in here so any regression to it surfaces immediately,
  and the "auto vs manual split" assertion is pytest.skip'd until v2.41.

We exercise this with --dry-run so no real Gemini fires.
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
# Test 3: hybrid currently falls back to auto — locks the documented behavior
# ---------------------------------------------------------------------------
def test_hybrid_falls_back_to_auto_with_warning(tmp_path: Path) -> None:
    """Until v2.41 hybrid wiring lands, hybrid mode emits the auto-fallback
    warning to stderr. This test locks in that contract; remove it when the
    real router replaces the fallback.

    We patch BOTH _classify_phase (to short-circuit the in-line subprocess
    call to identify_interesting_clickables.py) AND subprocess.run on the
    module's own subprocess reference (used by spawn_one_worker for the
    Gemini call).
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

    # Synthetic classification — one mutation_button so build_plan returns ≥1 entry.
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
    with patch.object(mod, "_classify_phase", return_value=fake_classification), \
         patch.object(mod.subprocess, "run", return_value=_FakeCompleted()):
        with contextlib.redirect_stderr(captured_err), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                mod.main([
                    "--phase-dir", str(phase),
                    "--mode", "light",
                    "--probe-mode", "hybrid",
                    "--non-interactive",
                    "--target-env", "sandbox",
                ])
            except SystemExit:
                pass

    err = captured_err.getvalue()
    assert "hybrid probe-mode falls back to auto" in err, (
        f"expected fallback warning, stderr was: {err}"
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
