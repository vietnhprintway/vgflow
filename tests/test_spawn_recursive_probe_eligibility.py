"""Eligibility check tests for spawn_recursive_probe.py (Task 18).

Verifies the 6-rule eligibility gate and the skip-evidence audit trail.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"


def _setup_phase(tmp_path: Path, *, profile: str = "feature", surface: str = "ui",
                 touched_resources: list[str] | None = None,
                 with_crud: bool = True, with_env: bool = True) -> Path:
    """Build a minimal eligible phase dir under ``tmp_path``."""
    if touched_resources is None:
        touched_resources = ["topup_requests"]

    p = tmp_path / "phase"
    p.mkdir()
    (p / ".phase-profile").write_text(
        f"phase_profile: {profile}\nsurface: {surface}\n",
        encoding="utf-8",
    )
    if with_crud:
        (p / "CRUD-SURFACES.md").write_text(
            "# Resources\n\n"
            "```json\n"
            '{"resources": [{"name": "topup_requests", "scope": "admin"}]}\n'
            "```\n",
            encoding="utf-8",
        )
    if with_env:
        (p / "ENV-CONTRACT.md").write_text(
            "```yaml\n"
            "disposable_seed_data: true\n"
            "third_party_stubs:\n"
            "  payment: stubbed\n"
            "  email: stubbed\n"
            "```\n",
            encoding="utf-8",
        )
    (p / "SUMMARY.md").write_text(
        "```yaml\n"
        f"touched_resources:\n  - {touched_resources[0]}\n"
        "```\n",
        encoding="utf-8",
    )
    # No scan-*.json needed for dry-run eligibility-only checks.
    return p


def _run(phase_dir: Path, *extra: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--phase-dir", str(phase_dir),
         "--dry-run", "--json", *extra],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    return json.loads(r.stdout)


def test_eligibility_passes(tmp_path: Path) -> None:
    p = _setup_phase(tmp_path)
    out = _run(p)
    assert out["eligibility"]["passed"] is True, out["eligibility"]
    assert out["eligibility"]["reasons"] == []
    # Skip evidence must NOT be written when eligibility passes.
    assert not (p / ".recursive-probe-skipped.yaml").exists()


def test_eligibility_fails_docs_profile(tmp_path: Path) -> None:
    p = _setup_phase(tmp_path, profile="docs")
    out = _run(p)
    assert out["eligibility"]["passed"] is False
    assert any("phase_profile" in r for r in out["eligibility"]["reasons"])
    skip_yaml = p / ".recursive-probe-skipped.yaml"
    assert skip_yaml.is_file()
    data = yaml.safe_load(skip_yaml.read_text(encoding="utf-8"))
    assert data["via_override"] is False
    assert any("phase_profile" in r for r in data["reasons"])


def test_eligibility_fails_visual_only_surface(tmp_path: Path) -> None:
    """Rule 5: NOT visual-only — surface 'visual' must skip."""
    p = _setup_phase(tmp_path, surface="visual")
    out = _run(p)
    assert out["eligibility"]["passed"] is False
    assert any("surface" in r for r in out["eligibility"]["reasons"])


def test_eligibility_fails_no_crud_surfaces(tmp_path: Path) -> None:
    """Rule 3: CRUD-SURFACES has resources."""
    p = _setup_phase(tmp_path, with_crud=False)
    out = _run(p)
    assert out["eligibility"]["passed"] is False
    assert any("CRUD-SURFACES" in r for r in out["eligibility"]["reasons"])


def test_eligibility_fails_missing_env_contract(tmp_path: Path) -> None:
    """Rule 6: ENV-CONTRACT.md disposable seed + stubs."""
    p = _setup_phase(tmp_path, with_env=False)
    out = _run(p)
    assert out["eligibility"]["passed"] is False
    assert any("ENV-CONTRACT" in r for r in out["eligibility"]["reasons"])


def test_override_logs_skip_with_reason(tmp_path: Path) -> None:
    """--skip-recursive-probe='reason' triggers OVERRIDE skip + audit YAML."""
    p = _setup_phase(tmp_path)
    out = _run(p, "--skip-recursive-probe", "manual deferral until v2.41")
    assert out["eligibility"]["passed"] is False
    assert out["eligibility"]["skipped_via_override"] is True
    skip_yaml = p / ".recursive-probe-skipped.yaml"
    assert skip_yaml.is_file()
    data = yaml.safe_load(skip_yaml.read_text(encoding="utf-8"))
    assert data["via_override"] is True
    assert "manual deferral" in " ".join(data["reasons"])
