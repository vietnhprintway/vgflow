"""v2.77.0 Stage 2.1 — resolve_vg_doc() dual-mode doc helper.

Resolves VG documentation files (ROADMAP.md, FOUNDATION.md, vg.config.md)
across new v3 layout (`.vg/<name>.md`) vs legacy root layout (`<name>.md`).
Priority: new layout first, legacy fallback.

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 2.1
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


HELPER = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "scripts"
    / "vg-orchestrator"
    / "_doc_resolver.py"
)


def _resolve(cwd: Path, name: str, env_extra: dict | None = None) -> tuple[int, str, str]:
    code = (
        f"import sys; sys.path.insert(0, {str(HELPER.parent)!r}); "
        "from _doc_resolver import resolve_vg_doc; "
        f"print(resolve_vg_doc({name!r}))"
    )
    env = os.environ.copy()
    for k in ("VG_REPO_ROOT", "VG_PROJECT", "VG_HOME"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout.strip(), r.stderr


def _make_repo(tmp_path: Path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    (p / ".git").mkdir()
    return p


def test_new_layout_takes_priority(tmp_path):
    """`.vg/ROADMAP.md` resolves over root `ROADMAP.md`."""
    proj = _make_repo(tmp_path)
    (proj / ".vg").mkdir()
    (proj / ".vg" / "ROADMAP.md").write_text("new\n", encoding="utf-8")
    (proj / "ROADMAP.md").write_text("legacy\n", encoding="utf-8")
    rc, out, err = _resolve(proj, "ROADMAP.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == (proj / ".vg" / "ROADMAP.md").resolve()


def test_legacy_root_used_when_new_absent(tmp_path):
    """Legacy `ROADMAP.md` at root used when `.vg/ROADMAP.md` missing."""
    proj = _make_repo(tmp_path)
    (proj / "ROADMAP.md").write_text("legacy\n", encoding="utf-8")
    rc, out, err = _resolve(proj, "ROADMAP.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == (proj / "ROADMAP.md").resolve()


def test_returns_new_layout_path_when_neither_exists(tmp_path):
    """Default future-write target = new layout `.vg/<name>.md`."""
    proj = _make_repo(tmp_path)
    rc, out, err = _resolve(proj, "ROADMAP.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == (proj / ".vg" / "ROADMAP.md").resolve()


def test_works_for_foundation_md(tmp_path):
    """Same dual-mode for FOUNDATION.md."""
    proj = _make_repo(tmp_path)
    (proj / ".vg").mkdir()
    (proj / ".vg" / "FOUNDATION.md").write_text("new\n", encoding="utf-8")
    rc, out, err = _resolve(proj, "FOUNDATION.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == (proj / ".vg" / "FOUNDATION.md").resolve()


def test_works_for_vg_config_md(tmp_path):
    """vg.config.md special case: new layout drops vg. prefix → .vg/config.md."""
    proj = _make_repo(tmp_path)
    (proj / ".vg").mkdir()
    (proj / ".vg" / "config.md").write_text("new\n", encoding="utf-8")
    (proj / "vg.config.md").write_text("legacy\n", encoding="utf-8")
    rc, out, err = _resolve(proj, "vg.config.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    # New layout: .vg/config.md (vg. prefix dropped since already inside .vg/)
    assert Path(out).resolve() == (proj / ".vg" / "config.md").resolve()


def test_vg_config_md_legacy_fallback(tmp_path):
    """vg.config.md legacy still found when no .vg/config.md."""
    proj = _make_repo(tmp_path)
    (proj / "vg.config.md").write_text("legacy\n", encoding="utf-8")
    rc, out, err = _resolve(proj, "vg.config.md", {"VG_PROJECT": str(proj)})
    assert rc == 0, f"err={err}"
    assert Path(out).resolve() == (proj / "vg.config.md").resolve()
