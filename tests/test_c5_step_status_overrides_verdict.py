"""tests/test_c5_step_status_overrides_verdict.py — Batch 9 C5 gap.

Verifies test/close.md verdict computation ingests step-status ledger.
Any step BLOCK/FAIL must override goal-only PASS math.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "scripts" / "step-status-ledger.py"
LEDGER_MIR = REPO / ".claude" / "scripts" / "step-status-ledger.py"
CLOSE = REPO / "commands" / "vg" / "_shared" / "test" / "close.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_ledger_script_exists():
    assert LEDGER.is_file(), "C5: step-status-ledger.py must ship in scripts/"


def test_ledger_write_creates_json(tmp_path):
    """Calling ledger writer with --step + --status must produce/update
    .test-step-status.json with the entry."""
    phase_dir = tmp_path / "phase"
    phase_dir.mkdir()
    r = subprocess.run(
        [sys.executable, str(LEDGER), "--phase-dir", str(phase_dir),
         "--step", "5b_runtime_contract_verify",
         "--status", "BLOCK",
         "--reason", "endpoint /api/refund returned 404"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    ledger_file = phase_dir / ".test-step-status.json"
    assert ledger_file.is_file()
    data = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert "steps" in data
    assert "5b_runtime_contract_verify" in data["steps"]
    assert data["steps"]["5b_runtime_contract_verify"]["status"] == "BLOCK"


def test_close_md_verdict_reads_ledger():
    """close.md verdict computation must reference .test-step-status.json
    (or equivalent ledger) so step-level FAIL overrides goal-only PASS."""
    body = _read(CLOSE)
    assert ".test-step-status.json" in body, (
        "C5: close.md verdict computation must read step-status ledger to "
        "ensure step BLOCK/FAIL overrides goal-only PASS"
    )


def test_close_md_verdict_logic_includes_step_block_override():
    """close.md verdict computation must include logic that downgrades
    verdict when any step status is BLOCK or FAIL."""
    body = _read(CLOSE)
    # Look for the override pattern — step_status BLOCK/FAIL forces FAILED
    has_override = any(
        marker in body for marker in [
            "step_status_block", "step BLOCK overrides", "step_blocks > 0",
            "step.get('status') in", "BLOCK', 'FAIL'", "STEP_BLOCK_OVERRIDE",
        ]
    )
    assert has_override, (
        "C5: close.md must include logic mapping any step ledger entry "
        "with status=BLOCK or FAIL to override goal-only PASS. Look for "
        "step_status_block or similar verdict-override hook."
    )


def test_mirror_byte_identical():
    if LEDGER_MIR.is_file():
        assert _read(LEDGER) == _read(LEDGER_MIR)
