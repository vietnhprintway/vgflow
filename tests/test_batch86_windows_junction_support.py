"""B86 v4.64.4 — Issue #194 finding #6 Windows junction support.

User dogfood report (RTB, 2026-05-17): on Windows git-bash, `ln -s` falls
back to a silent directory copy without warning. The dispatcher then prints
"vgflow: linked …" even though no symlink was created. The `--check`
downstream then flags the resulting REAL directory as stale because it
shouldn't be a copy under global-install doctrine.

User asked for:
- Detect `os.name == 'nt'` (or MINGW* uname) in dispatcher
- Use `cmd //c mklink /J <target> <source>` for directory junctions
  (no admin needed on Windows in most cases)
- Update "linked" log message to "linked (junction)" or
  "linked (fallback copy + manual cleanup needed)"
- `--check` should distinguish stale project-local managed copies from
  intentional user files

B86 ships the junction-attempt + honest messages. The `--check`
distinction is out of scope (separate gate logic refactor).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = REPO_ROOT / "bin" / "vg-cli-dispatcher.sh"


def test_b86_windows_detection_helper_added() -> None:
    """`_vg_is_windows` helper must exist and recognize MSYS/MINGW/Cygwin."""
    body = DISPATCHER.read_text(encoding="utf-8")
    assert "_vg_is_windows" in body, "Windows detection helper missing"
    # Must check both OS env var and uname
    assert "Windows_NT" in body, "OS=Windows_NT branch missing"
    assert "MINGW" in body, "MINGW uname branch missing"
    assert "Cygwin" in body or "cygwin" in body.lower(), "Cygwin uname branch missing"


def test_b86_junction_helper_added() -> None:
    """`_vg_link_dir` helper must attempt mklink /J on Windows first."""
    body = DISPATCHER.read_text(encoding="utf-8")
    assert "_vg_link_dir" in body, "_vg_link_dir helper missing"
    # Must use cmd //c mklink /J for the junction attempt
    assert "mklink /J" in body, "mklink /J directory junction missing"
    # Must use cygpath -w to convert paths for cmd
    assert "cygpath -w" in body, "cygpath -w conversion missing"


def test_b86_honest_link_messages() -> None:
    """Output messages must distinguish junction / symlink / copy."""
    body = DISPATCHER.read_text(encoding="utf-8")
    assert "linked (junction)" in body, "junction success message missing"
    assert "linked (symlink)" in body, "symlink success message missing"
    assert "copied (no dir link support)" in body, "copy fallback message missing"


def test_b86_orchestrator_shim_uses_link_helper() -> None:
    """`link_project_orchestrator_shim` must call `_vg_link_dir` (no
    direct `ln -s` left in the function body).
    """
    body = DISPATCHER.read_text(encoding="utf-8")
    # Locate the function block
    start = body.index("link_project_orchestrator_shim()")
    # Find the next function definition to bound the search
    end = body.index("\nrefresh_global_claude_commands()", start)
    block = body[start:end]
    assert "_vg_link_dir" in block, "shim function must call _vg_link_dir helper"


def test_b86_claude_commands_refresh_uses_link_helper() -> None:
    body = DISPATCHER.read_text(encoding="utf-8")
    start = body.index("refresh_global_claude_commands()")
    end = body.index("\ncodex_config_path()", start)
    block = body[start:end]
    assert "_vg_link_dir" in block, "claude commands refresh must call _vg_link_dir"


def test_b86_dispatcher_bash_syntax_valid() -> None:
    """Dispatcher must parse via `bash -n` on the host."""
    import subprocess
    import shutil
    bash_bin = shutil.which("bash") or "/bin/bash"
    if not Path(bash_bin).exists():
        import pytest
        pytest.skip(f"bash not available at {bash_bin}")
    proc = subprocess.run(
        [bash_bin, "-n", str(DISPATCHER)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"bash -n failed: {proc.stderr}"
    )
