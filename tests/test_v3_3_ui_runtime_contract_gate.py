"""v3.3.0 — #173 Stage 3: UI-RUNTIME-CONTRACT pre-test-gate tests.

Coverage:
1. validator exists + content checks (token gate + spec-count gate paths)
2. canonical/mirror byte-identity
3. pre-test-gate.md wires the validator into STEP 6.5
4. happy-path: tokens present in CSS + spec count met → PASS (rc=0)
5. token missing → BLOCK (rc=1)
6. spec count too low → BLOCK (rc=1)
7. contract missing → PASS skip (rc=0)
8. skip_reason populated → PASS skip (rc=0)
9. severity=warn downgrades BLOCK → WARN (rc=0)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validators" / "verify-ui-runtime-contract.py"
VALIDATOR_MIRROR = REPO_ROOT / ".claude" / "scripts" / "validators" / "verify-ui-runtime-contract.py"
PRE_TEST_GATE_CANON = REPO_ROOT / "commands" / "vg" / "_shared" / "build" / "pre-test-gate.md"
PRE_TEST_GATE_MIRROR = REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "build" / "pre-test-gate.md"


# ── content checks ────────────────────────────────────────────────────────


def test_validator_exists_and_has_main():
    assert VALIDATOR.is_file()
    body = VALIDATOR.read_text(encoding="utf-8")
    assert "def main()" in body
    assert "check_tokens" in body
    assert "check_spec_count" in body
    assert "DEFAULT_CSS_GLOBS" in body
    assert "DEFAULT_SPEC_GLOBS" in body


def test_validator_mirror_byte_identity():
    assert VALIDATOR.read_bytes() == VALIDATOR_MIRROR.read_bytes()


def test_pre_test_gate_wires_validator():
    assert PRE_TEST_GATE_CANON.is_file()
    body = PRE_TEST_GATE_CANON.read_text(encoding="utf-8")
    assert "verify-ui-runtime-contract.py" in body
    assert "--skip-ui-runtime-contract" in body
    assert "build.ui_runtime_contract_blocked" in body
    assert "build.ui_runtime_contract_passed" in body
    assert PRE_TEST_GATE_CANON.read_bytes() == PRE_TEST_GATE_MIRROR.read_bytes()


# ── functional tests ──────────────────────────────────────────────────────


def _write_phase(tmp_path: Path, contract: dict) -> Path:
    phase = tmp_path / "phase-99"
    phase.mkdir()
    (phase / "UI-RUNTIME-CONTRACT.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )
    return phase


def _run(phase_dir: Path, repo_root: Path, extra: list[str] | None = None) -> tuple[int, str]:
    args = [
        sys.executable, str(VALIDATOR),
        "--phase-dir", str(phase_dir),
        "--repo-root", str(repo_root),
        "--json",
    ]
    if extra:
        args.extend(extra)
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def _full_contract(tokens: list[dict], min_specs: int) -> dict:
    return {
        "version": "1",
        "phase_id": "phase-99",
        "generated_at": "2026-05-11T00:00:00Z",
        "source_artifacts": {},
        "required_tailwind_tokens": tokens,
        "first_viewport_surfaces": [],
        "route_inventory": [],
        "env_contract": {"status": "present"},
        "min_spec_count": {"count": min_specs, "source": "test"},
        "acceptance_criteria": ["test"],
        "skip_reason": None,
    }


def _make_css(repo_root: Path, content: str) -> Path:
    css_dir = repo_root / "apps" / "web" / "dist"
    css_dir.mkdir(parents=True)
    css = css_dir / "bundle.css"
    css.write_text(content, encoding="utf-8")
    return css


def _make_spec(repo_root: Path, n: int) -> None:
    spec_dir = repo_root / "apps" / "web" / "tests"
    spec_dir.mkdir(parents=True)
    for i in range(n):
        (spec_dir / f"f{i}.spec.ts").write_text(f"// spec {i}\n", encoding="utf-8")


def test_happy_path_pass(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(
        tokens=[
            {"class_name": "brand-primary", "evidence_source": "x", "occurrences": 1},
            {"class_name": "bg-brand-500", "evidence_source": "x", "occurrences": 1},
        ],
        min_specs=2,
    )
    phase = _write_phase(repo, contract)
    _make_css(repo, ".brand-primary { color: red; } .bg-brand-500 { background: blue; }")
    _make_spec(repo, 3)

    rc, out = _run(phase, repo)
    assert rc == 0, f"rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    assert payload["verdict"] == "PASS", payload


def test_token_missing_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(
        tokens=[
            {"class_name": "brand-primary", "evidence_source": "x", "occurrences": 1},
            {"class_name": "bg-brand-500", "evidence_source": "x", "occurrences": 1},
            {"class_name": "text-brand-700", "evidence_source": "x", "occurrences": 1},
        ],
        min_specs=0,
    )
    phase = _write_phase(repo, contract)
    # CSS only has 2 of 3 tokens
    _make_css(repo, ".brand-primary {} .bg-brand-500 {}")

    rc, out = _run(phase, repo)
    assert rc == 1, f"expected BLOCK, got rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    assert payload["verdict"] == "BLOCK"
    types = [e["type"] for e in payload["evidence"]]
    assert "ui_runtime_contract_token_missing" in types


def test_no_css_bundle_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(
        tokens=[{"class_name": "brand-primary", "evidence_source": "x", "occurrences": 1}],
        min_specs=0,
    )
    phase = _write_phase(repo, contract)
    # No CSS at all → BLOCK
    rc, out = _run(phase, repo)
    assert rc == 1
    payload = json.loads(out.strip().split("\n")[0])
    types = [e["type"] for e in payload["evidence"]]
    assert "ui_runtime_contract_no_css_bundle" in types


def test_spec_count_low_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(tokens=[], min_specs=3)
    phase = _write_phase(repo, contract)
    _make_spec(repo, 1)  # only 1 spec, need 3

    rc, out = _run(phase, repo)
    assert rc == 1, f"expected BLOCK, got rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    types = [e["type"] for e in payload["evidence"]]
    assert "ui_runtime_contract_spec_count_low" in types


def test_contract_missing_skips(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    phase = repo / "phase-99"
    phase.mkdir()
    # No UI-RUNTIME-CONTRACT.json
    rc, out = _run(phase, repo)
    assert rc == 0, f"missing contract should skip with PASS, got rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    assert payload["verdict"] == "PASS"
    types = [e["type"] for e in payload["evidence"]]
    assert "ui_runtime_contract_missing" in types


def test_skip_reason_skips(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(
        tokens=[{"class_name": "brand-primary", "evidence_source": "x", "occurrences": 1}],
        min_specs=3,
    )
    contract["skip_reason"] = "backend-only profile"
    phase = _write_phase(repo, contract)
    # No CSS, no specs — but skip_reason should short-circuit
    rc, out = _run(phase, repo)
    assert rc == 0, f"skip_reason should skip with PASS, got rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    assert payload["verdict"] == "PASS"
    types = [e["type"] for e in payload["evidence"]]
    assert "ui_runtime_contract_skipped" in types


def test_severity_warn_downgrades_block(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    contract = _full_contract(
        tokens=[{"class_name": "brand-missing", "evidence_source": "x", "occurrences": 1}],
        min_specs=0,
    )
    phase = _write_phase(repo, contract)
    _make_css(repo, "/* nothing */")

    rc, out = _run(phase, repo, extra=["--severity", "warn"])
    # BLOCK conditions present but severity=warn → exit 0 with verdict=WARN
    assert rc == 0, f"severity=warn should not exit 1, got rc={rc}, out={out}"
    payload = json.loads(out.strip().split("\n")[0])
    assert payload["verdict"] == "WARN"
