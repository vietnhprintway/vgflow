"""v2.66.1 #154 — crossai_review.done marker verdict-gated."""
import re
from pathlib import Path


def _review_md_full_text() -> str:
    """Concatenate review.md + all _shared/review/*.md sub-files.

    v2.70.0 T9 split moved crossai_review step body into _shared/review/close.md.
    These tests check semantic content (verdict-gating language) that lives in
    the close section, so the source-of-truth is the concatenation, not the
    routing shell.
    """
    parts = [Path("commands/vg/review.md").read_text(encoding="utf-8")]
    shared_review = Path("commands/vg/_shared/review")
    if shared_review.is_dir():
        for p in sorted(shared_review.glob("*.md")):
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_review_md_documents_verdict_gating():
    body = _review_md_full_text()
    # Must mention verdict-gating logic for crossai_review marker
    assert re.search(
        r"crossai_review.*(?:verdict|ok_count).*(?:gat|condition|check)",
        body, re.IGNORECASE | re.DOTALL
    ), "review.md must document verdict-gated crossai_review marker"


def test_inconclusive_marker_alternative_documented():
    body = _review_md_full_text()
    # When verdict=inconclusive, write crossai_review.inconclusive (different name) instead
    assert "crossai_review.inconclusive" in body, \
        "review.md must document fallback marker name for inconclusive"


def test_aggregator_logic_branches_on_verdict():
    """aggregator script must branch marker write on verdict + ok_count."""
    # Find script that writes the marker
    candidates = [
        "scripts/crossai-aggregate-results.py",
        "scripts/crossai-normalize-results.py",
        "scripts/crossai-runner.py",
        "scripts/crossai-marker-write.py",
    ]
    found = False
    for c in candidates:
        p = Path(c)
        if p.exists():
            body = p.read_text(encoding="utf-8")
            if "crossai_review.done" in body or "crossai_review.inconclusive" in body:
                found = True
                # Logic must reference verdict variable
                assert re.search(
                    r"verdict.*['\"](?:ok|pass|partial|flag|inconclusive|fail)['\"]",
                    body, re.IGNORECASE
                ), f"{c}: verdict-branching logic missing"
                break

    if not found:
        # If marker write is in review.md bash directly, that's also acceptable
        body = Path("commands/vg/review.md").read_text(encoding="utf-8")
        assert re.search(
            r"crossai_review\.done.*verdict|verdict.*crossai_review\.done",
            body, re.IGNORECASE | re.DOTALL
        ), "marker write logic must reference verdict either in script or review.md"
