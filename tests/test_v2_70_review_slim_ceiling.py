"""v2.70.0 T10 — review.md slim ceiling."""
from pathlib import Path


def test_review_md_under_slim_ceiling():
    """After full split, review.md should be slim routing + frontmatter only."""
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    line_count = len(body.splitlines())
    # Original 8159 lines → split target ≤ 1500 (60% reduction minimum)
    assert line_count <= 1500, \
        f"v2.70.0 split target: review.md ≤ 1500 lines (got {line_count})"


def test_shared_review_dir_has_9_files():
    review_dir = Path("commands/vg/_shared/review")
    md_files = sorted(review_dir.glob("*.md"))
    assert len(md_files) >= 9, \
        f"v2.70.0 split target: ≥9 sub-files in _shared/review/ (got {len(md_files)})"


def test_review_md_routes_to_each_subfile():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    expected_subfiles = [
        "preflight.md", "phase-p-variants.md", "code-scan.md", "api-and-discovery.md",
        "lens-and-findings.md", "limits-and-mobile.md", "url-and-error.md",
        "fix-loop-and-goals.md", "close.md",
    ]
    missing = [s for s in expected_subfiles if f"_shared/review/{s}" not in body]
    assert not missing, f"review.md missing routes: {missing}"
