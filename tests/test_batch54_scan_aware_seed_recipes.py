"""tests/test_batch54_scan_aware_seed_recipes.py — Batch 54.

generate-seed-recipes.py now consumes phase_dir/scan-*.json files
(Haiku scanner output) and attaches observed_state per recipe so AI
follow-up has real filter names + row counts instead of inventing them.

Coverage:
  1. Generator runs WITHOUT scans — recipes still emit (back-compat).
  2. Generator runs WITH scans — filter_combination gets real_filters,
     pagination_edge gets real_pagination/real_row_counts.
  3. observed_state block renders in SEED-RECIPE.md as YAML.
  4. Module-level helpers (_load_scans, _aggregate_scan_signals,
     _observed_for_kind) function correctly in isolation.
  5. Mirror in .claude/scripts stays in sync.
"""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEN = REPO / "scripts" / "generate-seed-recipes.py"
GEN_MIRROR = REPO / ".claude" / "scripts" / "generate-seed-recipes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_seed_recipes", GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_seed_recipes"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _write_lifecycle(phase_dir: Path, goals: dict) -> None:
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(
        json.dumps({"goals": goals}), encoding="utf-8"
    )


def _write_scan(phase_dir: Path, view: str, payload: dict) -> None:
    slug = view.replace("/", "-").strip("-") or "root"
    (phase_dir / f"scan-{slug}.json").write_text(
        json.dumps({"view": view, **payload}), encoding="utf-8"
    )


def test_back_compat_no_scans(tmp_path):
    """Phase dir without scan-*.json still produces recipes."""
    phase_dir = tmp_path / "phases" / "7"
    phase_dir.mkdir(parents=True)
    _write_lifecycle(phase_dir, {"G-01": {"edge_cases": [{"kind": "boundary"}]}})
    r = subprocess.run(
        ["python", str(GEN), "--phase", "7", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "G-01-b1" in body
    assert "observed_state" not in body  # no scans → no augmentation


def test_filter_combination_picks_up_real_filters(tmp_path):
    phase_dir = tmp_path / "phases" / "8"
    phase_dir.mkdir(parents=True)
    _write_lifecycle(phase_dir, {
        "G-01": {"edge_cases": [{"kind": "filter_combination"}]}
    })
    _write_scan(phase_dir, "/sites", {
        "filters": [
            {"name": "Status", "kind": "select",
             "options": ["all", "active", "archived"], "near_table_ref": "e20"},
            {"name": "Owner", "kind": "combobox",
             "options": None, "near_table_ref": "e20"},
        ],
    })
    r = subprocess.run(
        ["python", str(GEN), "--phase", "8", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "observed_state:" in body
    assert "Status" in body
    assert "Owner" in body
    assert "active" in body  # real options from scan


def test_pagination_edge_uses_observed_pagination(tmp_path):
    phase_dir = tmp_path / "phases" / "9"
    phase_dir.mkdir(parents=True)
    _write_lifecycle(phase_dir, {
        "G-02": {"edge_cases": [{"kind": "pagination_edge"}]}
    })
    _write_scan(phase_dir, "/users", {
        "pagination": {"present": True, "total_pages": 7,
                       "current_page": 1, "page_size": 25},
        "tables": [{"ref": "e30", "row_count": 168}],
    })
    r = subprocess.run(
        ["python", str(GEN), "--phase", "9", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "real_pagination" in body
    assert "total_pages" in body and "7" in body
    assert "page_size" in body and "25" in body
    assert "168" in body  # row_count from table


def test_not_found_404_uses_error_state_4xx(tmp_path):
    phase_dir = tmp_path / "phases" / "10"
    phase_dir.mkdir(parents=True)
    _write_lifecycle(phase_dir, {
        "G-03": {"negative_specs": [{"kind": "not_found_404"}]}
    })
    _write_scan(phase_dir, "/orders", {
        "state_observations": {
            "error_state_4xx": {
                "observed": True,
                "expected_status": 404,
                "actual_status": 404,
                "trigger": "/orders/99999999-fake-id-probe",
            },
        },
    })
    r = subprocess.run(
        ["python", str(GEN), "--phase", "10", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "error_state_4xx" in body
    assert "fake-id-probe" in body


def test_observed_state_block_yaml_indentation(tmp_path):
    """observed_state must render as indented YAML inside ```yaml block."""
    phase_dir = tmp_path / "phases" / "11"
    phase_dir.mkdir(parents=True)
    _write_lifecycle(phase_dir, {
        "G-01": {"edge_cases": [{"kind": "filter_combination"}]}
    })
    _write_scan(phase_dir, "/x", {
        "filters": [{"name": "Status", "options": ["a", "b"]}]
    })
    r = subprocess.run(
        ["python", str(GEN), "--phase", "11", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    # observed_state line followed by indented JSON inside YAML block
    assert "observed_state:" in body
    obs_idx = body.find("observed_state:")
    snippet = body[obs_idx:obs_idx + 500]
    assert "  " in snippet  # indentation
    assert "real_filters" in snippet


def test_load_scans_module_helper(tmp_path):
    mod = _load_module()
    phase_dir = tmp_path / "phases" / "x"
    phase_dir.mkdir(parents=True)
    _write_scan(phase_dir, "/a", {"filters": [{"name": "F1"}]})
    _write_scan(phase_dir, "/b", {"filters": [{"name": "F2"}]})
    scans = mod._load_scans(phase_dir)
    assert len(scans) == 2
    views = sorted(s.get("view") for s in scans)
    assert views == ["/a", "/b"]


def test_aggregate_scan_signals_module_helper():
    mod = _load_module()
    scans = [
        {"view": "/v",
         "filters": [{"name": "Status", "options": ["a", "b"]}],
         "pagination": {"present": True, "total_pages": 3, "page_size": 20},
         "tables": [{"ref": "t1", "row_count": 42}],
         "state_observations": {
             "empty_state": {"observed": True, "trigger": "search 'zzz'",
                             "message_text": "No results"},
         },
         "search": [{"placeholder": "Search...", "debounce_ms_observed": 300}],
        }
    ]
    agg = mod._aggregate_scan_signals(scans)
    assert agg["views_scanned"] == 1
    assert len(agg["filters"]) == 1
    assert agg["filters"][0]["name"] == "Status"
    assert len(agg["pagination"]) == 1
    assert agg["pagination"][0]["total_pages"] == 3
    assert len(agg["row_counts"]) == 1
    assert agg["empty_state"] is not None
    assert agg["empty_state"]["message_text"] == "No results"
    assert len(agg["search"]) == 1


def test_observed_for_kind_module_helper():
    mod = _load_module()
    agg = mod._aggregate_scan_signals([{
        "view": "/x",
        "filters": [{"name": "F1", "options": ["a"]}],
        "pagination": [],
        "tables": [{"ref": "t1", "row_count": 10}],
    }])
    # filter_combination → real_filters
    o = mod._observed_for_kind("filter_combination", agg)
    assert o is not None and "real_filters" in o
    # pagination_edge → real_row_counts (no pagination)
    o = mod._observed_for_kind("pagination_edge", agg)
    assert o is not None and "real_row_counts" in o
    # rate_limit_429 → None (no scan signal)
    assert mod._observed_for_kind("rate_limit_429", agg) is None


def test_mirror_in_sync():
    assert GEN.read_text(encoding="utf-8") == GEN_MIRROR.read_text(encoding="utf-8")
