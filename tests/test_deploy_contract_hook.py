"""tests/test_deploy_contract_hook.py — Batch 20 PreToolUse drift guard."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "scripts" / "hooks" / "vg-deploy-contract-guard.sh"
INSTALL = REPO / "scripts" / "hooks" / "install-hooks.sh"


def test_hook_exists():
    assert HOOK.is_file()


def test_hook_blocks_command_drift(tmp_path, monkeypatch):
    """Contract = ansible. AI tries 'pm2 restart all'. Hook BLOCKs."""
    vg_dir = tmp_path / ".vg"
    vg_dir.mkdir()
    (vg_dir / "DEPLOY-CONTRACT.json").write_text(json.dumps({
        "method": "ansible",
        "commands": {"build": "ansible-playbook x", "restart": "ansible-playbook y", "health": "ansible-playbook z"},
        "fingerprint_pattern": "^ansible(-playbook)?\\b",
        "lock_sha256": "abc",
    }), encoding="utf-8")

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "pm2 restart all"},
    })
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    r = subprocess.run(
        ["bash", str(HOOK)],
        input=payload, env=env,
        capture_output=True, text=True,
    )
    # Hook must block — non-zero exit OR emit decision=block in stdout JSON
    blocked = r.returncode != 0 or '"decision": "block"' in r.stdout or '"decision":"block"' in r.stdout
    assert blocked, (
        f"Hook must BLOCK pm2 command when contract locked to ansible. "
        f"rc={r.returncode}, stdout={r.stdout[:200]}, stderr={r.stderr[:200]}"
    )


def test_hook_allows_matching_command(tmp_path):
    """ansible-playbook command must pass when contract = ansible."""
    vg_dir = tmp_path / ".vg"
    vg_dir.mkdir()
    (vg_dir / "DEPLOY-CONTRACT.json").write_text(json.dumps({
        "method": "ansible",
        "commands": {"build": "ansible-playbook x", "restart": "ansible-playbook y", "health": "ansible-playbook z"},
        "fingerprint_pattern": "^ansible(-playbook)?\\b",
        "lock_sha256": "abc",
    }), encoding="utf-8")

    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "ansible-playbook deploy.yml --tags restart"},
    })
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    r = subprocess.run(
        ["bash", str(HOOK)],
        input=payload, env=env,
        capture_output=True, text=True,
    )
    # Exit 0, no decision=block
    assert r.returncode == 0, f"Hook should pass matching command, rc={r.returncode}"
    assert '"decision": "block"' not in r.stdout


def test_hook_passes_through_non_deploy_commands(tmp_path):
    """Non-deploy commands (npm test, git status, etc.) must pass through."""
    vg_dir = tmp_path / ".vg"
    vg_dir.mkdir()
    (vg_dir / "DEPLOY-CONTRACT.json").write_text(json.dumps({
        "method": "ansible",
        "commands": {"build": "ansible-playbook x", "restart": "ansible-playbook y", "health": "ansible-playbook z"},
        "fingerprint_pattern": "^ansible(-playbook)?\\b",
        "lock_sha256": "abc",
    }), encoding="utf-8")
    for cmd in ["npm test", "git status", "ls -la", "python script.py"]:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        r = subprocess.run(["bash", str(HOOK)], input=payload, env=env,
                          capture_output=True, text=True)
        assert r.returncode == 0, f"non-deploy '{cmd}' should pass, rc={r.returncode}"


def test_install_hooks_wires_deploy_guard():
    body = INSTALL.read_text(encoding="utf-8")
    assert "vg-deploy-contract-guard" in body, (
        "install-hooks.sh must register vg-deploy-contract-guard.sh as "
        "PreToolUse Bash hook"
    )
