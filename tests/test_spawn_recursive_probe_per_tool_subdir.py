"""Per-tool subdir isolation: runs/{gemini,codex,claude}/ (Task 26h).

Test the path layer (output paths + aggregator glob), not the actual subprocess
spawn — we set --dry-run + check the spawn function constructs the right
output_path.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPAWN = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"
AGG = REPO_ROOT / "scripts" / "aggregate_recursive_goals.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def _load_spawn_module():
    spec = importlib.util.spec_from_file_location("spawn_recursive_probe", SPAWN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spawn_recursive_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_tool_for_model_mapping() -> None:
    mod = _load_spawn_module()
    assert mod.tool_for_model("gemini-2.5-flash") == "gemini"
    assert mod.tool_for_model("gemini-1.5-pro") == "gemini"
    assert mod.tool_for_model("claude-3-5-sonnet-20241022") == "claude"
    assert mod.tool_for_model("claude-haiku-4-5") == "claude"
    assert mod.tool_for_model("codex-mini") == "codex"
    assert mod.tool_for_model("o4-mini") == "codex"
    assert mod.tool_for_model("unknown-model") == "gemini"  # safe default


def test_spawn_one_worker_writes_to_per_tool_subdir(tmp_path: Path) -> None:
    """spawn_one_worker should compose runs/<tool>/<basename>.json paths.

    We can't actually run gemini in tests; instead we patch FileNotFoundError
    on the binary by inspecting the returned dict's output_path.
    """
    mod = _load_spawn_module()
    phase = tmp_path / "phase"
    phase.mkdir()
    entry = {
        "element": {
            "selector": "button#x", "selector_hash": "ab12",
            "view": "/", "resource": "r", "element_class": "row_action",
        },
        "lens": "lens-idor",
    }
    res = mod.spawn_one_worker(entry, phase, mcp_slot="playwright1",
                                model="gemini-2.5-flash", timeout=1)
    out = Path(res["output_path"])
    # Path layout must be runs/<tool>/...; tool=gemini for the gemini model.
    assert "runs" in out.parts and "gemini" in out.parts, out


def test_aggregator_globs_across_tool_subdirs(tmp_path: Path) -> None:
    """aggregate_recursive_goals.py must read goals-*.partial.yaml under
    runs/<tool>/ subdirs (NOT just runs/)."""
    phase = tmp_path / "phase"
    phase.mkdir()
    runs = phase / "runs"
    (runs / "gemini").mkdir(parents=True)
    (runs / "codex").mkdir(parents=True)
    (runs / "gemini" / "goals-w1.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/a", "selector_hash": "h1", "action_semantic": "delete",
        "lens": "lens-idor", "resource": "r", "assertion_type": "forbidden",
    }]), encoding="utf-8")
    (runs / "codex" / "goals-w2.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/b", "selector_hash": "h2", "action_semantic": "create",
        "lens": "lens-csrf", "resource": "r", "assertion_type": "forbidden",
    }]), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(AGG), "--phase-dir", str(phase), "--mode", "light"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body = (phase / "TEST-GOALS-DISCOVERED.md").read_text(encoding="utf-8")
    assert "lens-idor" in body, body
    assert "lens-csrf" in body, body


def test_aggregator_still_reads_legacy_runs_root(tmp_path: Path) -> None:
    """Backward-compat: pre-26h artifacts written directly to runs/ keep working."""
    phase = tmp_path / "phase"
    phase.mkdir()
    runs = phase / "runs"
    runs.mkdir()
    (runs / "goals-legacy.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/legacy", "selector_hash": "old1",
        "action_semantic": "view",
        "lens": "lens-info-disclosure", "resource": "r",
        "assertion_type": "noinfo",
    }]), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(AGG), "--phase-dir", str(phase), "--mode", "light"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body = (phase / "TEST-GOALS-DISCOVERED.md").read_text(encoding="utf-8")
    assert "lens-info-disclosure" in body
