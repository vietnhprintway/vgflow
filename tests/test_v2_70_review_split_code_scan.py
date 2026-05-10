"""v2.70.0 T3 — review.md code-scan section split."""
from pathlib import Path


def test_code_scan_subfile_exists():
    p = Path("commands/vg/_shared/review/code-scan.md")
    assert p.exists(), "v2.70.0 T3 must create _shared/review/code-scan.md"


def test_code_scan_subfile_contains_extracted_steps():
    body = Path("commands/vg/_shared/review/code-scan.md").read_text(encoding="utf-8")
    expected_steps = [
        "phase1_code_scan",
        "phase1_5_ripple_and_god_node",
    ]
    for s in expected_steps:
        assert s in body, f"code-scan.md missing step: {s}"


def test_review_md_routes_to_code_scan_subfile():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    assert "_shared/review/code-scan.md" in body, \
        "review.md must reference _shared/review/code-scan.md after T3 split"


def test_review_md_no_longer_contains_extracted_step_bodies():
    """Verify extracted code-scan step <step name=...> tags are gone from review.md."""
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    extracted_step_tags = [
        '<step name="phase1_code_scan"',
        '<step name="phase1_5_ripple_and_god_node"',
    ]
    for tag in extracted_step_tags:
        assert tag not in body, \
            f"review.md still contains extracted step tag {tag} (should live in _shared/review/code-scan.md)"


def test_code_scan_subfile_mirror_byte_identity():
    canonical = Path("commands/vg/_shared/review/code-scan.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/review/code-scan.md").read_bytes()
    assert canonical == mirror, "_shared/review/code-scan.md mirrors must be byte-identical"


def test_review_md_mirror_byte_identity():
    canonical = Path("commands/vg/review.md").read_bytes()
    mirror = Path(".claude/commands/vg/review.md").read_bytes()
    assert canonical == mirror, "commands/vg/review.md mirrors must be byte-identical"
