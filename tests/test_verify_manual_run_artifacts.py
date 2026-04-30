"""Manual-run artifact verifier tests for verify_manual_run_artifacts.py
(Task 21 + v2.40.2 per-tool flag tests).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_manual_run_artifacts.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _write_expected(phase_dir: Path, paths: list[str], *,
                    tool: str | None = None) -> None:
    """Drop a minimal EXPECTED-OUTPUTS.md.

    When ``tool`` is None, writes the legacy single-dir location
    (``recursive-prompts/EXPECTED-OUTPUTS.md``). Otherwise writes the
    per-tool subdir location (``recursive-prompts/<tool>/EXPECTED-OUTPUTS.md``).
    """
    out = phase_dir / "recursive-prompts"
    if tool:
        out = out / tool
    out.mkdir(parents=True, exist_ok=True)
    body = ["# EXPECTED OUTPUTS — recursive manual run\n"]
    for i, p in enumerate(paths, start=1):
        body.append(
            f"- {i}. lens=`lens-x` element_class=`mutation_button` "
            f"selector=`btn-{i}` → `{p}`"
        )
    (out / "EXPECTED-OUTPUTS.md").write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_artifact(phase_dir: Path, rel_path: str, *,
                    valid: bool = True) -> None:
    """Write a v3-shaped run artifact at <phase_dir>/<rel_path>."""
    target = phase_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if valid:
        body = {
            "lens": "lens-x",
            "element": {"selector": "btn-1", "view": "/admin"},
            "steps": [{"action": "click", "evidence_ref": "screenshot-1.png"}],
            "network_log": [{"method": "POST", "url": "/api/x", "status": 200}],
            "verdict": "pass",
            "notes": "",
        }
    else:
        body = {"oops": "missing required v3 keys"}
    target.write_text(json.dumps(body, indent=2), encoding="utf-8")


def _run(phase_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase_dir), *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# Legacy-path tests (preserved via fallback when no per-tool subdir exists).
# ---------------------------------------------------------------------------
def test_verify_passes_when_all_artifacts_match(tmp_path: Path) -> None:
    paths = [
        "runs/manual/recursive-lens-idor-btn-1-d1.json",
        "runs/manual/recursive-lens-bfla-btn-2-d1.json",
    ]
    _write_expected(tmp_path, paths)  # legacy single-dir layout
    for p in paths:
        _write_artifact(tmp_path, p, valid=True)
    # Use --tool gemini to hit the legacy fallback path.
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    assert "OK" in r.stdout or "passed" in r.stdout.lower()


def test_verify_blocks_when_missing(tmp_path: Path) -> None:
    paths = [
        "runs/manual/recursive-lens-idor-btn-1-d1.json",
        "runs/manual/recursive-lens-bfla-btn-2-d1.json",
        "runs/manual/recursive-lens-csrf-btn-3-d1.json",
    ]
    _write_expected(tmp_path, paths)
    # Only 2 of 3 written.
    _write_artifact(tmp_path, paths[0], valid=True)
    _write_artifact(tmp_path, paths[1], valid=True)
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode != 0, f"expected non-zero exit, got 0\nstdout={r.stdout}"
    combined = (r.stdout + r.stderr).lower()
    assert "missing" in combined or "block" in combined


def test_verify_blocks_when_invalid_schema(tmp_path: Path) -> None:
    paths = ["runs/manual/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, paths)
    _write_artifact(tmp_path, paths[0], valid=False)  # missing required keys
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode != 0, r.stdout
    combined = (r.stdout + r.stderr).lower()
    assert "schema" in combined or "invalid" in combined or "block" in combined


def test_verify_blocks_when_expected_outputs_missing(tmp_path: Path) -> None:
    """No EXPECTED-OUTPUTS.md → cannot verify, must BLOCK."""
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode != 0, r.stdout
    combined = (r.stdout + r.stderr).lower()
    assert "expected-outputs" in combined or "not found" in combined


def test_verify_handles_non_json_artifact(tmp_path: Path) -> None:
    paths = ["runs/manual/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, paths)
    target = tmp_path / paths[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not json at all", encoding="utf-8")
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode != 0, r.stdout


# ---------------------------------------------------------------------------
# v2.40.2 — per-tool flag tests.
# ---------------------------------------------------------------------------
def test_verify_passes_per_tool_gemini(tmp_path: Path) -> None:
    """runs/gemini/* with valid v3 artifacts + per-tool EXPECTED → PASS."""
    paths = ["runs/gemini/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, paths, tool="gemini")
    for p in paths:
        _write_artifact(tmp_path, p, valid=True)
    r = _run(tmp_path, "--tool", "gemini")
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    assert "OK" in r.stdout or "passed" in r.stdout.lower()


def test_verify_blocks_per_tool_missing_codex(tmp_path: Path) -> None:
    """gemini complete, codex empty → --tool codex BLOCKS."""
    gemini_paths = ["runs/gemini/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, gemini_paths, tool="gemini")
    for p in gemini_paths:
        _write_artifact(tmp_path, p, valid=True)
    # No codex EXPECTED-OUTPUTS.md, no codex artifacts.
    r = _run(tmp_path, "--tool", "codex")
    assert r.returncode != 0, f"expected BLOCK, got 0\nstdout={r.stdout}"
    combined = (r.stdout + r.stderr).lower()
    assert "block" in combined or "not found" in combined


def test_verify_both_requires_both_complete(tmp_path: Path) -> None:
    """--tool both with only gemini complete → BLOCK."""
    gemini_paths = ["runs/gemini/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, gemini_paths, tool="gemini")
    for p in gemini_paths:
        _write_artifact(tmp_path, p, valid=True)
    # codex side missing entirely.
    r = _run(tmp_path, "--tool", "both")
    assert r.returncode != 0, r.stdout


def test_verify_both_passes_when_both_complete(tmp_path: Path) -> None:
    gemini_paths = ["runs/gemini/recursive-lens-idor-btn-1-d1.json"]
    codex_paths = ["runs/codex/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, gemini_paths, tool="gemini")
    _write_expected(tmp_path, codex_paths, tool="codex")
    for p in gemini_paths + codex_paths:
        _write_artifact(tmp_path, p, valid=True)
    r = _run(tmp_path, "--tool", "both")
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"


def test_verify_default_is_both(tmp_path: Path) -> None:
    """No --tool flag → defaults to 'both' (matches help text)."""
    gemini_paths = ["runs/gemini/recursive-lens-idor-btn-1-d1.json"]
    _write_expected(tmp_path, gemini_paths, tool="gemini")
    for p in gemini_paths:
        _write_artifact(tmp_path, p, valid=True)
    # Codex side missing → expect BLOCK because default = both.
    r = _run(tmp_path)
    assert r.returncode != 0, r.stdout
