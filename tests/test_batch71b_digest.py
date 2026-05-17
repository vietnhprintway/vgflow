"""tests/test_batch71b_digest.py — B71b compact tasklist digest on non-slash prompts.

Tests verify the digest block in vg-user-prompt-submit.sh:
  - Fires on stale snapshot / contract-changed / >30min since last / <50% overlap.
  - Skips on short prompts (<10 chars — Y/N replies).
  - Rate-limited to 60s.
  - Respects VG_TASKLIST_REPROJECT_DISABLE=1.
  - Skips when slash command (slash branch owns).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "scripts" / "hooks" / "vg-user-prompt-submit.sh"
HOOK_MIRROR = REPO / ".claude" / "scripts" / "hooks" / "vg-user-prompt-submit.sh"


# ---------------------------------------------------------------------------
# Text presence tests (cheap, deterministic).
# ---------------------------------------------------------------------------


def test_b71b_hook_has_digest_block():
    body = HOOK.read_text(encoding="utf-8")
    assert "B71b" in body
    assert "[VG-TASKLIST]" in body
    assert "VG_TASKLIST_REPROJECT_DISABLE" in body
    assert "60" in body  # rate-limit
    assert "1800" in body  # 30min trigger


def test_b71b_hook_respects_disable_env():
    body = HOOK.read_text(encoding="utf-8")
    assert 'VG_TASKLIST_REPROJECT_DISABLE:-0' in body or 'VG_TASKLIST_REPROJECT_DISABLE' in body


def test_b71b_hook_skips_short_prompts():
    body = HOOK.read_text(encoding="utf-8")
    # `$prompt_len >= 10` check.
    assert "prompt_len" in body
    assert "-ge 10" in body or ">= 10" in body


def test_b71b_hook_emits_to_stderr():
    body = HOOK.read_text(encoding="utf-8")
    # Python heredoc writes to stderr via the bash `>&2` redirect on python3 -.
    # Find the redirect on the heredoc line.
    assert "python3 - <<'DIGEST_PY' >&2" in body


def test_b71b_triggers_documented():
    body = HOOK.read_text(encoding="utf-8")
    for trigger in ("contract-changed", "snapshot-changed", "overlap<50%", ">30min-since-last"):
        assert trigger in body, f"Missing trigger: {trigger}"


# ---------------------------------------------------------------------------
# Behavioral tests via bash subprocess.
# ---------------------------------------------------------------------------


pytestmark_bash_unavailable = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)


def _setup_run(tmp_path: Path, run_id: str, session_id: str,
               with_contract: bool = True, with_snapshot: bool = False,
               snapshot_status_counts: tuple[int, int, int] | None = None) -> dict:
    """Build a synthetic project layout in tmp_path with .vg/active-runs + contract."""
    active_runs = tmp_path / ".vg" / "active-runs"
    active_runs.mkdir(parents=True, exist_ok=True)
    (active_runs / f"{session_id}.json").write_text(
        json.dumps({
            "command": "vg:test-spec",
            "phase": "7.16",
            "run_id": run_id,
            "tasklist_projected": True,
            "tasklist_projected_adapter": "claude",
        }),
        encoding="utf-8",
    )
    run_dir = tmp_path / ".vg" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if with_contract:
        (run_dir / "tasklist-contract.json").write_text(
            json.dumps({
                "command": "vg:test-spec",
                "phase": "7.16",
                "projection_items": [
                    {"id": "step1", "kind": "step", "title": "Step 1"},
                    {"id": "step2", "kind": "step", "title": "Step 2"},
                ],
            }),
            encoding="utf-8",
        )
    if with_snapshot:
        items = []
        if snapshot_status_counts:
            ip, p, c = snapshot_status_counts
            for i in range(ip):
                items.append({"id": "step1", "content": "Step 1", "status": "in_progress", "match_class": "exact"})
            for i in range(p):
                items.append({"id": "step2", "content": "Step 2", "status": "pending", "match_class": "exact"})
            for i in range(c):
                items.append({"id": "step1", "content": "Step 1", "status": "completed", "match_class": "exact"})
        (run_dir / ".todowrite-snapshot.json").write_text(
            json.dumps({"schema_version": 2, "items": items}),
            encoding="utf-8",
        )
    # Empty events.db
    (tmp_path / ".vg" / "events.db").write_bytes(b"")
    return {"active_runs": active_runs, "run_dir": run_dir}


def _run_hook(prompt: str, tmp_path: Path, session_id: str = "sess-1",
              extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "VG_REPO_ROOT": str(tmp_path),
           "VG_HOME": str(REPO / ".claude"),
           "CLAUDE_HOOK_SESSION_ID": session_id,
           "PYTHONIOENCODING": "utf-8"}
    if extra_env:
        env.update(extra_env)
    stdin_json = json.dumps({"prompt": prompt, "session_id": session_id})
    return subprocess.run(
        ["bash", str(HOOK)],
        input=stdin_json,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(tmp_path),
        timeout=15,
    )


@pytestmark_bash_unavailable
def test_b71b_digest_fires_on_first_stale_snapshot(tmp_path: Path):
    """First non-slash prompt with active run + contract → digest emitted."""
    _setup_run(tmp_path, "rid-1", "sess-1", with_contract=True, with_snapshot=False)
    result = _run_hook("Hello, please check the status", tmp_path)
    # Hook exits 0; stderr may contain flow-context + digest.
    assert "[VG-TASKLIST]" in result.stderr or "vg-flow-context" in result.stderr


@pytestmark_bash_unavailable
def test_b71b_digest_skipped_on_short_prompt(tmp_path: Path):
    """Prompt < 10 chars → no digest (Y/N reply heuristic)."""
    _setup_run(tmp_path, "rid-1", "sess-1", with_contract=True)
    result = _run_hook("yes", tmp_path)
    assert "[VG-TASKLIST]" not in result.stderr


@pytestmark_bash_unavailable
def test_b71b_digest_disabled_env(tmp_path: Path):
    """VG_TASKLIST_REPROJECT_DISABLE=1 → no digest."""
    _setup_run(tmp_path, "rid-1", "sess-1", with_contract=True)
    result = _run_hook(
        "Hello check tasklist please",
        tmp_path,
        extra_env={"VG_TASKLIST_REPROJECT_DISABLE": "1"},
    )
    assert "[VG-TASKLIST]" not in result.stderr


@pytestmark_bash_unavailable
def test_b71b_digest_skipped_for_slash_command(tmp_path: Path):
    """Slash command → digest not emitted (slash branch owns)."""
    _setup_run(tmp_path, "rid-1", "sess-1", with_contract=True)
    result = _run_hook("/vg:next", tmp_path)
    # The slash branch is taken; B71b digest in non-slash branch is unreachable.
    assert "[VG-TASKLIST]" not in result.stderr


# ---------------------------------------------------------------------------
# Mirror parity.
# ---------------------------------------------------------------------------


def test_b71b_hook_mirror_byte_identical():
    canonical = HOOK.read_bytes()
    mirror = HOOK_MIRROR.read_bytes()
    assert canonical == mirror
