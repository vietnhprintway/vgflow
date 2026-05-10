"""v2.76.0 Stage 1.1 — resolver dual-mode (cwd-walk priority over __file__-walk).

For v3.0.0 global install: scripts in ~/.vgflow/ cannot walk __file__ to find
the user's project .git. Cwd-walk now first; __file__-walk fallback for legacy
project-local installs.

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 1.1
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT_HELPER = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "scripts"
    / "vg-orchestrator"
    / "_repo_root.py"
)


def _run(cmd, cwd, env=None):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _make_repo(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.mkdir()
    _run(["git", "init", "-q"], cwd=p)
    _run(["git", "config", "user.email", "test@vg.local"], cwd=p)
    _run(["git", "config", "user.name", "VG Test"], cwd=p)
    (p / "README.md").write_text("# test\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=p)
    _run(["git", "commit", "-q", "-m", "init"], cwd=p)
    return p


def _resolve(cwd: Path, env_extra: dict | None = None) -> Path:
    code = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT_HELPER.parent)!r}); "
        "from _repo_root import find_repo_root; print(find_repo_root())"
    )
    env = os.environ.copy()
    # Remove VG_REPO_ROOT/VG_PROJECT from inherited env unless explicitly set
    env.pop("VG_REPO_ROOT", None)
    env.pop("VG_PROJECT", None)
    if env_extra:
        env.update(env_extra)
    r = _run([sys.executable, "-c", code], cwd=cwd, env=env)
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    return Path(r.stdout.strip())


def test_cwd_walk_takes_priority_over_file_walk(tmp_path):
    """Resolver walks from cwd first → finds project's .git, NOT the .git
    of the script's anchor location. Critical for global install where
    script lives in ~/.vgflow/ but cwd = user project."""
    proj = _make_repo(tmp_path, "user_project")
    resolved = _resolve(proj)
    assert resolved.resolve() == proj.resolve(), (
        f"cwd-walk should resolve to {proj}, got {resolved}"
    )


def test_env_var_takes_top_priority(tmp_path):
    proj = _make_repo(tmp_path, "user_project")
    other = _make_repo(tmp_path, "other_project")
    resolved = _resolve(proj, env_extra={"VG_REPO_ROOT": str(other)})
    assert resolved.resolve() == other.resolve()


def test_vg_project_alias(tmp_path):
    """VG_PROJECT alias works same as VG_REPO_ROOT (NEW v2.76.0)."""
    proj = _make_repo(tmp_path, "user_project")
    other = _make_repo(tmp_path, "other_project")
    resolved = _resolve(proj, env_extra={"VG_PROJECT": str(other)})
    assert resolved.resolve() == other.resolve()


def test_falls_back_to_file_walk_when_cwd_outside_repo(tmp_path):
    """cwd outside any git repo → fall back to __file__-walk (legacy mode).
    Ensures backwards compat for project-local installs whose hooks fire
    from temp dirs without git ancestors."""
    not_a_repo = tmp_path / "noplace"
    not_a_repo.mkdir()
    resolved = _resolve(not_a_repo)
    # Either: file-walk found vgflow-repo (anchor traversal), OR final cwd-fallback
    expected_repo = REPO_ROOT_HELPER.resolve().parents[3]
    assert (
        resolved.resolve() == expected_repo.resolve()
        or resolved.resolve() == not_a_repo.resolve()
    ), f"expected vgflow-repo or {not_a_repo}, got {resolved}"
