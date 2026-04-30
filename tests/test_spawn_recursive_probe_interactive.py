"""Interactive probe-mode prompt at Phase 2b-2.5 (Task 26g).

Behavior:
  - --non-interactive flag => skip prompt, use --probe-mode value (or default).
  - When --probe-mode is supplied, never prompt (CLI is authoritative).
  - When --probe-mode is omitted AND interactive => stdin prompt
    `[a]uto / [m]anual / [h]ybrid / [s]kip?`. Default 'a' on Enter.
  - 's' (skip) writes .recursive-probe-skipped.yaml.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "spawn_recursive_probe.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "recursive-probe-smoke"


def _seed(tmp_path: Path) -> Path:
    phase = tmp_path / "phase"
    shutil.copytree(FIXTURE, phase)
    (phase / ".phase-profile").write_text(
        "phase_profile: feature\nsurface: ui\n", encoding="utf-8"
    )
    (phase / "scan-admin.json").write_text(json.dumps({
        "view": "/admin",
        "elements_total": 1,
        "results": [
            {"selector": "button#x", "network": [{"method": "POST", "url": "/api/x"}]}
        ],
    }), encoding="utf-8")
    return phase


def _run(phase: Path, *, stdin: str | None, extra: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--phase-dir", str(phase), "--dry-run", "--json", *extra],
        capture_output=True, text=True, input=stdin,
    )


def test_non_interactive_skips_prompt(tmp_path: Path) -> None:
    """With --non-interactive and no --probe-mode, default 'auto' applies, no stdin read."""
    phase = _seed(tmp_path)
    r = _run(phase, stdin="", extra=["--non-interactive"])
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["probe_mode"] == "auto"


def test_probe_mode_cli_wins_over_prompt(tmp_path: Path) -> None:
    """Explicit --probe-mode bypasses prompt even without --non-interactive."""
    phase = _seed(tmp_path)
    # No stdin provided — would hang if prompt were shown.
    r = _run(phase, stdin="", extra=["--probe-mode", "manual", "--non-interactive"])
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["probe_mode"] == "manual"


def test_interactive_default_auto_on_enter(tmp_path: Path) -> None:
    """Interactive run, just press Enter → defaults to 'auto'."""
    phase = _seed(tmp_path)
    r = _run(phase, stdin="\n", extra=[])
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(r.stdout)
    assert payload["probe_mode"] == "auto"


def test_interactive_manual_choice(tmp_path: Path) -> None:
    phase = _seed(tmp_path)
    r = _run(phase, stdin="m\n", extra=[])
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(r.stdout)
    assert payload["probe_mode"] == "manual"


def test_interactive_skip_choice_writes_evidence(tmp_path: Path) -> None:
    phase = _seed(tmp_path)
    r = _run(phase, stdin="s\n", extra=[])
    assert r.returncode == 0, r.stderr + r.stdout
    payload = json.loads(r.stdout)
    assert payload["eligibility"]["skipped_via_override"] is True
    assert (phase / ".recursive-probe-skipped.yaml").is_file()
