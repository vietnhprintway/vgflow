"""B87 v4.65.0 — IMPLEMENTATION-NOTES.html validator + wiring tests.

User dogfood request (2026-05-19): capture AI decisions/tradeoffs/deviations
in a per-phase HTML artifact. VG previously had no place for:
  1. Decisions AI made beyond specs
  2. Changes from original requirements
  3. Tradeoffs considered
  4. Anything else operator needs to know

Existing artifacts cover adjacent concerns (OVERRIDE-DEBT.md for forced
override deviations, .final-review/verdict.md for cross-task gaps,
reflection-*.yaml for post-hoc learnings) but NOT implementation-time
AI rationale.

B87 ships:
  - Template HTML at commands/vg/_shared/templates/IMPLEMENTATION-NOTES-template.html
  - Blueprint close.md copies template to ${PHASE_DIR}/IMPLEMENTATION-NOTES.html
  - Build waves-overview B72 directive extended with per-task append rule
  - Build close.md STEP 7.2 wires verify-implementation-notes.py validator
  - Hard BLOCK on OVERRIDE-DEBT non-empty + notes empty (B87 enforcement)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "commands" / "vg" / "_shared" / "templates" / "IMPLEMENTATION-NOTES-template.html"
VALIDATOR = REPO_ROOT / "scripts" / "validators" / "verify-implementation-notes.py"
BLUEPRINT_CLOSE = REPO_ROOT / "commands" / "vg" / "_shared" / "blueprint" / "close.md"
WAVES_OVERVIEW = REPO_ROOT / "commands" / "vg" / "_shared" / "build" / "waves-overview.md"
BUILD_CLOSE = REPO_ROOT / "commands" / "vg" / "_shared" / "build" / "close.md"


# ---------------------------------------------------------------------------
# Template + validator artifact presence
# ---------------------------------------------------------------------------

def test_b87_template_exists_with_required_sections() -> None:
    assert TEMPLATE.is_file(), f"template missing: {TEMPLATE}"
    body = TEMPLATE.read_text(encoding="utf-8")
    # 4 user-requested criteria reflected as section keys
    for cls in ("class=\"what\"", "class=\"why\"",
                "class=\"tradeoff\"", "class=\"other\""):
        assert cls in body, f"section {cls!r} missing in template"
    # Append syntax documented in HTML comment
    assert "HOW TO APPEND" in body, "append syntax doc missing"
    assert "data-category" in body, "category data-attr missing"
    # Empty-state placeholder so a freshly-stubbed file is well-formed
    assert "empty-state" in body or "No implementation notes yet" in body


def test_b87_blueprint_close_copies_template() -> None:
    body = BLUEPRINT_CLOSE.read_text(encoding="utf-8")
    assert "IMPLEMENTATION-NOTES.html" in body, (
        "blueprint/close.md must reference IMPLEMENTATION-NOTES.html"
    )
    assert "IMPLEMENTATION-NOTES-template.html" in body, (
        "blueprint/close.md must reference the template"
    )
    # Idempotent guard
    assert "if [ ! -f \"$IMPL_NOTES_DST\" ]" in body or "if [ ! -f" in body


def test_b87_waves_overview_has_append_directive() -> None:
    body = WAVES_OVERVIEW.read_text(encoding="utf-8")
    assert "B87" in body, "waves-overview missing B87 marker"
    assert "IMPLEMENTATION-NOTES.html" in body, (
        "waves directive must point AI at IMPLEMENTATION-NOTES.html"
    )
    # Cover all 4 user criteria explicitly
    assert "Decision beyond" in body or "beyond what specs" in body
    assert "Change from the original requirement" in body or "deviation" in body
    assert "Tradeoff" in body
    assert "anything else" in body.lower() or "operator needs to know" in body.lower()


def test_b87_build_close_wires_validator_before_run_complete() -> None:
    body = BUILD_CLOSE.read_text(encoding="utf-8")
    assert "verify-implementation-notes.py" in body, (
        "build/close.md must wire the validator"
    )
    # Ordering: validator MUST appear before the run-complete invocation
    val_idx = body.index("verify-implementation-notes.py")
    rc_idx = body.index("vg-orchestrator run-complete\nRUN_RC=$?")
    assert val_idx < rc_idx, "validator must run BEFORE run-complete"
    # 3-tier fallback present
    assert "VG_SCRIPT_ROOT" in body
    assert ".claude/scripts/validators/verify-implementation-notes.py" in body


# ---------------------------------------------------------------------------
# Validator behavioral
# ---------------------------------------------------------------------------

def _mk_phase(tmp_path: Path, phase: str = "9.9",
              override_count: int = 0,
              verdict_gaps: list[str] | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    pdir = repo / ".vg" / "phases" / f"{phase}-test"
    pdir.mkdir(parents=True)
    # OVERRIDE-DEBT lives at repo .vg/ root per the helper canonical path.
    # B85 cli-forced format: line starts `- <ts> <event_type-in-backticks> ...`.
    # B88: validator requires backticks to distinguish entries from prose
    # bullets in header text.
    if override_count > 0:
        od = repo / ".vg" / "OVERRIDE-DEBT.md"
        od.write_text(
            "# Override Debt\n\n" + "\n".join(
                f"- 2026-05-19 `example.event` run=abc phase={phase} cli-forced reason='test'"
                for _ in range(override_count)
            ) + "\n",
            encoding="utf-8",
        )
    if verdict_gaps:
        fr = pdir / ".final-review"
        fr.mkdir()
        gaps_yaml = ", ".join(f'"{g}"' for g in verdict_gaps)
        (fr / "verdict.md").write_text(
            f"---\nverdict: PARTIAL\ngaps: [{gaps_yaml}]\n---\nbody\n",
            encoding="utf-8",
        )
    return pdir


def _run_validator(repo: Path, phase: str, *extra) -> subprocess.CompletedProcess:
    env = {**os.environ, "VG_REPO_ROOT": str(repo), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--phase", phase, *extra],
        cwd=repo, capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace",
    )


def test_b87_validator_pass_when_no_overrides_no_gaps(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=0, verdict_gaps=None)
    repo = pdir.parents[2]  # .vg/phases/<dir> → repo
    # No notes file — still PASS since nothing to document
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"


def test_b87_validator_block_when_overrides_exist_but_no_notes(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=2)
    repo = pdir.parents[2]
    # Empty notes file (stub-only)
    notes = pdir / "IMPLEMENTATION-NOTES.html"
    notes.write_text(
        "<html><body><main><p class='empty-state'>No notes</p></main></body></html>",
        encoding="utf-8",
    )
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 1, f"expected exit 1; got {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "no valid <article>" in proc.stderr or "no valid" in proc.stderr.lower()


def test_b87_validator_pass_with_valid_article(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=1)
    repo = pdir.parents[2]
    long_text = "Detailed rationale for the decision. " * 5  # ≥50 chars easily
    notes_content = f"""<html><body><main>
<article data-task-id="task-01" data-ts="2026-05-19T00:00:00Z" data-category="decision">
  <h3>Decision: <code>auth flow</code></h3>
  <section class="what"><h4>1. What AI decided</h4><p>{long_text}</p></section>
  <section class="why"><h4>2. Change</h4><p class="na">N/A</p></section>
  <section class="tradeoff"><h4>3. Tradeoff</h4><p class="na">N/A</p></section>
  <section class="other"><h4>4. Other</h4><p class="na">N/A</p></section>
</article>
</main></body></html>"""
    (pdir / "IMPLEMENTATION-NOTES.html").write_text(notes_content, encoding="utf-8")
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 0, (
        f"expected PASS; got rc={proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_b87_validator_block_on_shallow_article(tmp_path: Path) -> None:
    """Articles with all-N/A or <50-char sections must NOT count as valid."""
    pdir = _mk_phase(tmp_path, "9.9", override_count=1)
    repo = pdir.parents[2]
    notes_content = """<html><body><main>
<article data-task-id="task-01" data-category="note">
  <h3>Decision: <code>shallow</code></h3>
  <section class="what"><h4>1.</h4><p>short</p></section>
  <section class="why"><h4>2.</h4><p class="na">N/A</p></section>
  <section class="tradeoff"><h4>3.</h4><p class="na">N/A</p></section>
  <section class="other"><h4>4.</h4><p class="na">N/A</p></section>
</article>
</main></body></html>"""
    (pdir / "IMPLEMENTATION-NOTES.html").write_text(notes_content, encoding="utf-8")
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 1, "shallow article must NOT bypass gate"


def test_b87_validator_pass_with_context_waiver(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=5)
    repo = pdir.parents[2]
    (pdir / "CONTEXT.md").write_text(
        "# Context\n\nimplementation_notes_waiver: true\n",
        encoding="utf-8",
    )
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 0, f"waiver bypass failed: {proc.stderr}"


def test_b87_validator_pass_with_allow_shortfall_flag(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=2)
    repo = pdir.parents[2]
    proc = _run_validator(repo, "9.9", "--allow-shortfall")
    assert proc.returncode == 0, f"shortfall flag failed: {proc.stderr}"


def test_b87_validator_block_on_verdict_gaps_without_notes(tmp_path: Path) -> None:
    pdir = _mk_phase(tmp_path, "9.9", override_count=0,
                     verdict_gaps=["missing-test", "doc-drift"])
    repo = pdir.parents[2]
    proc = _run_validator(repo, "9.9")
    assert proc.returncode == 1, (
        f"verdict gaps must trigger BLOCK; got rc={proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )


# ---------------------------------------------------------------------------
# Mirror parity
# ---------------------------------------------------------------------------

def test_b87_template_mirror_byte_identical() -> None:
    canonical = REPO_ROOT / "commands" / "vg" / "_shared" / "templates" / "IMPLEMENTATION-NOTES-template.html"
    mirror = REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "templates" / "IMPLEMENTATION-NOTES-template.html"
    assert canonical.read_bytes() == mirror.read_bytes(), (
        "IMPLEMENTATION-NOTES-template.html mirror drift"
    )


def test_b87_validator_mirror_byte_identical() -> None:
    canonical = REPO_ROOT / "scripts" / "validators" / "verify-implementation-notes.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "validators" / "verify-implementation-notes.py"
    assert canonical.read_bytes() == mirror.read_bytes(), (
        "verify-implementation-notes.py mirror drift"
    )
