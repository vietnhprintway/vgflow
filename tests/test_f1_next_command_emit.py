"""tests/test_f1_next_command_emit.py — F1 auto-chain next_command on all closes."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

CASES = [
    ("commands/vg/_shared/specs/write-and-commit.md", "/vg:scope"),
    ("commands/vg/_shared/scope/close.md", "/vg:blueprint"),
    ("commands/vg/_shared/blueprint/close.md", "/vg:build"),
    ("commands/vg/test-spec.md", "/vg:review"),
    ("commands/vg/_shared/test/close.md", "/vg:accept"),
]


def test_each_close_writes_next_command_to_pipeline_state():
    """Each phase close must write state['next_command'] = '/vg:NEXT {phase}'
    to PIPELINE-STATE.json so --auto-chain readers can pick it up."""
    failures = []
    for rel, expected_cmd in CASES:
        path = REPO / rel
        body = path.read_text(encoding="utf-8")
        if 'next_command' not in body:
            failures.append(f"{rel}: missing next_command write")
            continue
        if expected_cmd not in body:
            failures.append(f"{rel}: expected '{expected_cmd}' next-command target")
    assert not failures, "F1 next_command missing:\n  " + "\n  ".join(failures)


def test_review_close_pattern_remains_intact():
    """Review close (existing emit) must still write next_command — no regression."""
    body = (REPO / "commands/vg/_shared/review/close.md").read_text(encoding="utf-8")
    assert "next_command" in body, "F1: existing review next_command pattern must remain"
