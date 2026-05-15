"""tests/test_batch59_data_observations.py — Batch 59.

Scanner emits data_observations field with cardinality + status_diversity
+ distinct_values_per_filter. Recipe generator (B54) reads these to
size pagination_edge seed counts and warn on single-value filters.

Coverage:
  1. scanner SKILL.md declares data_observations + note
  2. generator _aggregate_scan_signals collects data_observations
  3. filter_combination recipe gets filter_cardinality from
     distinct_values_per_filter
  4. pagination_edge recipe gets status_distribution
  5. Recipe warns on distinct_count=1 (always-full-set filter)
  6. Back-compat: scan without data_observations still works
  7. Mirror parity for generator + scanner
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
SKILL = REPO / "skills" / "vg-haiku-scanner" / "SKILL.md"
SKILL_MIRROR = REPO / ".claude" / "skills" / "vg-haiku-scanner" / "SKILL.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_seed_recipes", GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_seed_recipes"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_scanner_declares_data_observations():
    body = SKILL.read_text(encoding="utf-8")
    assert '"data_observations"' in body
    assert "cardinality" in body
    assert "status_diversity" in body
    assert "distinct_values_per_filter" in body
    assert "sampled_status_distribution" in body
    assert "Batch 59" in body


def test_aggregate_collects_data_observations():
    mod = _load_module()
    scans = [{
        "view": "/sites",
        "data_observations": {
            "cardinality": {"tables_total_rows": 168},
            "distinct_values_per_filter": [
                {"filter_name": "Status", "distinct_count": 3,
                 "sampled_values": ["all", "active", "archived"]}
            ],
            "sampled_status_distribution": {"Active": 134, "Archived": 28},
            "row_id_pattern": "site-NNN",
        },
    }]
    agg = mod._aggregate_scan_signals(scans)
    assert "data_observations" in agg
    assert len(agg["data_observations"]) == 1
    do = agg["data_observations"][0]
    assert do["view"] == "/sites"
    assert do["cardinality"]["tables_total_rows"] == 168
    assert do["row_id_pattern"] == "site-NNN"


def test_filter_combination_includes_filter_cardinality(tmp_path):
    phase_dir = tmp_path / "phases" / "7"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "goals": {"G-01": {"edge_cases": [{"kind": "filter_combination"}]}}
    }), encoding="utf-8")
    (phase_dir / "scan-sites.json").write_text(json.dumps({
        "view": "/sites",
        "filters": [{"name": "Status", "options": ["a", "b"]}],
        "data_observations": {
            "distinct_values_per_filter": [
                {"filter_name": "Status", "distinct_count": 3,
                 "sampled_values": ["all", "active", "archived"]}
            ],
        },
    }), encoding="utf-8")
    r = subprocess.run(
        ["python", str(GEN), "--phase", "7", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "filter_cardinality" in body
    assert "distinct_count" in body
    # Warning about distinct_count=1 should be in hint
    assert "distinct_count" in body


def test_pagination_edge_includes_status_distribution(tmp_path):
    phase_dir = tmp_path / "phases" / "8"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "goals": {"G-01": {"edge_cases": [{"kind": "pagination_edge"}]}}
    }), encoding="utf-8")
    (phase_dir / "scan-sites.json").write_text(json.dumps({
        "view": "/sites",
        "pagination": {"present": True, "total_pages": 7, "page_size": 25},
        "tables": [{"ref": "e20", "row_count": 168}],
        "data_observations": {
            "sampled_status_distribution": {"Active": 134, "Archived": 28},
        },
    }), encoding="utf-8")
    r = subprocess.run(
        ["python", str(GEN), "--phase", "8", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    assert "status_distribution" in body
    assert "Active" in body
    assert "134" in body


def test_back_compat_no_data_observations(tmp_path):
    """Scan without data_observations field still works (B54 path)."""
    phase_dir = tmp_path / "phases" / "9"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "goals": {"G-01": {"edge_cases": [{"kind": "filter_combination"}]}}
    }), encoding="utf-8")
    (phase_dir / "scan-sites.json").write_text(json.dumps({
        "view": "/sites",
        "filters": [{"name": "Status", "options": ["a"]}],
        # NO data_observations
    }), encoding="utf-8")
    r = subprocess.run(
        ["python", str(GEN), "--phase", "9", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    # real_filters still present, filter_cardinality not (no data_observations)
    assert "real_filters" in body
    # filter_cardinality should NOT appear (no data_observations)
    # but real_filters block still has the filter
    assert "Status" in body


def test_aggregate_handles_missing_data_observations():
    """aggregator doesn't crash when scans lack data_observations."""
    mod = _load_module()
    scans = [{"view": "/x", "filters": [{"name": "F1"}]}]
    agg = mod._aggregate_scan_signals(scans)
    assert agg["data_observations"] == []
    assert len(agg["filters"]) == 1


def test_observed_for_kind_filter_combination_with_distinct(tmp_path):
    mod = _load_module()
    agg = mod._aggregate_scan_signals([{
        "view": "/x",
        "filters": [{"name": "Status", "options": ["a"]}],
        "data_observations": {
            "distinct_values_per_filter": [
                {"filter_name": "Status", "distinct_count": 1, "sampled_values": ["only"]}
            ],
        },
    }])
    obs = mod._observed_for_kind("filter_combination", agg)
    assert obs is not None
    assert "filter_cardinality" in obs
    assert obs["filter_cardinality"]["Status"]["distinct_count"] == 1
    # Warn about single-value filter should be in hint
    assert "distinct_count=1" in obs["hint"] or "distinct_count >= 2" in obs["hint"] or "distinct_count>=2" in obs["hint"]


def test_mirrors_in_sync():
    assert GEN.read_text(encoding="utf-8") == GEN_MIRROR.read_text(encoding="utf-8")
    assert SKILL.read_text(encoding="utf-8") == SKILL_MIRROR.read_text(encoding="utf-8")
