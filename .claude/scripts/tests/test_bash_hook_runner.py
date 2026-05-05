from __future__ import annotations

import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "hooks" / "vg-run-bash-hook.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("vg_run_bash_hook", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runner_detects_wsl_launcher_paths():
    mod = _load_runner()
    assert mod._is_wsl_launcher(r"C:\Windows\System32\bash.exe")
    assert mod._is_wsl_launcher(
        r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\bash.exe"
    )
    assert not mod._is_wsl_launcher(r"C:\Program Files\Git\bin\bash.exe")


def test_runner_prefers_git_bash_over_path_wsl_on_windows(monkeypatch):
    if os.name != "nt":
        return
    mod = _load_runner()
    candidates = mod.candidate_bashes()
    assert candidates, "expected at least one bash candidate"
    assert not mod._is_wsl_launcher(candidates[0]), (
        "Git Bash must be preferred over WSL launcher for Windows hook paths"
    )


def test_runner_normalizes_windows_paths_for_git_bash():
    mod = _load_runner()
    script = r"D:\Workspace\repo\.claude\scripts\hooks\vg-user-prompt-submit.sh"
    bash = r"C:\Program Files\Git\bin\bash.exe"
    normalized = mod.script_arg_for_bash(script, bash)
    if os.name == "nt":
        assert "\\" not in normalized
        assert normalized.endswith("/.claude/scripts/hooks/vg-user-prompt-submit.sh")
    else:
        assert normalized == script
