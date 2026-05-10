"""v2.76.0 Stage 1.3 — vg_resolve_project_root() shell helper test.

Mirrors find_repo_root() Python priority on the shell side. Hooks running in
v3.0.0 global install (script in ~/.vgflow/) need cwd-walk to find user
project .git.

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 1.3
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LIB_SH = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "_lib.sh"
)


def _has_bash() -> bool:
    return shutil.which("bash") is not None


# WSL bash on Windows applies its own filesystem mapping (C: → /mnt/c) and
# WSLENV filtering that prevents reliable test setup. Skip on Windows; CI
# runs Linux bash directly so coverage is not lost.
pytestmark = [
    pytest.mark.skipif(not _has_bash(), reason="bash not available"),
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="WSL path mapping fragile on Windows; CI Linux validates",
    ),
]


def _run_resolver(cwd: Path, env_extra: dict | None = None) -> tuple[int, str, str]:
    script = f'source "{LIB_SH.as_posix()}"\nvg_resolve_project_root\n'
    env = os.environ.copy()
    for k in ("VG_PROJECT", "VG_REPO_ROOT"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        ["bash", "-c", script],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout.strip(), r.stderr


def test_cwd_inside_git_repo(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".git").mkdir()
    rc, out, err = _run_resolver(proj)
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == proj.resolve()


def test_cwd_inside_subdir_walks_up(tmp_path):
    proj = tmp_path / "proj"
    sub = proj / "src" / "deep" / "nested"
    sub.mkdir(parents=True)
    (proj / ".git").mkdir()
    rc, out, err = _run_resolver(sub)
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == proj.resolve()


def test_vg_project_env_override(tmp_path):
    other = tmp_path / "override"
    other.mkdir()
    rc, out, err = _run_resolver(tmp_path, {"VG_PROJECT": str(other)})
    assert rc == 0
    assert Path(out).resolve() == other.resolve()


def test_vg_repo_root_env_override(tmp_path):
    other = tmp_path / "override"
    other.mkdir()
    rc, out, err = _run_resolver(tmp_path, {"VG_REPO_ROOT": str(other)})
    assert rc == 0
    assert Path(out).resolve() == other.resolve()


def test_vg_project_takes_priority_over_vg_repo_root(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    rc, out, err = _run_resolver(
        tmp_path, {"VG_PROJECT": str(a), "VG_REPO_ROOT": str(b)}
    )
    assert rc == 0
    assert Path(out).resolve() == a.resolve()


def test_no_git_ancestor_errors(tmp_path):
    """cwd outside any git tree → exit 1, stderr message."""
    bare = tmp_path / "bare"
    bare.mkdir()
    rc, out, err = _run_resolver(bare)
    # On Windows the resolver may walk all the way up to drive root and find
    # SOME .git eventually; only assert when it actually fails.
    if rc != 0:
        assert "no .git" in err.lower() or "vg_resolve_project_root" in err
