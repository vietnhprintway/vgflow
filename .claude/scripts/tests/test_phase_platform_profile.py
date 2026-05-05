from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "commands" / "vg" / "_shared" / "lib" / "phase-profile.sh"


def _detect(phase_dir: Path, fallback: str = "web-fullstack") -> str:
    script = (
        f"source {str(HELPER)!r}; "
        f"detect_phase_platform_profile {str(phase_dir)!r} {fallback!r}"
    )
    result = subprocess.run(
        ["bash", "-lc", script],
        text=True,
        capture_output=True,
        timeout=5,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_detects_platform_frontmatter_backend_only(tmp_path: Path) -> None:
    phase = tmp_path / "04.2-pricing"
    phase.mkdir()
    (phase / "PLAN.md").write_text(
        textwrap.dedent(
            """\
            ---
            phase: "4.2"
            profile: feature
            platform: web-backend-only
            ---

            # Plan
            """
        ),
        encoding="utf-8",
    )

    assert _detect(phase) == "web-backend-only"


def test_detects_test_goals_backend_only_profile(tmp_path: Path) -> None:
    phase = tmp_path / "04.2-pricing"
    phase.mkdir()
    (phase / "TEST-GOALS.md").write_text(
        "Profile: `web-backend-only`. NO `surface: ui` goals.\n",
        encoding="utf-8",
    )

    assert _detect(phase) == "web-backend-only"


def test_ui_scope_false_downgrades_fullstack_project_phase(tmp_path: Path) -> None:
    phase = tmp_path / "04.2-pricing"
    phase.mkdir()
    (phase / ".ui-scope.json").write_text(
        json.dumps({"has_ui": False}),
        encoding="utf-8",
    )

    assert _detect(phase, "web-fullstack") == "web-backend-only"
