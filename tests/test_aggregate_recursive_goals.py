import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dedupe_collapses_same_behavior_class(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # 3 worker partials all same canonical key
    for i in range(3):
        (runs_dir / f"goals-worker-{i}.partial.yaml").write_text(yaml.safe_dump([{
            "view": "/x", "element_class": "row_action", "selector_hash": "abc12345",
            "lens": "lens-idor", "resource": "users", "assertion_type": "status_403",
            "priority": "critical", "action_semantic": "delete",
        }]))
    output = tmp_path / "TEST-GOALS-DISCOVERED.md"
    overflow = tmp_path / "recursive-goals-overflow.json"
    r = subprocess.run([
        sys.executable, "scripts/aggregate_recursive_goals.py",
        "--phase-dir", str(tmp_path), "--mode", "light",
        "--output", str(output), "--overflow", str(overflow),
    ], capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 0, f"stderr: {r.stderr}"
    text = output.read_text()
    assert text.count("G-RECURSE-") == 1, "Should dedupe to 1 entry"


def test_overflow_when_cap_exceeded(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # 60 distinct behavior classes in light mode (cap=50)
    partials = []
    for i in range(60):
        partials.append({
            "view": f"/v{i}", "element_class": "row_action",
            "selector_hash": f"hash{i:04d}", "lens": "lens-idor",
            "resource": f"r{i}", "assertion_type": "x", "priority": "high",
            "action_semantic": "delete",
        })
    (runs_dir / "goals-worker-0.partial.yaml").write_text(yaml.safe_dump(partials))
    output = tmp_path / "TEST-GOALS-DISCOVERED.md"
    overflow = tmp_path / "overflow.json"
    subprocess.run([
        sys.executable, "scripts/aggregate_recursive_goals.py",
        "--phase-dir", str(tmp_path), "--mode", "light",
        "--output", str(output), "--overflow", str(overflow),
    ], check=True, cwd=REPO_ROOT)
    main_count = output.read_text().count("G-RECURSE-")
    overflow_count = len(json.loads(overflow.read_text())["goals"])
    assert main_count == 50
    assert overflow_count == 10


def test_empty_runs_dir_succeeds_with_no_goals(tmp_path):
    """No partials -> exit 0, section emitted but empty."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    output = tmp_path / "TEST-GOALS-DISCOVERED.md"
    overflow = tmp_path / "overflow.json"
    r = subprocess.run([
        sys.executable, "scripts/aggregate_recursive_goals.py",
        "--phase-dir", str(tmp_path), "--mode", "light",
        "--output", str(output), "--overflow", str(overflow),
    ], capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 0
    overflow_data = json.loads(overflow.read_text())
    assert overflow_data["total"] == 0
    assert overflow_data["goals"] == []


def test_malformed_yaml_partial_skipped_with_warning(tmp_path):
    """Malformed partial logged + skipped, valid partials still aggregated."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "goals-bad.partial.yaml").write_text("invalid: yaml: [unclosed")
    (runs_dir / "goals-good.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/x", "element_class": "row_action", "selector_hash": "abc",
        "lens": "lens-idor", "resource": "users", "assertion_type": "x",
        "priority": "high", "action_semantic": "delete",
    }]))
    output = tmp_path / "TEST-GOALS-DISCOVERED.md"
    overflow = tmp_path / "overflow.json"
    r = subprocess.run([
        sys.executable, "scripts/aggregate_recursive_goals.py",
        "--phase-dir", str(tmp_path), "--mode", "light",
        "--output", str(output), "--overflow", str(overflow),
    ], capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 0
    assert "warning" in r.stderr.lower() or "malformed" in r.stderr.lower()
    assert output.read_text().count("G-RECURSE-") == 1  # only good partial counted


def test_section_replacement_preserves_manual_content_after_auto(tmp_path):
    """Manual section AFTER auto section must be preserved on re-run (I-1 fix)."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "goals-w0.partial.yaml").write_text(yaml.safe_dump([{
        "view": "/v1", "element_class": "row_action", "selector_hash": "h1",
        "lens": "lens-idor", "resource": "r1", "assertion_type": "x",
        "priority": "high", "action_semantic": "delete",
    }]))
    output = tmp_path / "TEST-GOALS-DISCOVERED.md"
    output.write_text(
        "# Test goals\n\n## Manual goals before\n- some manual goal\n\n"
        "## Auto-emitted recursive probe goals\n## G-RECURSE-old123456\n- old: data\n\n"
        "## Manual goals after\n- this should NOT be deleted\n"
    )
    overflow = tmp_path / "overflow.json"
    subprocess.run([
        sys.executable, "scripts/aggregate_recursive_goals.py",
        "--phase-dir", str(tmp_path), "--mode", "light",
        "--output", str(output), "--overflow", str(overflow),
    ], check=True, cwd=REPO_ROOT)
    text = output.read_text()
    assert "Manual goals before" in text  # before content preserved
    assert "Manual goals after" in text  # after content preserved (I-1 fix)
    assert "this should NOT be deleted" in text
    assert "G-RECURSE-old123456" not in text  # old auto content replaced
