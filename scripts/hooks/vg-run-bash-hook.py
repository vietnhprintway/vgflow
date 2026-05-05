#!/usr/bin/env python3
r"""Run a VG bash hook with a Windows-safe bash selection.

Claude Code executes hook command strings through the host shell. On Windows,
`bash` can resolve to the WSL launcher at C:\Windows\System32\bash.exe before
Git Bash. WSL bash receives Windows paths such as D:\repo\... and fails before
the hook script starts. This wrapper prefers Git Bash and preserves stdin,
stdout, stderr, cwd, and exit code.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _is_wsl_launcher(path: str) -> bool:
    p = path.replace("/", "\\").lower()
    return (
        "\\windows\\system32\\bash.exe" in p
        or "\\appdata\\local\\microsoft\\windowsapps\\bash.exe" in p
    )


def _existing(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in paths:
        if not raw:
            continue
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(raw)))
        key = os.path.normcase(path)
        if key in seen or not os.path.isfile(path):
            continue
        seen.add(key)
        out.append(path)
    return out


def candidate_bashes() -> list[str]:
    env_bash = os.environ.get("VG_BASH", "")
    path_bash = shutil.which("bash") or shutil.which("bash.exe") or ""

    if os.name != "nt":
        return _existing([env_bash, path_bash, "/usr/bin/bash", "/bin/bash"])

    program_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LocalAppData", ""),
    ]
    git_candidates: list[str] = []
    for root in program_files:
        if not root:
            continue
        git_candidates.extend(
            [
                str(Path(root) / "Git" / "bin" / "bash.exe"),
                str(Path(root) / "Git" / "usr" / "bin" / "bash.exe"),
                str(Path(root) / "Programs" / "Git" / "bin" / "bash.exe"),
                str(Path(root) / "Programs" / "Git" / "usr" / "bin" / "bash.exe"),
            ]
        )

    # Prefer explicit/env + Git Bash. PATH bash is accepted only when it is not
    # the WSL launcher that cannot consume Windows paths.
    candidates = [env_bash, *git_candidates]
    if path_bash and not _is_wsl_launcher(path_bash):
        candidates.append(path_bash)
    candidates.append(path_bash)  # final fallback: fail with real host error
    return _existing(candidates)


def script_arg_for_bash(script: str, bash: str) -> str:
    if os.name != "nt":
        return script
    if _is_wsl_launcher(bash):
        return script
    # Git Bash accepts D:/repo/file.sh reliably. Plain D:\repo\file.sh is
    # parsed by bash with backslash escapes and becomes D:repofile.sh.
    return str(Path(script).resolve()).replace("\\", "/")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: vg-run-bash-hook.py <hook-script>", file=sys.stderr)
        return 64

    script = argv[1]
    stdin_bytes = sys.stdin.buffer.read()
    bashes = candidate_bashes()
    if not bashes:
        print(
            "VG hook runner: no bash found. Install Git Bash or set VG_BASH.",
            file=sys.stderr,
        )
        return 127

    bash = bashes[0]
    script_for_bash = script_arg_for_bash(script, bash)
    proc = subprocess.run(
        [bash, script_for_bash],
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.getcwd(),
        env=os.environ.copy(),
    )
    sys.stdout.buffer.write(proc.stdout)
    sys.stderr.buffer.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
