"""v2.68.0 C6 — Min-budget floor."""
import importlib.util
import sys
import json
from pathlib import Path
import pytest


def _load_tracker():
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "vg_budget_tracker",
        repo_root / "scripts" / "vg-budget-tracker.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_budget_tracker_module_exists():
    p = Path("scripts/vg-budget-tracker.py")
    assert p.exists(), "vg-budget-tracker.py missing (v2.68.0 C6)"


def test_track_token_usage(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"

    mod.track(state_file, "phase-test", input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "phase-test" in state["phases"]
    phase_data = state["phases"]["phase-test"]
    assert phase_data["total_input_tokens"] == 1000
    assert phase_data["total_output_tokens"] == 500


def test_abort_when_budget_exceeded(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"

    # Simulate: floor set at $0.01, tokens cost > floor
    mod.track(state_file, "phase-test", input_tokens=1_000_000, output_tokens=500_000, model="claude-opus-4-7")

    over_budget, total_cost = mod.check_budget(state_file, "phase-test", floor_usd=0.01)
    assert over_budget is True
    assert total_cost > 0.01


def test_under_budget_passes(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"

    mod.track(state_file, "phase-test", input_tokens=100, output_tokens=50, model="claude-haiku-4-5-20251001")

    over_budget, total_cost = mod.check_budget(state_file, "phase-test", floor_usd=10.00)
    assert over_budget is False


def test_config_template_documents_floor():
    body = Path("vg.config.template.md").read_text(encoding="utf-8")
    assert "min_budget_floor_usd" in body or "budget_floor" in body.lower(), \
        "vg.config.template.md must document min_budget_floor field"
