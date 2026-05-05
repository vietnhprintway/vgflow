from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / ".claude" / "scripts" / "validators" / "verify-container-hardening.py"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        encoding="utf-8",
        errors="replace",
    )


def test_auto_detect_ignores_node_modules_dockerfiles(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "recast" / ".devcontainer"
    vendored.mkdir(parents=True)
    (vendored / "Dockerfile").write_text("FROM node:latest\n", encoding="utf-8")

    result = _run(["--project-root", str(tmp_path), "--json"])

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert data["dockerfile"] is None


def test_auto_detect_keeps_project_dockerfile_priority(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "recast" / ".devcontainer"
    vendored.mkdir(parents=True)
    (vendored / "Dockerfile").write_text("FROM node:latest\n", encoding="utf-8")
    project = tmp_path / "Dockerfile"
    project.write_text(
        "FROM node:20-alpine\nWORKDIR /app\nUSER node\nHEALTHCHECK CMD true\n",
        encoding="utf-8",
    )

    result = _run(["--project-root", str(tmp_path), "--json"])

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert Path(data["dockerfile"]) == project.resolve()


def test_non_tty_output_defaults_to_json(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ${VARIANT}\n", encoding="utf-8")

    result = _run(["--project-root", str(tmp_path)])

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["block_count"] >= 1
    assert data["dockerfile"] == str(dockerfile.resolve())
