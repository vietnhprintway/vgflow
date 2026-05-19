"""B88 v4.65.1 — audit gaps from B87 IMPLEMENTATION-NOTES.html ship.

Post-ship audit (2026-05-20) found 4 critical gaps + 3 important:

  C1 — validator count_override_debt() only matched `- ` bullet (B85
       cli-forced format) but the PRIMARY production writer
       commands/vg/_shared/lib/override-debt.sh:log_override_debt() emits
       markdown TABLE rows starting with `| DEBT-`. Validator missed all
       real-world entries → gate never fired in production.

  C2 — CONFIG_DEBT_REGISTER_PATH env override not honored for custom
       register locations.

  C3 — commands/vg/build.md frontmatter `must_write` did not list
       IMPLEMENTATION-NOTES.html — Stop hook wouldn't catch missing-file
       case if blueprint stub-emit failed.

  C4 — vg-build-task-executor SKILL.md + waves-delegation.md did not
       propagate the append directive into spawned-agent prompts. Agents
       making implementation decisions were not aware they needed to log.

  I5 — LIFECYCLE.md did not list IMPLEMENTATION-NOTES.html.

  I7 — Validator did not detect raw `<script>` tags (XSS / payload
       injection if file rendered in stakeholder review) or guard the
       file's closing-tag chain (`</main></body></html>`) against
       append-corruption.

B88 ships fixes for all of the above.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "validators" / "verify-implementation-notes.py"
BUILD_MD = REPO_ROOT / "commands" / "vg" / "build.md"
LIFECYCLE_MD = REPO_ROOT / "commands" / "vg" / "LIFECYCLE.md"
AGENT_SKILL = REPO_ROOT / "agents" / "vg-build-task-executor" / "SKILL.md"
WAVES_DELEGATION = REPO_ROOT / "commands" / "vg" / "_shared" / "build" / "waves-delegation.md"


def _run_validator(repo: Path, phase: str, *extra,
                   env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "VG_REPO_ROOT": str(repo), "PYTHONIOENCODING": "utf-8"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--phase", phase, *extra],
        cwd=repo, capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace",
    )


def _mk_phase(tmp_path: Path, phase: str = "1.0") -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    pdir = repo / ".vg" / "phases" / f"{phase}-test"
    pdir.mkdir(parents=True)
    return repo, pdir


# ---------------------------------------------------------------------------
# C1: validator counts table-row OVERRIDE-DEBT entries
# ---------------------------------------------------------------------------

def test_b88_validator_counts_log_override_debt_table_rows(tmp_path: Path) -> None:
    """log_override_debt.sh table format must trigger gate."""
    repo, pdir = _mk_phase(tmp_path)
    od = repo / ".vg" / "OVERRIDE-DEBT.md"
    od.write_text("""# Override Debt Register

| ID | Severity | Phase | Step | Flag | Reason | Logged (UTC) | Status | Gate ID | Resolved | Legacy |
|----|----------|-------|------|------|--------|--------------|--------|---------|----------|--------|
| DEBT-20260520000001-1 | medium | 1.0 | build.wave-3 | `--allow-x` | test reason | 2026-05-20T00:00:00Z | OPEN | gate-x |  | false |
| DEBT-20260520000002-2 | high   | 1.0 | review.gate-y | `--skip-y` | another      | 2026-05-20T00:01:00Z | OPEN | gate-y |  | false |
""", encoding="utf-8")
    # No notes file → must BLOCK because 2 overrides exist
    proc = _run_validator(repo, "1.0")
    assert proc.returncode == 1, (
        f"expected BLOCK on table-row overrides; got rc={proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )
    # Sanity: stderr shows non-zero override count
    assert "override_debt=2" in proc.stderr


def test_b88_validator_counts_mixed_bullet_and_table(tmp_path: Path) -> None:
    """Mix of B85 cli-forced bullets + log_override_debt table rows."""
    repo, pdir = _mk_phase(tmp_path)
    od = repo / ".vg" / "OVERRIDE-DEBT.md"
    od.write_text("""# Override Debt Register

| DEBT-table-1 | high | 1.0 | step | `--flag` | reason | ts | OPEN | gid |  | false |

- 2026-05-20T00:00:00Z `wave.completed` run=abc phase=1.0 cli-forced reason='backfill'
- 2026-05-20T00:01:00Z `run.completed` run=def phase=1.0 cli-forced reason='backfill'
""", encoding="utf-8")
    proc = _run_validator(repo, "1.0")
    assert proc.returncode == 1
    # 1 table row + 2 bullet entries = 3
    assert "override_debt=3" in proc.stderr


def test_b88_validator_ignores_table_header(tmp_path: Path) -> None:
    """Markdown table header `| ID | Severity | ...` MUST NOT be counted."""
    repo, pdir = _mk_phase(tmp_path)
    od = repo / ".vg" / "OVERRIDE-DEBT.md"
    od.write_text("""# Override Debt Register

| ID | Severity | Phase | Step | Flag | Reason | Logged | Status | Gate | Resolved | Legacy |
|----|----------|-------|------|------|--------|--------|--------|------|----------|--------|
""", encoding="utf-8")
    # Header only, zero real entries → must PASS even without notes
    proc = _run_validator(repo, "1.0")
    assert proc.returncode == 0, (
        f"header-only register must NOT trigger gate; rc={proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )
    assert "override_debt=0" in proc.stdout


# ---------------------------------------------------------------------------
# C2: CONFIG_DEBT_REGISTER_PATH env override
# ---------------------------------------------------------------------------

def test_b88_validator_honors_config_debt_register_path(tmp_path: Path) -> None:
    repo, pdir = _mk_phase(tmp_path)
    custom = tmp_path / "custom-debt.md"
    custom.write_text("| DEBT-custom | high | 1.0 | s | `--f` | r | t | OPEN | g |  | false |\n",
                      encoding="utf-8")
    proc = _run_validator(repo, "1.0",
                          env_extra={"CONFIG_DEBT_REGISTER_PATH": str(custom)})
    assert proc.returncode == 1, (
        f"custom register path must be honored; rc={proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )
    assert "override_debt=1" in proc.stderr


# ---------------------------------------------------------------------------
# C3: build.md frontmatter must_write entry
# ---------------------------------------------------------------------------

def test_b88_build_md_frontmatter_lists_impl_notes() -> None:
    body = BUILD_MD.read_text(encoding="utf-8")
    # IMPLEMENTATION-NOTES.html appears in must_write list with content_min_bytes
    must_write_idx = body.index("must_write:")
    # Find next top-level frontmatter key OR end of frontmatter
    next_section = body.find("\n  must_emit_telemetry:", must_write_idx)
    if next_section < 0:
        next_section = body.find("\n---\n", must_write_idx)
    region = body[must_write_idx:next_section] if next_section > 0 else body[must_write_idx:]
    assert "IMPLEMENTATION-NOTES.html" in region, (
        "build.md must_write list missing IMPLEMENTATION-NOTES.html entry"
    )
    assert "content_min_bytes" in region


# ---------------------------------------------------------------------------
# C4: agent + delegation propagate directive
# ---------------------------------------------------------------------------

def test_b88_task_executor_agent_documents_append_rule() -> None:
    body = AGENT_SKILL.read_text(encoding="utf-8")
    assert "IMPLEMENTATION-NOTES.html" in body, (
        "vg-build-task-executor SKILL.md missing append directive"
    )
    assert "B87" in body
    assert "<article" in body, "agent must see the article syntax"
    # Reminds about all 4 criteria
    for cue in ("Decision beyond", "Change from the original requirement",
                "Tradeoff", "operator"):
        assert cue in body, f"agent missing criterion cue: {cue!r}"


def test_b88_waves_delegation_propagates_into_executor_prompt() -> None:
    body = WAVES_DELEGATION.read_text(encoding="utf-8")
    assert "IMPLEMENTATION-NOTES.html" in body, (
        "waves-delegation.md prompt template missing append directive"
    )
    assert "B87" in body
    # Must explicitly say the orchestrator appends it BEFORE spawn
    assert "BEFORE spawning" in body or "before spawning" in body.lower()


# ---------------------------------------------------------------------------
# I5: LIFECYCLE.md mentions artifact
# ---------------------------------------------------------------------------

def test_b88_lifecycle_md_lists_impl_notes() -> None:
    body = LIFECYCLE_MD.read_text(encoding="utf-8")
    assert "IMPLEMENTATION-NOTES.html" in body


# ---------------------------------------------------------------------------
# I7: HTML integrity (script tag + closing-tag preservation)
# ---------------------------------------------------------------------------

def _seed_overrides_and_notes(pdir: Path, repo: Path, notes_html: str) -> None:
    od = repo / ".vg" / "OVERRIDE-DEBT.md"
    od.write_text(
        "| DEBT-x | high | 1.0 | s | `--f` | r | t | OPEN | g |  | false |\n",
        encoding="utf-8",
    )
    (pdir / "IMPLEMENTATION-NOTES.html").write_text(notes_html, encoding="utf-8")


def test_b88_validator_blocks_on_script_tag(tmp_path: Path) -> None:
    repo, pdir = _mk_phase(tmp_path)
    long = "Detailed rationale. " * 5
    _seed_overrides_and_notes(pdir, repo, f"""<html><body><main>
<article data-task-id="task-01" data-category="decision">
  <h3>Decision: <code>x</code></h3>
  <section class="what"><h4>1.</h4><p>{long}</p></section>
  <section class="why"><h4>2.</h4><p class="na">N/A</p></section>
  <section class="tradeoff"><h4>3.</h4><p class="na">N/A</p></section>
  <section class="other"><h4>4.</h4><p class="na">N/A</p></section>
</article>
<script>alert(1)</script>
</main></body></html>""")
    proc = _run_validator(repo, "1.0")
    assert proc.returncode == 2, (
        f"script tag must trigger structural BLOCK; got {proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )
    assert "script" in proc.stderr.lower()


def test_b88_validator_blocks_on_missing_closing_tag(tmp_path: Path) -> None:
    repo, pdir = _mk_phase(tmp_path)
    long = "Detailed rationale. " * 5
    # Missing </main></body></html> — append-corruption simulation
    _seed_overrides_and_notes(pdir, repo, f"""<html><body><main>
<article data-task-id="task-01" data-category="decision">
  <h3>Decision: <code>x</code></h3>
  <section class="what"><h4>1.</h4><p>{long}</p></section>
  <section class="why"><h4>2.</h4><p class="na">N/A</p></section>
  <section class="tradeoff"><h4>3.</h4><p class="na">N/A</p></section>
  <section class="other"><h4>4.</h4><p class="na">N/A</p></section>
</article>""")
    proc = _run_validator(repo, "1.0")
    assert proc.returncode == 2
    assert "closing tag" in proc.stderr.lower() or "</main>" in proc.stderr


# ---------------------------------------------------------------------------
# Mirror parity (re-assert after B88 edits)
# ---------------------------------------------------------------------------

def test_b88_validator_mirror_byte_identical() -> None:
    canonical = REPO_ROOT / "scripts" / "validators" / "verify-implementation-notes.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "validators" / "verify-implementation-notes.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_b88_agent_mirror_byte_identical() -> None:
    canonical = AGENT_SKILL
    mirror = REPO_ROOT / ".claude" / "agents" / "vg-build-task-executor" / "SKILL.md"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_b88_waves_delegation_mirror_byte_identical() -> None:
    canonical = WAVES_DELEGATION
    mirror = REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "build" / "waves-delegation.md"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_b88_lifecycle_mirror_byte_identical() -> None:
    canonical = LIFECYCLE_MD
    mirror = REPO_ROOT / ".claude" / "commands" / "vg" / "LIFECYCLE.md"
    assert canonical.read_bytes() == mirror.read_bytes()
