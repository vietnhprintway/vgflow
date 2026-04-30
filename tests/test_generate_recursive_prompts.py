"""Manual-mode template renderer tests for generate_recursive_prompts.py
(Task 20 + v2.40.2 per-tool subdir tests).
"""
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


# ---------------------------------------------------------------------------
# Existing default-behavior tests (re-pointed at per-tool subdirs).
# ---------------------------------------------------------------------------
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
    # Both tool subdirs exist by default.
    for tool in ("gemini", "codex"):
        assert (prompts_dir / tool / "MANIFEST.md").is_file()
        assert (prompts_dir / tool / "lens-idor-delete-42.md").is_file()
        assert (prompts_dir / tool / "lens-modal-state-approve-modal.md").is_file()
        assert (prompts_dir / tool / "EXPECTED-OUTPUTS.md").is_file()


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
    manifest = (tmp_path / "recursive-prompts" / "gemini" / "MANIFEST.md").read_text(encoding="utf-8")
    assert "lens-bfla" in manifest
    assert "lens-csrf" in manifest
    assert "Probe 1" in manifest and "Probe 2" in manifest


def test_per_lens_file_references_lens_path_and_no_unrendered_vars(tmp_path: Path) -> None:
    plan = [
        {"element": {"element_class": "mutation_button", "selector": "btn-x",
                     "view": "/admin", "resource": "topup"},
         "lens": "lens-bfla"},
    ]
    r = _run(tmp_path, plan)
    assert r.returncode == 0, r.stderr
    body = (tmp_path / "recursive-prompts" / "gemini" / "lens-bfla-btn-x.md").read_text(encoding="utf-8")
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
    expected = (tmp_path / "recursive-prompts" / "gemini" / "EXPECTED-OUTPUTS.md").read_text(encoding="utf-8")
    # Two recursive-*.json paths, one per probe.
    assert expected.count("recursive-") >= 2
    assert "lens-idor" in expected
    assert "lens-modal-state" in expected


def test_empty_plan_still_produces_manifest(tmp_path: Path) -> None:
    r = _run(tmp_path, [])
    assert r.returncode == 0, r.stderr
    for tool in ("gemini", "codex"):
        assert (tmp_path / "recursive-prompts" / tool / "MANIFEST.md").is_file()
        assert (tmp_path / "recursive-prompts" / tool / "EXPECTED-OUTPUTS.md").is_file()


# ---------------------------------------------------------------------------
# v2.40.2 — per-tool subdir + short paste file + tool-specific token env.
# ---------------------------------------------------------------------------
_BASIC_PLAN = [
    {"element": {"element_class": "row_action", "selector": "delete-42",
                 "view": "/admin/topup", "resource": "topup", "role": "admin"},
     "lens": "lens-idor"},
]


def test_generates_per_tool_subdirs(tmp_path: Path) -> None:
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "gemini,codex")
    assert r.returncode == 0, r.stderr
    prompts = tmp_path / "recursive-prompts"
    assert (prompts / "gemini" / "MANIFEST.md").is_file()
    assert (prompts / "gemini" / "lens-idor-delete-42.md").is_file()
    assert (prompts / "gemini" / "EXPECTED-OUTPUTS.md").is_file()
    assert (prompts / "codex" / "MANIFEST.md").is_file()
    assert (prompts / "codex" / "lens-idor-delete-42.md").is_file()
    assert (prompts / "codex" / "EXPECTED-OUTPUTS.md").is_file()


def test_per_probe_file_is_short_and_refs_lens(tmp_path: Path) -> None:
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "gemini")
    assert r.returncode == 0, r.stderr
    probe = (tmp_path / "recursive-prompts" / "gemini" / "lens-idor-delete-42.md").read_text(encoding="utf-8")
    # Short paste target — << 30 lines (current generic template was ~200).
    line_count = len(probe.splitlines())
    assert line_count < 30, f"per-probe file too long: {line_count} lines"
    # References the canonical lens prompt file by path.
    assert "commands/vg/_shared/lens-prompts/lens-idor.md" in probe
    # Tool-specific token env is named in body.
    assert "GEMINI_PROBE_TOKEN" in probe


def test_codex_uses_codex_token_env(tmp_path: Path) -> None:
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "codex,gemini")
    assert r.returncode == 0, r.stderr
    codex_probe = (tmp_path / "recursive-prompts" / "codex" / "lens-idor-delete-42.md").read_text(encoding="utf-8")
    assert "CODEX_PROBE_TOKEN" in codex_probe
    assert "GEMINI_PROBE_TOKEN" not in codex_probe
    gemini_probe = (tmp_path / "recursive-prompts" / "gemini" / "lens-idor-delete-42.md").read_text(encoding="utf-8")
    assert "GEMINI_PROBE_TOKEN" in gemini_probe
    assert "CODEX_PROBE_TOKEN" not in gemini_probe


def test_output_path_per_tool(tmp_path: Path) -> None:
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "gemini,codex")
    assert r.returncode == 0, r.stderr
    gemini_probe = (tmp_path / "recursive-prompts" / "gemini" / "lens-idor-delete-42.md").read_text(encoding="utf-8")
    assert "runs/gemini/" in gemini_probe
    assert "runs/codex/" not in gemini_probe
    codex_probe = (tmp_path / "recursive-prompts" / "codex" / "lens-idor-delete-42.md").read_text(encoding="utf-8")
    assert "runs/codex/" in codex_probe
    assert "runs/gemini/" not in codex_probe


def test_tools_flag_single_subdir(tmp_path: Path) -> None:
    """--tools gemini → only gemini subdir exists; codex subdir absent."""
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "gemini")
    assert r.returncode == 0, r.stderr
    prompts = tmp_path / "recursive-prompts"
    assert (prompts / "gemini").is_dir()
    assert not (prompts / "codex").exists(), (
        "codex subdir must NOT be written when --tools gemini"
    )


def test_invalid_tool_rejected(tmp_path: Path) -> None:
    r = _run(tmp_path, _BASIC_PLAN, "--tools", "unknownai")
    assert r.returncode == 2, r.stdout
    assert "unknown tool" in r.stderr.lower()


def test_default_tools_writes_both_subdirs(tmp_path: Path) -> None:
    """Without --tools flag, default writes both gemini and codex subdirs."""
    r = _run(tmp_path, _BASIC_PLAN)
    assert r.returncode == 0, r.stderr
    prompts = tmp_path / "recursive-prompts"
    assert (prompts / "gemini").is_dir()
    assert (prompts / "codex").is_dir()


def test_manifest_references_verify_with_tool_flag(tmp_path: Path) -> None:
    """Each tool's MANIFEST mentions --tool <tool> for the verifier."""
    r = _run(tmp_path, _BASIC_PLAN)
    assert r.returncode == 0, r.stderr
    gemini_manifest = (tmp_path / "recursive-prompts" / "gemini" / "MANIFEST.md").read_text(encoding="utf-8")
    assert "--tool gemini" in gemini_manifest
    codex_manifest = (tmp_path / "recursive-prompts" / "codex" / "MANIFEST.md").read_text(encoding="utf-8")
    assert "--tool codex" in codex_manifest
