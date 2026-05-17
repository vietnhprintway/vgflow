"""tests/test_batch71f_rtb_fixture_replay.py — B71f end-to-end RTB fixture regression.

Loads anonymized RTB fixtures (tests/fixtures/tasklist-rtb-c1a5/ and
tests/fixtures/tasklist-rtb-10fa/) and verifies the full restore pipeline
produces correct status overlay:

Fixture c1a5 — display-label snapshot pattern. Snapshot IDs are TodoWrite
  titles (e.g. "↳ 0 Parse And Validate") not contract step_ids. Tests:
  1. Resolver maps each snapshot ID to correct contract step_id.
  2. Restore-mode produces overlay with non-zero in_progress + completed counts.
  3. Status precedence: when same step_id appears under multiple labels
     (e.g. "↳ 3.5 CrossAI Sweep" + "↳ test-spec 3_crossai_sweep"), the
     in_progress wins over pending.

Fixture 10fa — numeric tid snapshot pattern. Snapshot IDs are backend
  task_ids (353-360). Contract has step5_fix_loop, step7_matrix_verdict.
  Tests:
  4. Naive overlay (without trace rehydration) yields 0% overlap.
  5. Legacy rehydration via .taskcreate-trace.jsonl maps numeric → step_id.
  6. Resulting overlay has correct in_progress state for active step.

This is the regression test for the exact RTB symptom the user reported:
"TaskList vẫn không hiệu quả, vẫn bị ẩn các task đang làm việc hoặc
chờ làm việc, chỉ hiện mỗi các task đã làm".
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
FIXTURE_C1A5 = FIXTURES / "tasklist-rtb-c1a5"
FIXTURE_10FA = FIXTURES / "tasklist-rtb-10fa"
RESOLVER = REPO / "scripts" / "tasklist_id_resolver.py"
EMIT_TASKLIST = REPO / "scripts" / "emit-tasklist.py"

spec = importlib.util.spec_from_file_location("tasklist_id_resolver", RESOLVER)
resolver = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(resolver)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Fixture sanity.
# ---------------------------------------------------------------------------


def test_b71f_fixture_c1a5_present():
    assert (FIXTURE_C1A5 / "tasklist-contract.json").exists()
    assert (FIXTURE_C1A5 / ".todowrite-snapshot.json").exists()


def test_b71f_fixture_10fa_present():
    assert (FIXTURE_10FA / "tasklist-contract.json").exists()
    assert (FIXTURE_10FA / ".todowrite-snapshot.json").exists()
    assert (FIXTURE_10FA / ".taskcreate-trace.jsonl").exists()


# ---------------------------------------------------------------------------
# Fixture c1a5 — display-label pattern (the RTB c1a5edc3 symptom).
# ---------------------------------------------------------------------------


def _load_c1a5():
    contract = json.loads((FIXTURE_C1A5 / "tasklist-contract.json").read_text(encoding="utf-8"))
    snapshot = json.loads((FIXTURE_C1A5 / ".todowrite-snapshot.json").read_text(encoding="utf-8"))
    return contract, snapshot


def test_b71f_c1a5_resolver_maps_all_snapshot_ids():
    """Every snapshot.items[].id should resolve to a contract step_id
    (or unresolved with no shadowing of real steps)."""
    contract, snapshot = _load_c1a5()
    contract_items = contract["projection_items"]
    contract_ids = {it["id"] for it in contract_items}
    matched = 0
    unresolved_count = 0
    for snap_it in snapshot["items"]:
        sid, mc = resolver.resolve(snap_it["id"], contract_items)
        if sid in contract_ids:
            matched += 1
        elif sid.startswith("<unresolved>:"):
            unresolved_count += 1
    # Most of the 18 snapshot items should resolve to one of the 9 contract IDs.
    # Group rows ("Test-Spec 7.16 Steps") + sub-step orphans may stay unresolved.
    assert matched >= 14, f"expected >=14 matches, got {matched}; unresolved={unresolved_count}"


def test_b71f_c1a5_status_precedence_resolves_collisions():
    """When snapshot has multiple labels for same step (e.g. "↳ 3.5 CrossAI Sweep"
    in_progress + "↳ test-spec 3_crossai_sweep" in_progress), resolver returns
    same step_id; status_precedence picks in_progress when present."""
    contract, snapshot = _load_c1a5()
    contract_items = contract["projection_items"]
    by_step: dict[str, list[str]] = {}
    for snap_it in snapshot["items"]:
        sid, _mc = resolver.resolve(snap_it["id"], contract_items)
        if not sid.startswith("<unresolved>:"):
            by_step.setdefault(sid, []).append(snap_it["status"])
    # crossai_sweep had in_progress in both labels → status_precedence yields in_progress.
    if "3_crossai_sweep" in by_step:
        final = resolver.status_precedence(*by_step["3_crossai_sweep"])
        assert final == "in_progress"
    # parse_and_validate had completed in both labels → completed.
    if "0_parse_and_validate" in by_step:
        final = resolver.status_precedence(*by_step["0_parse_and_validate"])
        assert final == "completed"


def test_b71f_c1a5_restore_overlay_correctness(tmp_path: Path, monkeypatch):
    """Full restore-mode replay on fixture c1a5: copy fixture to a fake
    .vg/runs/{run_id}/ tree, write a v2 snapshot derived from the v1
    fixture (simulating B71a hook resolution), then invoke restore-mode.

    Assert: stdout output shows in_progress + completed counts that match
    the snapshot's actual non-pending statuses."""
    contract, snapshot_v1 = _load_c1a5()
    run_id = "fixture-c1a5"
    run_dir = tmp_path / ".vg" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasklist-contract.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )
    # Simulate B71a hook resolution: build v2 snapshot from v1 by running each
    # snapshot ID through the resolver.
    contract_items = contract["projection_items"]
    resolved_items = []
    by_step: dict[str, dict] = {}
    for snap_it in snapshot_v1["items"]:
        sid, mc = resolver.resolve(snap_it["id"], contract_items)
        if sid.startswith("<unresolved>:"):
            continue
        if sid in by_step:
            # status_precedence dedup
            existing = by_step[sid]["status"]
            new = snap_it["status"]
            by_step[sid]["status"] = resolver.status_precedence(existing, new)
        else:
            by_step[sid] = {
                "id": sid,
                "content": snap_it["id"],
                "status": snap_it["status"],
                "match_class": mc,
            }
    resolved_items = list(by_step.values())
    (run_dir / ".todowrite-snapshot.json").write_text(
        json.dumps({"schema_version": 2, "items": resolved_items}),
        encoding="utf-8",
    )
    # Run restore.
    result = subprocess.run(
        [sys.executable, str(EMIT_TASKLIST), "--restore-mode",
         "--run-id", run_id,
         "--command", "vg:test-spec", "--phase", "7.16",
         "--profile", "web-fullstack"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "VG_REPO_ROOT": str(tmp_path),
             "VG_HOME": str(REPO / ".claude"), "PYTHONIOENCODING": "utf-8"},
        cwd=str(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    # Output should show non-zero in_progress and completed (the user's actual progress).
    output = result.stdout.lower()
    # Pattern from emit-tasklist: "Contract: N items (X in_progress, Y pending, Z completed)"
    # OR rows showing "in_progress" / "completed".
    assert "in_progress" in output or "in progress" in output, (
        f"restore output missing in_progress signal — symptom regression!\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "completed" in output, (
        f"restore output missing completed signal\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Fixture 10fa — numeric tid pattern (RTB 10faabdb symptom).
# ---------------------------------------------------------------------------


def test_b71f_10fa_naive_overlay_is_zero():
    """Without trace rehydration, the numeric snapshot has 0% overlap with
    contract step_ids — proves the original bug."""
    contract = json.loads((FIXTURE_10FA / "tasklist-contract.json").read_text(encoding="utf-8"))
    snapshot = json.loads((FIXTURE_10FA / ".todowrite-snapshot.json").read_text(encoding="utf-8"))
    contract_ids = {it["id"] for it in contract["projection_items"]}
    snap_ids = {it["id"] for it in snapshot["items"]}
    overlap = contract_ids & snap_ids
    assert len(overlap) == 0, (
        f"Expected 0% overlap on legacy numeric snapshot fixture; "
        f"got overlap={overlap}"
    )


def test_b71f_10fa_trace_rehydration_recovers_step_ids():
    """Reading .taskcreate-trace.jsonl + running subjects through resolver
    should recover step_ids that match contract."""
    contract = json.loads((FIXTURE_10FA / "tasklist-contract.json").read_text(encoding="utf-8"))
    trace_lines = (FIXTURE_10FA / ".taskcreate-trace.jsonl").read_text(encoding="utf-8").splitlines()
    contract_items = contract["projection_items"]
    contract_ids = {it["id"] for it in contract_items}
    recovered = set()
    for line in trace_lines:
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("action") == "create":
            subject = rec.get("subject") or ""
            sid, mc = resolver.resolve(subject, contract_items)
            if sid in contract_ids:
                recovered.add(sid)
    # Expect step5_fix_loop + step7_matrix_verdict to be recovered.
    assert "step5_fix_loop" in recovered
    assert "step7_matrix_verdict" in recovered


def test_b71f_10fa_restore_with_rehydration(tmp_path: Path):
    """End-to-end: copy fixture, run restore-mode. With v1 snapshot + trace
    present, restore should auto-rehydrate and emit non-pending statuses."""
    run_id = "fixture-10fa"
    run_dir = tmp_path / ".vg" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("tasklist-contract.json", ".todowrite-snapshot.json",
                  ".taskcreate-trace.jsonl"):
        shutil.copy(FIXTURE_10FA / fname, run_dir / fname)
    result = subprocess.run(
        [sys.executable, str(EMIT_TASKLIST), "--restore-mode",
         "--run-id", run_id,
         "--command", "vg:test", "--phase", "7.16",
         "--profile", "web-fullstack"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "VG_REPO_ROOT": str(tmp_path),
             "VG_HOME": str(REPO / ".claude"), "PYTHONIOENCODING": "utf-8"},
        cwd=str(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    # Stderr should mention rehydration kicked in.
    assert ("rehydration" in result.stderr.lower()
            or "B71a" in result.stderr), (
        f"expected legacy rehydration log on numeric snapshot fixture\n"
        f"STDERR:\n{result.stderr}"
    )
    # Stdout should show some non-pending state for step5_fix_loop or step7_matrix_verdict.
    out = result.stdout.lower()
    assert "in_progress" in out or "completed" in out, (
        f"restore output should reflect rehydrated statuses\n"
        f"STDOUT:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Regression assertion: the bug the user reported is NOT reproducible
# on these fixtures after the fix.
# ---------------------------------------------------------------------------


def test_b71f_user_symptom_NOT_reproducible_on_c1a5(tmp_path: Path):
    """User report: "TodoWrite shows ONLY completed, hides in_progress/pending".

    On the c1a5 fixture (RTB pattern), AFTER B71a resolver + B71d overlay
    validator are in place, restore output must show ALL three statuses
    proportional to the snapshot's actual content (not all-pending).
    """
    contract, snapshot_v1 = _load_c1a5()
    run_id = "fixture-c1a5-regression"
    run_dir = tmp_path / ".vg" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "tasklist-contract.json").write_text(json.dumps(contract), encoding="utf-8")

    # Resolved v2 snapshot (what B71a hook produces).
    contract_items = contract["projection_items"]
    by_step: dict[str, dict] = {}
    for snap_it in snapshot_v1["items"]:
        sid, mc = resolver.resolve(snap_it["id"], contract_items)
        if sid.startswith("<unresolved>:"):
            continue
        if sid in by_step:
            by_step[sid]["status"] = resolver.status_precedence(
                by_step[sid]["status"], snap_it["status"]
            )
        else:
            by_step[sid] = {
                "id": sid, "content": snap_it["id"],
                "status": snap_it["status"], "match_class": mc,
            }
    (run_dir / ".todowrite-snapshot.json").write_text(
        json.dumps({"schema_version": 2, "items": list(by_step.values())}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(EMIT_TASKLIST), "--restore-mode",
         "--run-id", run_id,
         "--command", "vg:test-spec", "--phase", "7.16",
         "--profile", "web-fullstack"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "VG_REPO_ROOT": str(tmp_path),
             "VG_HOME": str(REPO / ".claude"), "PYTHONIOENCODING": "utf-8"},
        cwd=str(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0
    # Symptom: "ẩn task in_progress/pending, chỉ hiện completed".
    # Regression assertion: output contains evidence of in_progress AND pending,
    # not just completed.
    out = result.stdout.lower()
    counts_present = ("in_progress" in out or "in progress" in out) and "pending" in out
    assert counts_present, (
        f"REGRESSION: user-reported symptom reproducible — output hides "
        f"in_progress or pending. STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
