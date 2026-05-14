"""tests/test_batch25_review_gate_inverted.py — Batch 25 review gate semantics."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
REVIEW = REPO / "commands" / "vg" / "review.md"


def test_no_backwards_gate_text():
    body = REVIEW.read_text(encoding="utf-8")
    # Old wording (backwards in v4.0): "first full review requires /vg:test-spec"
    assert "first full review requires `/vg:test-spec`" not in body, (
        "Batch 25: remove 'review requires test-spec first' — v4.0 order is "
        "review WRITES RUNTIME-MAP, test-spec consumes it. Reversed dependency."
    )


def test_pipeline_arrow_correct():
    import re
    body = REVIEW.read_text(encoding="utf-8")
    # Pipeline arrow must be review → test-spec → test (v4.0)
    # review may be bolded as **review** so use regex
    assert re.search(r"\*?\*?review\*?\*?\s*→\s*test-spec", body), (
        "Batch 25: review.md pipeline arrow must show review → test-spec → test"
    )
    # Old wrong order must be gone
    assert not re.search(r"test-spec\s*→\s*\*?\*?review", body), (
        "Batch 25: old wrong arrow 'test-spec → review' must be removed"
    )
