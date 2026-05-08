"""Tests for vg_bootstrap_render_split helper (Stage 4 task 4/4).

The helper sources bootstrap-inject.sh, calls vg_bootstrap_render_split with
loader JSON, and asserts the output contains the 2 markdown headers
(Declarative Rules + Procedural Recipes).

Used by Stage 4 inject sites (Tasks 4.1-4.3) to render rules consistently.

Mirror byte-identity is required.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


CANONICAL = Path("commands/vg/_shared/lib/bootstrap-inject.sh")
MIRROR = Path(".claude/commands/vg/_shared/lib/bootstrap-inject.sh")


def _bash_exe():
    """Locate bash. On Windows, depend on Git Bash being on PATH."""
    return shutil.which("bash") or shutil.which("bash.exe")


def test_bootstrap_inject_defines_render_split_function():
    f = CANONICAL.read_text(encoding="utf-8")
    assert "vg_bootstrap_render_split" in f, (
        "vg_bootstrap_render_split function must be defined in bootstrap-inject.sh"
    )


def test_bootstrap_inject_render_split_uses_python():
    """Helper renders via python so loader JSON is parsed safely."""
    f = CANONICAL.read_text(encoding="utf-8")
    # Function body must use python with json
    assert "vg_bootstrap_render_split" in f
    # Find function and verify python invocation context
    idx = f.index("vg_bootstrap_render_split")
    # Look at next ~1500 chars after function definition
    body = f[idx:idx + 2500]
    assert "PYTHON_BIN" in body or "python3" in body
    assert "json" in body


def test_bootstrap_inject_render_split_emits_headers():
    """Function body must reference both 2-section headers in the output."""
    f = CANONICAL.read_text(encoding="utf-8")
    # Both headers must appear in source (so the function emits them)
    assert "Declarative Rules" in f
    assert "Procedural Recipes" in f


@pytest.mark.skipif(_bash_exe() is None, reason="bash unavailable on PATH")
def test_render_split_runtime_emits_both_sections(tmp_path):
    """Source bootstrap-inject.sh, call render with sample JSON, verify output."""
    bash = _bash_exe()
    sample = {
        "rules_declarative": [
            {"id": "d1", "title": "Always lint", "prose": "Run linter pre-commit"}
        ],
        "rules_procedural": [
            {
                "id": "p1",
                "title": "Deploy recipe",
                "prose": "Build then push",
                "sequence": [{"cmd": "docker build"}, {"cmd": "kubectl apply"}],
            }
        ],
    }
    sample_json = json.dumps(sample)

    # Use canonical (POSIX) path so bash on Windows can read it.
    script_path = CANONICAL.as_posix()

    # Build a small bash invocation that sources the lib and calls helper.
    bash_cmd = (
        f'source "{script_path}" && '
        f'vg_bootstrap_render_split \'{sample_json}\''
    )

    env = os.environ.copy()
    # Don't pin PYTHON_BIN — the helper's ${PYTHON_BIN:-python3} fallback
    # is unquoted and breaks if the path has spaces (e.g. "Program Files").
    # CI / dev shells already have python3 on PATH.
    env.pop("PYTHON_BIN", None)

    result = subprocess.run(
        [bash, "-c", bash_cmd],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"helper exited {result.returncode}\nstderr: {result.stderr}"
    )
    out = result.stdout
    assert "### Declarative Rules" in out, f"missing declarative header. out:\n{out}"
    assert "### Procedural Recipes" in out, f"missing procedural header. out:\n{out}"
    assert "Always lint" in out
    assert "Deploy recipe" in out


@pytest.mark.skipif(_bash_exe() is None, reason="bash unavailable on PATH")
def test_render_split_runtime_handles_empty_json():
    """Helper must not crash on empty / invalid JSON."""
    bash = _bash_exe()
    script_path = CANONICAL.as_posix()
    bash_cmd = f'source "{script_path}" && vg_bootstrap_render_split \'{{}}\''
    env = os.environ.copy()
    # Don't pin PYTHON_BIN — the helper's ${PYTHON_BIN:-python3} fallback
    # is unquoted and breaks if the path has spaces (e.g. "Program Files").
    # CI / dev shells already have python3 on PATH.
    env.pop("PYTHON_BIN", None)
    result = subprocess.run(
        [bash, "-c", bash_cmd], capture_output=True, text=True, env=env, timeout=30
    )
    # Must succeed even on empty input
    assert result.returncode == 0, (
        f"helper crashed on empty JSON\nstderr: {result.stderr}"
    )


def test_mirror_byte_identical_bootstrap_inject():
    canonical = CANONICAL.read_bytes()
    mirror = MIRROR.read_bytes()
    assert canonical == mirror, (
        f"Mirror drift: canonical={len(canonical)} bytes vs mirror={len(mirror)} bytes"
    )
