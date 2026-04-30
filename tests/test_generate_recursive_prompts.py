"""Manual-mode template renderer tests for generate_recursive_prompts.py (Task 20)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_recursive_prompts.py"


def _run(phase_dir: Path, plan: list[dict], *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase_dir),
         "--plan-json", json.dumps(plan), *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def test_generates_manifest_and_per_lens_files(tmp_path: Path) -> None:
    plan = [
        {"element": {"element_class": "row_action", "selector": "delete-42",
                     "view": "/admin/topup", "resource": "topup"},
         "lens": "lens-idor"},
        {"element": {"element_class": "modal_trigger", "selector": "approve-modal",
                     "view": "/admin/topup", "resource": "topup"},
         "lens": "lens-modal-state"},
    ]
    r = _run(tmp_path, plan)
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    prompts_dir = tmp_path / "recursive-prompts"
    assert (prompts_dir / "MANIFEST.md").is_file()
    assert (prompts_dir / "lens-idor-delete-42.md").is_file()
    assert (prompts_dir / "lens-modal-state-approve-modal.md").is_file()
    assert (prompts_dir / "EXPECTED-OUTPUTS.md").is_file()


def test_manifest_lists_every_probe(tmp_path: Path) -> None:
    plan = [
        {"element": {"element_class": "mutation_button", "selector": "btn-1",
                     "view": "/admin", "resource": "topup"},
         "lens": "lens-bfla"},
        {"element": {"element_class": "form_trigger", "selector": "form-x",
                     "view": "/admin", "resource": "topup"},
         "lens": "lens-csrf"},
    ]
    r = _run(tmp_path, plan)
    assert r.returncode == 0, r.stderr
    manifest = (tmp_path / "recursive-prompts" / "MANIFEST.md").read_text(encoding="utf-8")
    assert "lens-bfla" in manifest
    assert "lens-csrf" in manifest
    assert "Probe 1" in manifest and "Probe 2" in manifest


def test_per_lens_file_contains_context_block(tmp_path: Path) -> None:
    plan = [
        {"element": {"element_class": "mutation_button", "selector": "btn-x",
                     "view": "/admin", "resource": "topup"},
         "lens": "lens-bfla"},
    ]
    r = _run(tmp_path, plan)
    assert r.returncode == 0, r.stderr
    body = (tmp_path / "recursive-prompts" / "lens-bfla-btn-x.md").read_text(encoding="utf-8")
    assert "lens-bfla" in body
    assert "btn-x" in body
    assert "/admin" in body
    # No unrendered template variables should leak.
    assert "{{" not in body and "}}" not in body


def test_expected_outputs_lists_all_run_paths(tmp_path: Path) -> None:
    plan = [
        {"element": {"element_class": "row_action", "selector": "delete-42",
                     "view": "/admin/topup", "resource": "topup"},
         "lens": "lens-idor"},
        {"element": {"element_class": "modal_trigger", "selector": "approve-modal",
                     "view": "/admin/topup", "resource": "topup"},
         "lens": "lens-modal-state"},
    ]
    r = _run(tmp_path, plan)
    assert r.returncode == 0, r.stderr
    expected = (tmp_path / "recursive-prompts" / "EXPECTED-OUTPUTS.md").read_text(encoding="utf-8")
    # Two recursive-*.json paths, one per probe.
    assert expected.count("recursive-") >= 2
    assert "lens-idor" in expected
    assert "lens-modal-state" in expected


def test_empty_plan_still_produces_manifest(tmp_path: Path) -> None:
    r = _run(tmp_path, [])
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "recursive-prompts" / "MANIFEST.md").is_file()
    assert (tmp_path / "recursive-prompts" / "EXPECTED-OUTPUTS.md").is_file()
