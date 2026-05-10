"""v2.77.0 Stage 2.1 — dual-mode VG doc resolver.

Resolves VG documentation files (ROADMAP.md, FOUNDATION.md, vg.config.md)
across new v3 layout (`.vg/<name>.md`) vs legacy root layout (`<name>.md`).

For v3.0.0 migration: callers can switch to `resolve_vg_doc("ROADMAP.md")`
without caring whether the project has migrated yet — the helper transparently
falls back to legacy root location while it exists.

Special case: `vg.config.md` legacy filename → `.vg/config.md` in new layout
(the `vg.` prefix is redundant once the file lives inside `.vg/`).

Resolution priority:
  1. New layout: `${VG_PROJECT}/.vg/<name>.md` (or `config.md` for vg.config.md)
  2. Legacy: `${VG_PROJECT}/<name>.md`
  3. Default for future writes: new layout path

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 2.1
"""
from __future__ import annotations

from pathlib import Path

from _repo_root import find_repo_root


def _new_layout_name(name: str) -> str:
    """Map legacy doc name to new-layout name. vg.config.md → config.md."""
    if name == "vg.config.md":
        return "config.md"
    return name


def resolve_vg_doc(name: str, start_file: str | None = None) -> Path:
    """Return absolute Path to a VG doc, preferring new `.vg/` layout.

    Args:
        name: Legacy doc filename (ROADMAP.md, FOUNDATION.md, vg.config.md).
        start_file: Forwarded to find_repo_root() for project resolution.

    Returns:
        Path to the doc. If neither new nor legacy exists, returns the
        new-layout path (intended for future writes).
    """
    project = find_repo_root(start_file)
    new = project / ".vg" / _new_layout_name(name)
    legacy = project / name
    if new.exists():
        return new
    if legacy.exists():
        return legacy
    # Default for future writes: new layout
    return new
