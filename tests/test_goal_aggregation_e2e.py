"""Goal aggregation + dedupe E2E (Task 28, v2.40.0).

Validates aggregate_recursive_goals.py against two synthetic fixtures:

  - goal-dedupe-50-rows: 50 elements all sharing the same canonical key
    must collapse to exactly 1 main entry, 0 overflow.
  - goal-explosion-200: 200 distinct canonical keys exercise the per-mode
    cap envelope:
        light cap=50       → 50 main, 150 overflow
        deep cap=150       → 150 main, 50 overflow
        exhaustive cap=400 → 200 main, 0 overflow

Fixtures are minimal stub directories on disk; the partials are written into
``tmp_path/runs/`` per test so the canonical aggregator script reads them
exactly the way Phase 2b-2.5 workers do in production. No subprocess Gemini.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "aggregate_recursive_goals.py"
FIX_DEDUPE = REPO_ROOT / "tests" / "fixtures" / "goal-dedupe-50-rows"
FIX_EXPLOSION = REPO_ROOT / "tests" / "fixtures" / "goal-explosion-200"


# ---------------------------------------------------------------------------
# Fixture builders — emit goals-*.partial.yaml under tmp_path/runs/
# ---------------------------------------------------------------------------
def _write_partial(runs_dir: Path, name: str, entries: list[dict]) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / name).write_text(yaml.safe_dump(entries), encoding="utf-8")


def _build_50_same_class_partials(runs_dir: Path) -> None:
    """50 worker-partial entries, all collapsing to one canonical key.

    Same view + selector_hash + action_semantic + lens + resource +
    assertion_type → identical hash. We split them across 5 partial files
    of 10 entries each to mirror real multi-worker output.
    """
    base = {
        "view": "/admin/users",
        "element_class": "row_action",
        "selector_hash": "users_row_a",
        "lens": "lens-idor",
        "resource": "users",
        "assertion_type": "status_403",
        "action_semantic": "delete",
        "priority": "critical",
    }
    for w in range(5):
        _write_partial(
            runs_dir, f"goals-worker-{w}.partial.yaml",
            [dict(base) for _ in range(10)],
        )


def _build_200_distinct_partials(runs_dir: Path) -> None:
    """200 distinct canonical keys spread across 4 worker partial files."""
    chunk = 50
    for w in range(4):
        entries = []
        for i in range(chunk):
            idx = w * chunk + i
            entries.append({
                "view": f"/admin/v{idx}",
                "element_class": "row_action",
                "selector_hash": f"sel_{idx:04d}",
                "lens": "lens-idor",
                "resource": f"resource_{idx}",
                "assertion_type": f"assert_{idx % 7}",
                "action_semantic": "delete",
                "priority": "high",
            })
        _write_partial(runs_dir, f"goals-worker-{w}.partial.yaml", entries)


def _run_aggregator(phase_dir: Path, mode: str) -> tuple[Path, Path, str]:
    """Run aggregate_recursive_goals.py and return (output, overflow, stdout)."""
    output = phase_dir / "TEST-GOALS-DISCOVERED.md"
    overflow = phase_dir / "recursive-goals-overflow.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--phase-dir", str(phase_dir),
         "--mode", mode,
         "--output", str(output),
         "--overflow", str(overflow)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    return output, overflow, r.stdout


# ---------------------------------------------------------------------------
# Fixture sanity tests (verify the fixture dirs were created on disk)
# ---------------------------------------------------------------------------
def test_fixture_dirs_present():
    """Fixture directory placeholders exist (README only — partials emitted at runtime)."""
    assert FIX_DEDUPE.is_dir()
    assert FIX_EXPLOSION.is_dir()
    assert (FIX_DEDUPE / "README.md").is_file()
    assert (FIX_EXPLOSION / "README.md").is_file()


# ---------------------------------------------------------------------------
# Test 1: 50 elements same behavior class → 1 goal entry, 0 overflow
# ---------------------------------------------------------------------------
def test_50_rows_same_class_dedupes_to_one(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _build_50_same_class_partials(runs_dir)

    output, overflow, stdout = _run_aggregator(tmp_path, "light")

    text = output.read_text(encoding="utf-8")
    assert text.count("G-RECURSE-") == 1, f"expected 1 entry, got:\n{text}"

    payload = json.loads(overflow.read_text(encoding="utf-8"))
    assert payload["total"] == 1
    assert payload["in_main"] == 1
    assert payload["goals"] == []  # 0 overflow

    # stdout summary should reflect the single deduped goal.
    assert "1 unique goals" in stdout
    assert "0 -> overflow" in stdout


# ---------------------------------------------------------------------------
# Test 2: 200 distinct → light cap split (50 main + 150 overflow)
# ---------------------------------------------------------------------------
def test_200_distinct_light_mode_50_main_150_overflow(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _build_200_distinct_partials(runs_dir)

    output, overflow, _ = _run_aggregator(tmp_path, "light")

    text = output.read_text(encoding="utf-8")
    main_count = text.count("G-RECURSE-")
    assert main_count == 50, f"expected 50 main entries, got {main_count}"

    payload = json.loads(overflow.read_text(encoding="utf-8"))
    assert payload["total"] == 200
    assert payload["in_main"] == 50
    assert len(payload["goals"]) == 150
    assert payload["mode"] == "light"
    assert payload["cap"] == 50


# ---------------------------------------------------------------------------
# Test 3: 200 distinct → exhaustive cap (200 main, 0 overflow)
# ---------------------------------------------------------------------------
def test_200_distinct_exhaustive_mode_no_overflow(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _build_200_distinct_partials(runs_dir)

    output, overflow, _ = _run_aggregator(tmp_path, "exhaustive")

    text = output.read_text(encoding="utf-8")
    main_count = text.count("G-RECURSE-")
    assert main_count == 200, f"expected 200 main entries, got {main_count}"

    payload = json.loads(overflow.read_text(encoding="utf-8"))
    assert payload["total"] == 200
    assert payload["in_main"] == 200
    assert payload["goals"] == []
    assert payload["cap"] == 400


# ---------------------------------------------------------------------------
# Test 4: 200 distinct → deep mode (150 main + 50 overflow)
# ---------------------------------------------------------------------------
def test_200_distinct_deep_mode_split(tmp_path: Path) -> None:
    """Bonus coverage of the middle deep cap envelope."""
    runs_dir = tmp_path / "runs"
    _build_200_distinct_partials(runs_dir)

    output, overflow, _ = _run_aggregator(tmp_path, "deep")

    main_count = output.read_text(encoding="utf-8").count("G-RECURSE-")
    assert main_count == 150

    payload = json.loads(overflow.read_text(encoding="utf-8"))
    assert payload["in_main"] == 150
    assert len(payload["goals"]) == 50
    assert payload["cap"] == 150
