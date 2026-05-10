"""v2.77.0 Stage 2.2 — .gitignore v3 whitelist generator.

Generates `.gitignore` patterns that ignore `.vg/*` by default but whitelist
tracked files (ROADMAP, FOUNDATION, config, OVERRIDE-DEBT, .install-target,
phases/, bootstrap/{ACCEPTED,REJECTED,RETRACTED,CONSOLIDATION-LOG,MEMORY}.md,
bootstrap/rules/, bootstrap/overlay.yml, bootstrap/topics/, deploy/STATE.json,
deploy/history.jsonl).

Re-ignores untracked subpaths (events.db, runs/, deploy-log.{env}.txt, etc.).

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 2.2
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "scripts"
    / "migrate"
    / "generate-gitignore-v3.py"
)


def _run() -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout, r.stderr


def test_script_exists():
    assert SCRIPT.exists(), f"missing {SCRIPT}"


def test_emits_blanket_ignore_first():
    rc, out, err = _run()
    assert rc == 0, f"err={err}"
    assert ".vg/*" in out, "blanket ignore missing"


def test_whitelists_tracked_docs():
    rc, out, _ = _run()
    assert rc == 0
    for entry in [
        "!.vg/ROADMAP.md",
        "!.vg/FOUNDATION.md",
        "!.vg/config.md",
        "!.vg/OVERRIDE-DEBT.md",
        "!.vg/.install-target",
    ]:
        assert entry in out, f"missing whitelist: {entry}"


def test_whitelists_phases_tree():
    rc, out, _ = _run()
    assert rc == 0
    for entry in ["!.vg/phases/", "!.vg/phases/**/*.md", "!.vg/phases/**/*.json"]:
        assert entry in out, f"missing phases whitelist: {entry}"


def test_whitelists_bootstrap_tracked():
    rc, out, _ = _run()
    assert rc == 0
    for entry in [
        "!.vg/bootstrap/",
        "!.vg/bootstrap/ACCEPTED.md",
        "!.vg/bootstrap/REJECTED.md",
        "!.vg/bootstrap/RETRACTED.md",
        "!.vg/bootstrap/CONSOLIDATION-LOG.md",
        "!.vg/bootstrap/MEMORY.md",
        "!.vg/bootstrap/rules/",
        "!.vg/bootstrap/rules/*.md",
        "!.vg/bootstrap/overlay.yml",
        "!.vg/bootstrap/topics/",
        "!.vg/bootstrap/topics/*.md",
    ]:
        assert entry in out, f"missing bootstrap whitelist: {entry}"


def test_whitelists_deploy_tracked():
    rc, out, _ = _run()
    assert rc == 0
    for entry in [
        "!.vg/deploy/",
        "!.vg/deploy/STATE.json",
        "!.vg/deploy/history.jsonl",
    ]:
        assert entry in out, f"missing deploy whitelist: {entry}"


def test_re_ignores_untracked_subpaths():
    rc, out, _ = _run()
    assert rc == 0
    for entry in [
        ".vg/phases/**/.runtime-state.json",
        ".vg/bootstrap/CANDIDATES.md",
        ".vg/bootstrap/state.json",
        ".vg/bootstrap/.consolidation.lock",
        ".vg/deploy/deploy-log.*",
        ".vg/deploy/.deploy.lock",
    ]:
        assert entry in out, f"missing re-ignore: {entry}"


def test_output_is_idempotent():
    """Running twice produces identical output."""
    rc1, out1, _ = _run()
    rc2, out2, _ = _run()
    assert rc1 == rc2 == 0
    assert out1 == out2
