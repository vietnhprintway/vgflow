"""B82 v4.63.14 — Stop hook wave-done marker filename fix.

User dogfood report (RTB 2026-05-17/18, phase 8.1):
"vấn đề là AI bỏ qua Step nằm trong flow build, nghĩa là chạy build, chạy
hết wave là dừng, trong khi còn các step khác như 5.x v.v cần chạy, thì
AI không tự kích hoạt chúng để chạy."

Forensics: 6 of 8 phase 8.1 build sessions on 2026-05-17 had
`last_step=8_execute_waves` — AI marked wave execution done then ended
turn. Stop hook gate 4a (POST-WAVE CONTINUATION) was supposed to BLOCK
the turn-end with "STEP 5 post-execution not run", but it never fired.

Root cause in `scripts/hooks/vg-stop.sh:93`:
    waves_done=$(ls "$phase_dir/.step-markers"/wave-*.done 2>/dev/null | wc -l)

The waves-overview.md script doesn't write `wave-N.done` markers — it
only writes the single `8_execute_waves.done` marker after wave block
finishes (line 1311). The wave-*.done glob matched ZERO files always,
making `waves_done=0`, making the gate 4a precondition
`[ "$waves_done" -gt 0 ]` always false. Gates 4b/4c/4d/4e have other
preconditions (need step 9/10/11/12 done first), so when AI stops at
step 8 NONE of the cascade gates fire.

Fix: detect waves done via the canonical `8_execute_waves.done` marker.
Legacy `wave-*.done` glob preserved as fallback for future per-wave
marker schemes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STOP_HOOK = REPO_ROOT / "scripts" / "hooks" / "vg-stop.sh"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "hooks" / "vg-stop.sh"


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def test_b82_stop_hook_uses_canonical_marker() -> None:
    """Stop hook must detect waves_done via 8_execute_waves.done marker."""
    body = STOP_HOOK.read_text(encoding="utf-8")
    assert "8_execute_waves.done" in body, (
        "canonical wave-done marker missing in stop hook"
    )
    # Legacy fallback preserved
    assert "wave-*.done" in body, "legacy glob fallback missing"


def test_b82_stop_hook_no_longer_relies_solely_on_glob() -> None:
    """The line that set waves_done from only the glob must be gone."""
    body = STOP_HOOK.read_text(encoding="utf-8")
    # Old broken pattern: `waves_done=$(ls "$phase_dir/.step-markers"/wave-*.done`
    # WITHOUT the canonical 8_execute_waves marker check first.
    # We accept the legacy glob as a fallback IF the canonical check runs first.
    canonical_idx = body.index("8_execute_waves.done")
    glob_idx = body.index("/wave-*.done")
    assert canonical_idx < glob_idx, (
        "canonical marker check must precede legacy glob fallback"
    )


def test_b82_mirror_byte_identical() -> None:
    assert STOP_HOOK.read_bytes() == MIRROR.read_bytes(), (
        "vg-stop.sh mirror drift"
    )


# ---------------------------------------------------------------------------
# Behavioral — simulate the failing scenario and assert gate 4a fires
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Stop hook is bash-only; behavioral run requires POSIX shell with "
           "vg-orchestrator + jq in PATH. Tested on Linux CI.",
)
def test_b82_gate_4a_fires_when_waves_done_but_post_exec_missing(tmp_path: Path) -> None:
    """End-to-end: simulate RTB scenario — `8_execute_waves.done` marker
    present, `9_post_execution.done` missing, `.is-final-wave=true` → Stop
    hook should emit POST-WAVE CONTINUATION (4a) failure.
    """
    repo = tmp_path / "repo"
    phase_dir = repo / ".vg" / "phases" / "8.1-test"
    markers = phase_dir / ".step-markers"
    markers.mkdir(parents=True)
    # Wave done, post-execution missing
    (markers / "8_execute_waves.done").touch()
    # active-run state
    run_id = "test-run"
    runs_dir = repo / ".vg" / "runs" / run_id
    runs_dir.mkdir(parents=True)
    (runs_dir / ".is-final-wave").write_text("true", encoding="utf-8")
    active_run = repo / ".vg" / "active-runs" / "sess.json"
    active_run.parent.mkdir(parents=True)
    active_run.write_text(
        '{"run_id":"' + run_id + '","command":"vg:build",'
        '"phase":"8.1","phase_dir":"' + str(phase_dir) + '","session_id":"sess"}',
        encoding="utf-8",
    )
    (repo / ".vg" / "current-run.json").write_text(
        '{"run_id":"' + run_id + '","command":"vg:build","phase":"8.1"}',
        encoding="utf-8",
    )

    # Invoke hook with stdin payload
    hook_input = '{"session_id":"sess","stop_hook_active":false}'
    proc = subprocess.run(
        ["bash", str(STOP_HOOK)],
        cwd=repo, input=hook_input,
        capture_output=True, text=True,
        env={**os.environ, "VG_REPO_ROOT": str(repo)},
    )
    # Gate 4a must fire — either via stderr block message or JSON decision
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "POST-WAVE CONTINUATION (4a)" in combined or "4a" in combined, (
        f"gate 4a did not fire. rc={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
