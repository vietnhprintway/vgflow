"""v2.82.1 Stage 6.5 — auto-detect phase context for deploy.

`/vg:deploy` (v3.0.0) drops the mandatory `<phase>` positional arg. When
absent, we derive `phase_context` from runtime signals so the resulting
deploy event still has audit lineage. Runtime gates (env preference,
test deploy step) MUST NOT branch on this — it's audit-only.

Detection priority:
  1. Explicit override (caller passed --phase=<N>)
  2. .vg/active-runs/*.json — newest file's `phase` field
  3. Git branch name pattern `phase-<N>` or `vg/<N>` or `vg-<N>`
  4. Last `/vg:scope` run row from events.db (if available)
  5. None — caller persists deploy without phase_context

All detection branches are best-effort + soft-fail; never raise.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


_BRANCH_PHASE_PATTERNS = [
    re.compile(r"^phase[-_/](?P<phase>[0-9]+(?:\.[0-9]+)*)"),
    re.compile(r"^vg[-_/](?P<phase>[0-9]+(?:\.[0-9]+)*)"),
    re.compile(r"^p(?P<phase>[0-9]+(?:\.[0-9]+)*)$"),
]


def detect_phase_context(
    project_root: Path | str,
    *,
    override: str | None = None,
) -> str | None:
    """Return phase number string (e.g., "6", "12.4") or None.

    Args:
        override: Explicit phase passed by caller (CLI flag); short-circuits.
    """
    if override:
        return str(override).strip() or None

    proj = Path(project_root).resolve()

    detected = _from_active_runs(proj)
    if detected:
        return detected

    detected = _from_git_branch(proj)
    if detected:
        return detected

    detected = _from_last_scope_event(proj)
    if detected:
        return detected

    return None


def _from_active_runs(project_root: Path) -> str | None:
    """Read newest active run JSON (mtime) and pluck `phase`."""
    active_dir = project_root / ".vg" / "active-runs"
    if not active_dir.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for p in active_dir.glob("*.json"):
        try:
            candidates.append((p.stat().st_mtime, p))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    for _, path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        phase = data.get("phase") if isinstance(data, dict) else None
        if phase:
            return str(phase).strip() or None
    return None


def _from_git_branch(project_root: Path) -> str | None:
    """Match current branch name against phase patterns."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not out or out == "HEAD":
        return None
    for pat in _BRANCH_PHASE_PATTERNS:
        m = pat.match(out)
        if m:
            return m.group("phase")
    return None


def _from_last_scope_event(project_root: Path) -> str | None:
    """Query `.vg/events.db` for the most recent `/vg:scope` runs row."""
    db_path = project_root / ".vg" / "events.db"
    if not db_path.exists():
        return None
    try:
        import sqlite3  # noqa: WPS433 — optional dep, std-lib
    except ImportError:
        return None
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.execute(
                """
                SELECT phase
                  FROM runs
                 WHERE command = 'vg:scope'
                   AND phase IS NOT NULL
                   AND phase != ''
              ORDER BY started_at DESC
                 LIMIT 1
                """
            )
            row = cur.fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    phase = row[0]
    return str(phase).strip() if phase else None
