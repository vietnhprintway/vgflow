"""Manual-mode E2E (Task 30, v2.40.0 + v2.40.2 per-tool layout).

End-to-end check that --probe-mode=manual:
  1. Issues 0 spawn_one_worker calls (no Gemini subprocess).
  2. Calls generate_recursive_prompts.py to write MANIFEST.md +
     per-lens prompt files + EXPECTED-OUTPUTS.md under
     <phase>/recursive-prompts/<tool>/ (per-tool subdirs, v2.40.2).
  3. verify_manual_run_artifacts.py BLOCKs (returncode 1) when the
     EXPECTED-OUTPUTS paths are missing on disk.
  4. verify_manual_run_artifacts.py passes (returncode 0) once those
     v3-compliant artifacts are written.

No real LLM call — manual mode is deterministic Python rendering.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPAWN_SCRIPT = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_manual_run_artifacts.py"
SMOKE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def _copy_fixture(tmp_path: Path) -> Path:
    dst = tmp_path / "phase"
    shutil.copytree(SMOKE_FIXTURE, dst)
    return dst


def _run_spawn_manual(phase: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SPAWN_SCRIPT),
         "--phase-dir", str(phase),
         "--mode", "light",
         "--probe-mode", "manual",
         "--non-interactive",
         "--target-env", "sandbox"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _run_verify(phase: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT),
         "--phase-dir", str(phase), "--json", *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# Test 1: manual mode emits all expected artifacts under per-tool subdirs
# ---------------------------------------------------------------------------
def test_manual_mode_emits_manifest_and_expected_outputs(tmp_path: Path) -> None:
    phase = _copy_fixture(tmp_path)
    r = _run_spawn_manual(phase)
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"

    prompts_dir = phase / "recursive-prompts"
    # v2.40.2: per-tool subdirs (gemini + codex by default).
    for tool in ("gemini", "codex"):
        tool_dir = prompts_dir / tool
        assert (tool_dir / "MANIFEST.md").is_file(), (
            f"missing MANIFEST.md under {tool_dir}"
        )
        assert (tool_dir / "EXPECTED-OUTPUTS.md").is_file(), (
            f"missing EXPECTED-OUTPUTS.md under {tool_dir}"
        )
        per_lens = list(tool_dir.glob("lens-*.md"))
        assert per_lens, f"no per-lens prompts written under {tool_dir}"

    # No runs/<tool>/ probe artifacts because manual mode does not spawn
    # workers; verify_manual_run_artifacts will catch that as BLOCK below.
    runs_dir = phase / "runs"
    if runs_dir.is_dir():
        recursive_jsons = list(runs_dir.rglob("recursive-*.json"))
        assert not recursive_jsons, (
            f"manual mode must not spawn workers, found: {recursive_jsons}"
        )


# ---------------------------------------------------------------------------
# Test 2: verify_manual_run_artifacts BLOCKs on missing artifacts
# ---------------------------------------------------------------------------
def test_verify_blocks_on_missing_artifacts(tmp_path: Path) -> None:
    phase = _copy_fixture(tmp_path)
    spawn_result = _run_spawn_manual(phase)
    assert spawn_result.returncode == 0

    # --tool gemini scope: artifacts under runs/gemini/ are absent → BLOCK.
    verify = _run_verify(phase, "--tool", "gemini")
    assert verify.returncode == 1, (
        f"verifier should BLOCK on missing artifacts: rc={verify.returncode} "
        f"stderr={verify.stderr}"
    )
    report = json.loads(verify.stdout)
    assert report["blocked"], "payload.blocked should be True"
    # First report covers gemini.
    g_report = report["reports"][0]
    assert g_report["missing"], "expected missing[] to be non-empty"
    assert g_report["ok"] == []


# ---------------------------------------------------------------------------
# Test 3: verify passes once v3-compliant artifacts are written per tool
# ---------------------------------------------------------------------------
def test_verify_passes_with_v3_artifacts(tmp_path: Path) -> None:
    phase = _copy_fixture(tmp_path)
    _run_spawn_manual(phase)

    # Use the gemini per-tool EXPECTED-OUTPUTS.md as our reference.
    expected_md = phase / "recursive-prompts" / "gemini" / "EXPECTED-OUTPUTS.md"
    assert expected_md.is_file(), f"missing {expected_md}"
    text = expected_md.read_text(encoding="utf-8")
    rels = re.findall(r"`([^`]+\.json)`", text)
    assert rels, "EXPECTED-OUTPUTS.md should reference .json paths"

    # Write a v3-compliant skeleton for every expected output (under runs/gemini/).
    for rel in rels:
        full = phase / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(json.dumps({
            "lens": rel.split("recursive-")[-1].split("-")[0] or "lens-stub",
            "steps": [{"action": "navigate", "evidence_ref": "ev-1"}],
            "network_log": [{"method": "GET", "path": "/x", "status": 200}],
            "verdict": "pass",
        }), encoding="utf-8")

    verify = _run_verify(phase, "--tool", "gemini")
    assert verify.returncode == 0, (
        f"verifier should pass with v3 artifacts: stderr={verify.stderr}\n"
        f"stdout={verify.stdout}"
    )
    report = json.loads(verify.stdout)
    assert report["blocked"] is False
    g_report = report["reports"][0]
    assert g_report["missing"] == []
    assert g_report["invalid"] == []
    assert len(g_report["ok"]) == len(rels)
