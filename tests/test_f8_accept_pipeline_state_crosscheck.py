"""tests/test_f8_accept_pipeline_state_crosscheck.py — F8 accept cross-check."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO / "commands" / "vg" / "_shared" / "accept" / "preflight.md"


def test_accept_reads_pipeline_state_next_command():
    body = PREFLIGHT.read_text(encoding="utf-8")
    assert "next_command" in body, (
        "F8: accept/preflight must read PIPELINE-STATE.next_command (written by "
        "test/close.md F1 fix) and cross-check it matches /vg:accept invocation"
    )


def test_accept_warns_on_routing_mismatch():
    body = PREFLIGHT.read_text(encoding="utf-8")
    assert "vg:accept" in body and "/vg:" in body, (
        "F8: cross-check logic must compare current command (/vg:accept) "
        "against PIPELINE-STATE.next_command. Mismatch = WARN (test verdict "
        "may not point here)."
    )
