"""v2.65.0 A5 — parallel_workers config field."""
import re
from pathlib import Path


def test_parallel_workers_in_template():
    body = Path("vg.config.template.md").read_text(encoding="utf-8")
    assert "parallel_workers:" in body, "template must declare parallel_workers field"
    m = re.search(r"^parallel_workers:\s*(\d+)", body, re.MULTILINE)
    assert m, "parallel_workers value must be a non-negative int"
    assert int(m.group(1)) >= 1, "default must be >= 1"


def test_parallel_workers_default_5():
    body = Path("vg.config.template.md").read_text(encoding="utf-8")
    m = re.search(r"^parallel_workers:\s*(\d+)", body, re.MULTILINE)
    assert m and int(m.group(1)) == 5, f"v2.65.0 default = 5 (found {m.group(1) if m else 'MISSING'})"


def test_parallel_workers_documented():
    """Field must have a comment explaining what it controls."""
    body = Path("vg.config.template.md").read_text(encoding="utf-8")
    # Look for doc lines preceding parallel_workers (within 6 lines before)
    m = re.search(
        r"((?:^[^\n]*\n){1,6})^parallel_workers:",
        body, re.MULTILINE
    )
    assert m, "parallel_workers should have preceding doc/comment block"
    preceding = m.group(1)
    assert "#" in preceding or "<!--" in preceding, \
        "parallel_workers must have explanatory comment (lines starting with # or <!--)"


def test_mirror_parallel_workers_block_identical():
    """v2.65.0 A5 — parallel_workers block must be identical across both
    template locations (root canonical + .claude/templates mirror).

    NOTE: full-file byte-identity is not enforced — the two files have
    pre-existing header divergence (instance config vs template generator).
    Only the A5 block itself must stay in sync.
    """
    canonical = Path("vg.config.template.md").read_text(encoding="utf-8")
    mirror = Path(".claude/templates/vg/vg.config.template.md").read_text(encoding="utf-8")
    pat = re.compile(
        r"(^# v2\.65\.0 A5[^\n]*\n(?:^# [^\n]*\n)*)^parallel_workers:\s*(\d+)\s*$",
        re.MULTILINE,
    )
    m_can = pat.search(canonical)
    m_mir = pat.search(mirror)
    assert m_can, "canonical: parallel_workers block missing"
    assert m_mir, "mirror: parallel_workers block missing"
    assert m_can.group(0) == m_mir.group(0), \
        "parallel_workers block must be byte-identical across both template files"
