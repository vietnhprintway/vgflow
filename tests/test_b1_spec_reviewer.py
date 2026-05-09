"""v2.66.0 Task 7 (B1) — per-task spec compliance reviewer agent.

Verifies:
1. .claude/agents/vg-build-spec-reviewer/SKILL.md exists with required content
2. post-execution-overview.md spawns the reviewer per task
3. build.md wires STEP 5.1 referencing the reviewer
4. Agent definition explicitly says per-task (not per-wave)
"""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def test_spec_reviewer_agent_exists():
    """v2.66.0 B1 — new vg-build-spec-reviewer agent definition exists."""
    p = REPO_ROOT / ".claude" / "agents" / "vg-build-spec-reviewer" / "SKILL.md"
    assert p.exists(), f"vg-build-spec-reviewer agent definition missing at {p}"
    body = p.read_text(encoding="utf-8")
    assert "spec compliance" in body.lower() or "spec-compliance" in body, \
        "Agent SKILL.md must mention spec compliance"
    assert "PLAN.md" in body, "Agent SKILL.md must reference PLAN.md as source of truth"


def test_build_post_execution_invokes_spec_reviewer():
    """post-execution-overview.md must reference the new reviewer."""
    body = (REPO_ROOT / "commands" / "vg" / "_shared" / "build" / "post-execution-overview.md").read_text(encoding="utf-8")
    assert "vg-build-spec-reviewer" in body, \
        "post-execution-overview must spawn vg-build-spec-reviewer per task"


def test_build_md_wires_b1_step():
    """build.md must wire B1 reviewer (in STEP 5.1 or similar)."""
    body = (REPO_ROOT / "commands" / "vg" / "build.md").read_text(encoding="utf-8")
    assert ("spec-reviewer" in body
            or "spec_reviewer" in body
            or "vg-build-spec-reviewer" in body), \
        "build.md must reference B1 spec reviewer wiring"


def test_spec_reviewer_per_task_not_per_wave():
    """B1 reviews per-task, not per-wave (each task gets independent compliance check)."""
    p = REPO_ROOT / ".claude" / "agents" / "vg-build-spec-reviewer" / "SKILL.md"
    body = p.read_text(encoding="utf-8")
    assert ("per task" in body.lower() or "per-task" in body), \
        "Agent SKILL.md must declare per-task semantics (not per-wave)"
