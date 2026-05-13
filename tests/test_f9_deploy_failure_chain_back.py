"""tests/test_f9_deploy_failure_chain_back.py — F9 deploy failure recovery."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
EXEC_MD = REPO / "commands" / "vg" / "_shared" / "deploy" / "execute.md"
CLOSE_MD = REPO / "commands" / "vg" / "_shared" / "deploy" / "persist-and-close.md"


def test_deploy_failure_updates_pipeline_state():
    body = EXEC_MD.read_text(encoding="utf-8") + CLOSE_MD.read_text(encoding="utf-8")
    assert "deploy_status" in body or "deploy.failed" in body or "deploy_failed" in body, (
        "F9: deploy must set pipeline_step or deploy_status='failed' in "
        "PIPELINE-STATE on failure (not silent stay at build-complete)"
    )


def test_deploy_failure_emits_event():
    body = EXEC_MD.read_text(encoding="utf-8") + CLOSE_MD.read_text(encoding="utf-8")
    assert "deploy.failed" in body or "deploy_failure" in body, (
        "F9: deploy failure must emit deploy.failed event for telemetry "
        "+ accept-time cross-check"
    )


def test_deploy_failure_sets_next_command():
    body = CLOSE_MD.read_text(encoding="utf-8")
    assert "next_command" in body and "/vg:deploy" in body, (
        "F9: deploy failure must set PIPELINE-STATE.next_command='/vg:deploy --resume' "
        "so auto-chain rerun is unambiguous"
    )
