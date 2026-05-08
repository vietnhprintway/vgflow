"""Regression: VG harness must isolate `.vg/` per git worktree.

Concurrent worktrees on the same repo MUST NOT share .vg/events.db,
.vg/active-runs/, .vg/.session-context.json. Cross-session destructive
guard (v2.52.2) scans own worktree's active-runs only — relies on
REPO_ROOT resolving to the worktree root, not the main repo.

Resolution mechanism (`.claude/scripts/vg-orchestrator/_repo_root.py:37-39`):
walk up from __file__ looking for `.git`. Worktree has `.git` as a FILE
pointing to main's `.git/worktrees/<name>/`. `(.git).exists()` is True
for files, so walker stops at worktree root.

Failure mode this test guards against: someone refactors find_repo_root
to use `Path.cwd()` or to skip non-directory `.git` entries — both would
collapse all worktrees onto a single .vg/ directory and re-introduce
cross-worktree state collisions.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT_HELPER = Path(__file__).resolve().parent.parent / ".claude" / "scripts" / "vg-orchestrator" / "_repo_root.py"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def _resolve_repo_root_from_anchor(anchor_file: Path) -> Path:
    """Ask find_repo_root() what root resolves to when walking up from
    `anchor_file`. Anchor is the script location, NOT cwd — matches how
    the orchestrator invokes the resolver in production (anchored to
    `__file__`).

    Test isolation requirement: real production anchor would be
    `.claude/scripts/vg-orchestrator/_repo_root.py` inside the test's
    fake worktree. We synthesize that by passing `start_file` explicitly,
    avoiding the need to copy the entire scripts/ tree into each tmp dir.
    """
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(REPO_ROOT_HELPER.parent)!r}); "
        "from _repo_root import find_repo_root; "
        f"print(find_repo_root({str(anchor_file)!r}))"
    )
    result = _run([sys.executable, "-c", code], cwd=anchor_file.parent)
    assert result.returncode == 0, f"find_repo_root crashed: {result.stderr}"
    return Path(result.stdout.strip())


@pytest.fixture
def two_worktrees(tmp_path: Path):
    """Create a temp git repo + an additional worktree. Yield (main, wt2).

    Cleans up worktree on exit (git worktree remove + rm -rf).
    """
    main = tmp_path / "main_repo"
    main.mkdir()
    _run(["git", "init", "-q"], cwd=main).check_returncode()
    _run(["git", "config", "user.email", "test@vg.local"], cwd=main).check_returncode()
    _run(["git", "config", "user.name", "VG Test"], cwd=main).check_returncode()
    (main / "README.md").write_text("# main\n", encoding="utf-8")
    _run(["git", "add", "README.md"], cwd=main).check_returncode()
    _run(["git", "commit", "-q", "-m", "init"], cwd=main).check_returncode()

    wt2 = tmp_path / "wt2"
    res = _run(["git", "worktree", "add", "-q", "-b", "feature/wt2", str(wt2)], cwd=main)
    if res.returncode != 0:
        pytest.skip(f"git worktree add unsupported in this env: {res.stderr}")

    try:
        yield main, wt2
    finally:
        _run(["git", "worktree", "remove", "--force", str(wt2)], cwd=main)


def test_worktree_has_dotgit_as_file(two_worktrees):
    """Sanity: a git worktree's `.git` is a FILE pointing to main's .git/worktrees/<name>/."""
    main, wt2 = two_worktrees
    assert (main / ".git").is_dir(), "main repo .git must be a directory"
    wt_git = wt2 / ".git"
    assert wt_git.exists(), "worktree must have .git entry"
    assert wt_git.is_file(), "worktree .git must be a FILE (gitlink), not a directory"


def _fake_anchor(root: Path) -> Path:
    """Synthesize a deep script anchor inside `root` so the .git walker
    has multiple levels to ascend through (matches production's
    .claude/scripts/vg-orchestrator/ depth)."""
    deep = root / ".claude" / "scripts" / "vg-orchestrator"
    deep.mkdir(parents=True, exist_ok=True)
    anchor = deep / "_repo_root.py"
    anchor.write_text("# fake anchor for isolation test\n", encoding="utf-8")
    return anchor


def test_repo_root_resolves_to_worktree_root(two_worktrees):
    """find_repo_root must return the worktree's own root, NOT the main repo's root.

    This is the core invariant: each worktree gets its own .vg/ tree because
    REPO_ROOT differs per worktree.
    """
    main, wt2 = two_worktrees
    main_anchor = _fake_anchor(main)
    wt2_anchor = _fake_anchor(wt2)

    main_resolved = _resolve_repo_root_from_anchor(main_anchor)
    wt2_resolved = _resolve_repo_root_from_anchor(wt2_anchor)

    assert main_resolved.resolve() == main.resolve(), \
        f"main resolved to {main_resolved}, expected {main}"
    assert wt2_resolved.resolve() == wt2.resolve(), \
        f"worktree 2 resolved to {wt2_resolved}, expected {wt2}"
    assert main_resolved.resolve() != wt2_resolved.resolve(), \
        "main and worktree must NOT collapse to the same REPO_ROOT — concurrent .vg/ collision risk"


def test_vg_paths_diverge_per_worktree(two_worktrees):
    """Derived `.vg/` paths must differ between main and worktree.

    Guards against subtle regressions where REPO_ROOT diverges but downstream
    consumers (db.py, state.py) hardcode a different anchor.
    """
    main, wt2 = two_worktrees
    main_anchor = _fake_anchor(main)
    wt2_anchor = _fake_anchor(wt2)

    main_resolved = _resolve_repo_root_from_anchor(main_anchor)
    wt2_resolved = _resolve_repo_root_from_anchor(wt2_anchor)

    main_db = main_resolved / ".vg" / "events.db"
    wt2_db = wt2_resolved / ".vg" / "events.db"
    main_runs = main_resolved / ".vg" / "active-runs"
    wt2_runs = wt2_resolved / ".vg" / "active-runs"

    assert main_db != wt2_db, "events.db paths must differ per worktree"
    assert main_runs != wt2_runs, "active-runs/ paths must differ per worktree"


def test_vg_repo_root_env_override_works(tmp_path: Path):
    """VG_REPO_ROOT env var must take priority over .git walking.

    Used by tests + by users who deliberately want to point at a sibling
    repo. Without this escape hatch, monkeypatching repo root from tests
    is impossible.
    """
    fake_root = tmp_path / "fake_repo"
    fake_root.mkdir()
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(REPO_ROOT_HELPER.parent)!r}); "
        "from _repo_root import find_repo_root; "
        "print(find_repo_root())"
    )
    env = os.environ.copy()
    env["VG_REPO_ROOT"] = str(fake_root)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert Path(result.stdout.strip()).resolve() == fake_root.resolve()
