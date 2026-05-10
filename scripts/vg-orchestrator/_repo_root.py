"""Shared repo-root resolver for orchestrator + validators.

v2.76.0 (Stage 1.1 of v3.0.0 plan): swap cwd-walk priority above __file__-walk
so that scripts living outside the user's project (e.g. ~/.vgflow/ in v3
global install) still resolve to the user's project root via cwd.

Earlier bug context: `Path(os.environ.get("VG_REPO_ROOT") or os.getcwd())`
fallback used `cwd` when env unset. A subprocess spawned from a subdirectory
would compute `.vg/events.db` relative to that subdir, creating rogue empty
DBs. Observed in practice at `.claude/scripts/.vg/` and
`.claude/scripts/vg-orchestrator/.vg/`. The cwd-walk added in v2.76.0 walks
ANCESTORS for `.git/`, so it never resolves to a subdir without git.

Resolution priority:
  1. `VG_REPO_ROOT` (legacy) or `VG_PROJECT` (v2.76.0+) env var — explicit, trusted.
  2. Walk up from cwd looking for `.git/` — works for global install + most
     project-local invocations where hooks/skills fire with cwd = project root.
  3. Walk up from `__file__` of the caller looking for `.git/` — legacy
     fallback for scripts launched outside any git ancestor (e.g. temp dirs).
  4. Fallback: `os.getcwd()` with stderr warning — signals likely rogue DB.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def find_repo_root(start_file: str | None = None) -> Path:
    """Return the repo root as an absolute Path.

    Args:
        start_file: Optional `__file__` of the caller. Used by the
          __file__-walk fallback (priority 3) when cwd-walk fails. Defaults
          to this helper's own location.
    """
    # 1. Explicit env (VG_REPO_ROOT or v2.76.0+ VG_PROJECT alias)
    env = os.environ.get("VG_REPO_ROOT") or os.environ.get("VG_PROJECT")
    if env:
        return Path(env).resolve()

    # 2. Walk from cwd (v2.76.0 — works for global install where script is
    #    outside the user's project tree)
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate

    # 3. Walk from __file__ anchor (legacy fallback for project-local installs
    #    whose scripts launch from temp dirs without git ancestors)
    anchor = (
        Path(start_file).resolve().parent
        if start_file
        else Path(__file__).resolve().parent
    )
    for candidate in [anchor, *anchor.parents]:
        if (candidate / ".git").exists():
            return candidate

    # 4. Last-resort cwd fallback with stderr warning
    print(
        "WARN: vg helper could not locate repo root "
        "(no VG_REPO_ROOT/VG_PROJECT, no .git/ via cwd-walk or "
        f"__file__-walk anchor={anchor}, cwd={cwd}). Falling back to cwd — "
        "this likely creates rogue .vg/ artifacts.",
        file=sys.stderr,
    )
    return Path.cwd().resolve()
