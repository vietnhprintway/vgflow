"""Tests for H1 (cleanup order) + C10 (GAPS_FOUND keeps traces) fixes."""
from __future__ import annotations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOSE_MD = REPO_ROOT / "commands" / "vg" / "_shared" / "test" / "close.md"


def test_cleanup_order_preserves_traces_first():
    """H1: trace/video preservation step must appear BEFORE the rm -rf test-results/ deletion."""
    body = CLOSE_MD.read_text(encoding="utf-8")
    # The preservation block references keeping videos/traces
    preserve_pos = body.find("keeping videos/traces")
    if preserve_pos == -1:
        # Alternative: find the conditional that keeps traces
        preserve_pos = body.find("keeping videos")
    rm_pos = body.find('rm -rf {} + 2>/dev/null')
    # rm -rf block deletes test-results/ dirs — preservation logic must come first
    assert preserve_pos != -1, "H1: close.md must have a trace/video preservation decision block"
    assert rm_pos != -1, "H1: close.md must have rm -rf cleanup block"
    # The preservation check (echo/comment about keeping) must appear before
    # the unconditional find/rm that deletes test-results
    # We check by: the condition that decides to keep must precede the rm block
    keep_verdict_pos = body.find("Verdict = $VERDICT")
    assert keep_verdict_pos != -1, "H1: close.md must reference VERDICT before cleanup"
    # The verdict-based keep block must come before rm-rf test-results
    assert keep_verdict_pos < rm_pos, (
        f"H1: verdict check (pos {keep_verdict_pos}) must precede rm -rf (pos {rm_pos}) "
        "to preserve traces before wiping test-results/"
    )


def test_cleanup_keeps_artifacts_for_gaps_found():
    """C10: GAPS_FOUND verdict must keep traces (same as FAILED), not delete them."""
    body = CLOSE_MD.read_text(encoding="utf-8")
    # Find the conditional that decides to delete vs keep videos/traces
    # It should NOT include GAPS_FOUND in the delete condition
    # i.e., we should not see 'GAPS_FOUND' paired with deletion of traces
    # The correct pattern: only delete if VERDICT == PASSED
    # Check that the condition does NOT combine PASSED and GAPS_FOUND for deletion
    assert 'VERDICT" = "GAPS_FOUND"' not in body or (
        # If GAPS_FOUND is present, it must be in the "keep" branch, not "delete"
        'echo "Verdict = $VERDICT — keeping videos/traces' in body
    ), (
        "C10: GAPS_FOUND should NOT trigger trace deletion — traces must be kept for debug"
    )
    # More direct: the deletion condition must be PASSED-only
    # Look for the if-condition around the find ... delete block
    import re
    # Match: if [ "$VERDICT" = "PASSED" ] or if [ "$VERDICT" = "PASSED" ] || ...GAPS...
    delete_cond = re.search(
        r'if \[.*VERDICT.*PASSED.*\].*\|\|.*GAPS_FOUND|if \[.*VERDICT.*GAPS_FOUND.*\].*PASSED',
        body
    )
    assert delete_cond is None, (
        "C10: deletion condition must NOT include GAPS_FOUND — "
        "GAPS_FOUND needs traces for debug, same as FAILED"
    )


def test_trace_paths_emitted_to_sandbox_test_md():
    """Batch 5 + H1: trace.zip and video paths must be documented for SANDBOX-TEST.md."""
    canonical = REPO_ROOT / "commands" / "vg" / "_shared" / "test" / "regression-security.md"
    body = canonical.read_text(encoding="utf-8")
    assert "trace.zip" in body, "Batch 5: trace.zip path must appear in regression-security.md"
    assert "video.webm" in body or ("video" in body and "test-results" in body), (
        "Batch 5: video path must appear in regression-security.md"
    )
    assert "SANDBOX-TEST.md" in body, "Batch 5: SANDBOX-TEST.md must be mentioned in failure handler"
