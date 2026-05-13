"""Batch 5 task 5: failure path must surface trace + video paths in SANDBOX-TEST.md."""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "commands" / "vg" / "_shared" / "test" / "regression-security.md"


def test_failure_block_mentions_trace():
    body = CANONICAL.read_text(encoding="utf-8")
    assert "trace.zip" in body or "trace-" in body, (
        "Batch 5: 5e_regression failure handler must surface trace.zip path"
    )


def test_failure_block_mentions_video():
    body = CANONICAL.read_text(encoding="utf-8")
    assert "video" in body.lower() and "test-results" in body
