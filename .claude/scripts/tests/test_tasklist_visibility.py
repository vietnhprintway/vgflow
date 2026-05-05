"""
Task-list visibility anti-forge tests (2026-04-24).

User requirement: "khởi tạo 1 flow nào đều phải show được Task để AI bám vào đó
mà làm". Every pipeline command entry step MUST:
  1. Call emit-tasklist.py helper (authoritative step list from filter-steps.py)
  2. Emit {command}.tasklist_shown event for contract verification
  3. Print step list to user so AI can't start silently

This test ensures:
  - emit-tasklist.py works end-to-end (filter → print → emit)
  - Every command has the helper invocation in its entry step
  - Every command contract lists {cmd}.tasklist_shown in must_emit_telemetry
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "sync.sh").exists() and (candidate / "commands" / "vg").exists():
            return candidate
        if (
            (candidate / ".claude" / "commands" / "vg").exists()
            and (candidate / ".claude" / "scripts" / "emit-tasklist.py").exists()
        ):
            return candidate
    return Path(__file__).resolve().parents[2]


REPO_ROOT = _repo_root()
HELPER    = REPO_ROOT / ".claude" / "scripts" / "emit-tasklist.py"
CMDS_DIR  = REPO_ROOT / ".claude" / "commands" / "vg"

COMMANDS_WITH_CONTRACT = [
    "accept", "blueprint", "build", "review", "scope", "specs", "test",
]


# ─── Helper script tests ──────────────────────────────────────────────

class TestEmitTasklistHelper:
    def test_helper_exists(self):
        assert HELPER.exists(), f"Missing {HELPER}"

    def test_helper_no_emit_mode_prints_summary(self):
        """--no-emit prints compact summary; full list lives in contract."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            [sys.executable, str(HELPER),
             "--command", "vg:blueprint",
             "--profile", "web-fullstack",
             "--phase", "7.14",
             "--no-emit"],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT), env=env, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 0, r.stderr
        # Summary line must contain command + phase + profile + counts.
        assert "vg:blueprint" in r.stdout
        assert "Phase 7.14" in r.stdout
        assert "web-fullstack" in r.stdout
        assert re.search(r"\d+\s*step", r.stdout)
        assert re.search(r"\d+\s*group", r.stdout)
        assert re.search(r"\d+\s*projection", r.stdout)

    def test_helper_writes_authoritative_contract(self):
        """Steps must come from filter-steps.py, not AI improv."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        filter_steps = REPO_ROOT / ".claude" / "scripts" / "filter-steps.py"
        cmd_file = REPO_ROOT / ".claude" / "commands" / "vg" / "blueprint.md"
        r = subprocess.run(
            [sys.executable, str(filter_steps),
             "--command", str(cmd_file),
             "--profile", "web-fullstack",
             "--output-ids"],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT), env=env, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 0, r.stderr
        assert "1_parse_args" in r.stdout
        assert "2a_plan" in r.stdout
        assert "2b_contracts" in r.stdout

    def test_helper_groups_build_steps_into_checklists(self):
        mod = _load_emit_tasklist_module()
        defs = mod.CHECKLIST_DEFS["vg:build"]
        group_ids = {g[0] for g in defs}
        assert "build_preflight" in group_ids
        assert "build_execute" in group_ids
        execute_steps = [g[2] for g in defs if g[0] == "build_execute"][0]
        assert "8_execute_waves" in execute_steps

    def test_helper_refuses_contract_for_wrong_active_command(self, tmp_path, monkeypatch):
        """Regression: deploy tasklist must not bind to an active vg:test run."""
        mod = _load_emit_tasklist_module()
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        vg = tmp_path / ".vg"
        (vg / "active-runs").mkdir(parents=True)
        run = {
            "run_id": "run-test",
            "command": "vg:test",
            "phase": "4.2",
            "session_id": "s1",
        }
        (vg / "current-run.json").write_text(json.dumps(run), encoding="utf-8")
        (vg / "active-runs" / "s1.json").write_text(json.dumps(run), encoding="utf-8")

        with pytest.raises(RuntimeError, match="command mismatch"):
            mod._write_contract(
                "vg:deploy",
                "4.2",
                "web-fullstack",
                None,
                ["0_parse_and_validate"],
                [{"id": "deploy_preflight", "title": "Deploy Preflight", "items": ["0_parse_and_validate"]}],
            )

    def test_helper_fails_gracefully_on_unknown_command(self):
        r = subprocess.run(
            [sys.executable, str(HELPER),
             "--command", "vg:nonexistent",
             "--profile", "web-fullstack",
             "--phase", "7.14",
             "--no-emit"],
            capture_output=True, text=True, timeout=5,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 1  # filter-steps returns empty → exit 1

    def test_helper_requires_all_three_args(self):
        r = subprocess.run(
            [sys.executable, str(HELPER), "--command", "vg:blueprint"],
            capture_output=True, text=True, timeout=5,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode != 0


# ─── Command wiring tests ─────────────────────────────────────────────

@pytest.mark.parametrize("cmd", COMMANDS_WITH_CONTRACT)
class TestCommandWiring:
    def test_command_invokes_emit_tasklist(self, cmd):
        """Each command must call emit-tasklist.py in an entry bash block."""
        path = CMDS_DIR / f"{cmd}.md"
        text = path.read_text(encoding="utf-8")
        assert "emit-tasklist.py" in text, (
            f"{cmd}.md missing emit-tasklist.py invocation — user won't see "
            f"step plan at flow start"
        )

    def test_command_emits_tasklist_shown_event(self, cmd):
        """Each command's runtime_contract must_emit_telemetry lists tasklist_shown."""
        path = CMDS_DIR / f"{cmd}.md"
        text = path.read_text(encoding="utf-8")
        # Match ${cmd}.tasklist_shown in frontmatter
        short = cmd  # accept → accept.tasklist_shown
        pattern = rf'event_type:\s*["\']?{short}\.tasklist_shown'
        assert re.search(pattern, text), (
            f"{cmd}.md runtime_contract missing {short}.tasklist_shown event "
            f"in must_emit_telemetry"
        )
        if cmd in {"blueprint", "build", "review", "test", "accept"}:
            native_pattern = rf'event_type:\s*["\']?{short}\.native_tasklist_projected'
            assert re.search(native_pattern, text), (
                f"{cmd}.md runtime_contract missing {short}.native_tasklist_projected"
            )
            frontmatter = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL).group(1)
            assert "TodoWrite" in frontmatter, (
                f"{cmd}.md must expose Claude Code's native TodoWrite tasklist tool"
            )
            policy_text = _tasklist_policy_text(text)
            assert "tasklist-contract.json" in policy_text, (
                f"{cmd}.md must bind native tasklist to tasklist-contract.json"
            )
            assert "replace-on-start" in policy_text, (
                f"{cmd}.md must replace stale native tasklists at workflow start"
            )
            assert "close-on-complete" in policy_text, (
                f"{cmd}.md must close/clear native tasklists at workflow completion"
            )

    def test_emit_tasklist_invocation_passes_command_arg(self, cmd):
        """Invocation must pass --command vg:{cmd} matching the skill name.

        Searches globally (not just first emit-tasklist.py mention) because
        frontmatter comments may reference the helper before the actual
        bash invocation appears.
        """
        path = CMDS_DIR / f"{cmd}.md"
        text = path.read_text(encoding="utf-8")
        exact = (
            f'--command "vg:{cmd}"' in text
            or f"--command 'vg:{cmd}'" in text
            or f"--command vg:{cmd}" in text
        )
        assert exact or (
            "emit-tasklist.py" in text
            and ("create_task_tracker" in text or "native_tasklist_projected" in text)
        ), (
            f"{cmd}.md must either call emit-tasklist.py with vg:{cmd} directly "
            f"or route through the shared create_task_tracker block"
        )


# ─── Contract end-to-end consistency ──────────────────────────────────

def test_all_commands_have_runtime_contract():
    """Every pipeline command file must declare runtime_contract frontmatter."""
    for cmd in COMMANDS_WITH_CONTRACT:
        path = CMDS_DIR / f"{cmd}.md"
        assert path.exists(), f"Missing {cmd}.md"
        text = path.read_text(encoding="utf-8")
        # Frontmatter between first two `---`
        m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        assert m, f"{cmd}.md missing YAML frontmatter"
        frontmatter = m.group(1)
        assert "runtime_contract:" in frontmatter, (
            f"{cmd}.md frontmatter missing runtime_contract block"
        )


def test_tasklist_shown_event_not_in_reserved_prefixes():
    """tasklist_shown event must be emittable via CLI (not reserved).

    Otherwise emit-tasklist.py itself would fail to register the event.
    """
    main_file = REPO_ROOT / ".claude" / "scripts" / "vg-orchestrator" / "__main__.py"
    text = main_file.read_text(encoding="utf-8")
    # Find RESERVED_EVENT_PREFIXES tuple
    m = re.search(r"RESERVED_EVENT_PREFIXES\s*=\s*\(([^)]+)\)", text, re.DOTALL)
    assert m, "RESERVED_EVENT_PREFIXES not found"
    reserved = m.group(1)
    # Must NOT include tasklist prefix
    assert '"tasklist"' not in reserved
    assert "tasklist_shown" not in reserved


def test_lifecycle_contract_in_slim_entry_or_shared_ref():
    policy_text = _tasklist_policy_text((CMDS_DIR / "blueprint.md").read_text(encoding="utf-8"))
    assert "replace-on-start" in policy_text and "close-on-complete" in policy_text


def test_codex_plan_window_stays_compact_in_contract(tmp_path, monkeypatch):
    """Codex shows a compact plan window; full hierarchy stays in contract."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("emit_tasklist", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    run_id = "r-codex-window"
    (tmp_path / ".vg").mkdir(parents=True)
    (tmp_path / ".vg" / "current-run.json").write_text(
        json.dumps({"run_id": run_id}), encoding="utf-8"
    )
    steps = [
        "00_gate_integrity_precheck",
        "0_parse_and_validate",
        "phase1_code_scan",
        "phase2_browser_discovery",
        "phase2_5_recursive_lens_probe",
        "phase2e_findings_merge",
        "phase3_fix_loop",
        "phase4_goal_comparison",
        "write_artifacts",
        "complete",
    ]
    checklists = mod._build_checklists("vg:review", steps)

    path = mod._write_contract("vg:review", "4.2", "web-fullstack", "full", steps, checklists)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["codex_plan_window"]["max_visible_items"] == 6
    assert data["codex_plan_window"]["active_first"] is True
    assert data["codex_plan_window"]["collapse_completed"] is True
    assert data["codex_plan_window"]["show_pending_remainder"] is True
    assert data["codex_plan_window"]["full_projection_item_count"] == data["projection_item_count"]
    assert data["projection_item_count"] > data["codex_plan_window"]["max_visible_items"]
    assert "+N pending" in data["native_adapters"]["codex"]
    assert "tasklist-contract.json" in data["native_adapters"]["codex"]


def test_blueprint_and_review_codex_projection_stays_compact_in_instructions():
    """Command bodies must not override the Codex adapter with full hierarchy."""
    source_root = REPO_ROOT / "commands" / "vg"
    blueprint_preflight = (
        source_root / "_shared" / "blueprint" / "preflight.md"
    ).read_text(encoding="utf-8")
    review = (source_root / "review.md").read_text(encoding="utf-8")

    assert "Codex CLI: consume `codex_plan_window`" in blueprint_preflight
    assert "NOT paste all `projection_items[]` into Codex `update_plan`" in blueprint_preflight
    assert "--adapter auto" in blueprint_preflight
    assert "--adapter <auto|claude|codex|fallback>" not in blueprint_preflight

    assert "Codex MUST keep the visible plan compact" in review
    assert "project only a compact plan window from `codex_plan_window`" in review
    assert "do not create one visible\n  item per `projection_items[]` row" in review
    assert "--adapter <auto|claude|codex|fallback>" not in review

def _load_emit_tasklist_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("emit_tasklist", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tasklist_policy_text(command_text: str) -> str:
    refs = [
        REPO_ROOT / "commands" / "vg" / "_shared" / "lib" / "tasklist-projection-instruction.md",
        REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "lib" / "tasklist-projection-instruction.md",
    ]
    parts = [command_text]
    for ref in refs:
        if ref.exists():
            parts.append(ref.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _emit_tasklist(command: str, profile: str = "web-fullstack", mode: str | None = None) -> str:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, str(HELPER),
        "--command", command,
        "--profile", profile,
        "--phase", "7.14",
        "--no-emit",
    ]
    if mode:
        cmd.extend(["--mode", mode])
    r = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=10,
        cwd=str(REPO_ROOT), env=env, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_helper_groups_test_steps_into_checklists():
    defs = _load_emit_tasklist_module().CHECKLIST_DEFS["vg:test"]
    group_ids = {g[0] for g in defs}
    assert "test_preflight" in group_ids
    assert "test_deploy" in group_ids
    assert "test_runtime" in group_ids
    assert "test_codegen" in group_ids
    assert "test_regression_security" in group_ids
    flat_steps = {step for _, _, steps in defs for step in steps}
    assert "5b_runtime_contract_verify" in flat_steps
    assert "5h_security_dynamic" in flat_steps


def test_helper_groups_accept_steps_into_checklists():
    defs = _load_emit_tasklist_module().CHECKLIST_DEFS["vg:accept"]
    group_ids = {g[0] for g in defs}
    assert "accept_preflight" in group_ids
    assert "accept_gates" in group_ids
    assert "accept_uat" in group_ids
    assert "accept_audit" in group_ids
    flat_steps = {step for _, _, steps in defs for step in steps}
    assert "create_task_tracker" in flat_steps
    assert "6_write_uat_md" in flat_steps


def test_test_tasklist_respects_profile_switches():
    mod = _load_emit_tasklist_module()
    web = set(mod._get_step_list("vg:test", "web-fullstack", None))
    mobile = set(mod._get_step_list("vg:test", "mobile-rn", None))
    cli = set(mod._get_step_list("vg:test", "cli-tool", None))

    assert "5a_deploy" in web
    assert "5a_mobile_deploy" in mobile
    assert "5c_mobile_flow" in mobile
    assert "5d_mobile_codegen" in mobile
    assert "5d_deep_probe" in cli
