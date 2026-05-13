"""tests/test_f3_posttooluse_hooks_wired.py — F3 PostToolUse orphans wired."""
from __future__ import annotations
import json
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
INSTALL_HOOKS = REPO / "scripts" / "hooks" / "install-hooks.sh"


def test_install_hooks_wires_agent_post_hook():
    body = INSTALL_HOOKS.read_text(encoding="utf-8")
    assert "vg-post-tool-use-agent" in body, (
        "F3: install-hooks.sh must wire vg-post-tool-use-agent.sh for "
        "PostToolUse on Agent matcher (Issue #140 git intent-to-add mitigation)"
    )


def test_install_hooks_wires_askuserquestion_post_hook():
    body = INSTALL_HOOKS.read_text(encoding="utf-8")
    assert "vg-post-tool-use-askuserquestion" in body or "askuserquestion" in body.lower(), (
        "F3: install-hooks.sh must wire vg-post-tool-use-askuserquestion.sh "
        "for PostToolUse on AskUserQuestion matcher (TaskUpdate reminder)"
    )
