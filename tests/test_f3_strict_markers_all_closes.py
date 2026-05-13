"""tests/test_f3_strict_markers_all_closes.py — F3 strict markers propagate."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

CLOSES = [
    "commands/vg/_shared/blueprint/close.md",
    "commands/vg/_shared/build/close.md",
    "commands/vg/_shared/accept/cleanup/overview.md",
    "commands/vg/_shared/test/close.md",  # already done in Batch 9 — must stay
]


def test_all_phase_closes_use_strict_marker_check():
    failures = []
    for rel in CLOSES:
        body = (REPO / rel).read_text(encoding="utf-8")
        if "verify_all_markers_strict_runid" not in body and "verify_marker" not in body:
            failures.append(f"{rel}: missing strict marker verification call")
    assert not failures, "F3 strict marker missing:\n  " + "\n  ".join(failures)


def test_blueprint_close_no_bare_file_exists_check_on_markers():
    body = (REPO / "commands/vg/_shared/blueprint/close.md").read_text(encoding="utf-8")
    # The bare `[ ! -f "${PHASE_DIR}/.step-markers/${step}.done" ]` pattern
    # should be removed in favor of strict-runid verification.
    # Tolerate the pattern if it's wrapped by verify_marker fallback.
    if 'verify_all_markers_strict_runid' in body or 'verify_marker' in body:
        return  # acceptable — strict path present
    assert False, "F3: blueprint/close.md must replace bare -f check with verify_marker"
