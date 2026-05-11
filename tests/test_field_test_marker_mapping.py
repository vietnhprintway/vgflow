"""tests/test_field_test_marker_mapping.py — MARKER_TO_AUTO_EVENT field-test entry."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCH_MAIN = REPO_ROOT / "scripts" / "vg-orchestrator" / "__main__.py"
ORCH_MIRROR = REPO_ROOT / ".claude" / "scripts" / "vg-orchestrator" / "__main__.py"


def _read_marker_dict_block(path: Path) -> str:
    """Extract the MARKER_TO_AUTO_EVENT dict block from __main__.py."""
    body = path.read_text(encoding="utf-8")
    m = re.search(
        r"MARKER_TO_AUTO_EVENT.*?^\}",
        body, re.DOTALL | re.MULTILINE,
    )
    assert m, "MARKER_TO_AUTO_EVENT dict not found"
    return m.group(0)


def test_field_test_complete_marker_mapping_exists():
    """v2.1 Task 7d: orchestrator must auto-emit field_test.session_completed
    when the field-test skill writes the 'complete' marker."""
    block = _read_marker_dict_block(ORCH_MAIN)
    assert '("field-test", "complete")' in block, (
        "MARKER_TO_AUTO_EVENT must include ('field-test', 'complete') tuple key"
    )
    assert "field_test.session_completed" in block, (
        "Mapping value must be 'field_test.session_completed'"
    )


def test_field_test_marker_severity_is_info():
    """Same severity convention as other lifecycle complete markers."""
    block = _read_marker_dict_block(ORCH_MAIN)
    # The block has tuple key followed by tuple value — look for the specific line
    # ("field-test", "complete"): ("field_test.session_completed", "INFO")
    pattern = re.compile(
        r'\("field-test",\s*"complete"\)\s*:\s*\(\s*"field_test\.session_completed"\s*,\s*"INFO"\s*\)'
    )
    assert pattern.search(block), (
        f"field-test mapping must use severity 'INFO' to match build/review/test convention"
    )


def test_mirror_has_same_mapping():
    """Canonical and .claude/ mirror must both carry the new mapping."""
    canon_block = _read_marker_dict_block(ORCH_MAIN)
    mirror_block = _read_marker_dict_block(ORCH_MIRROR)
    assert '("field-test", "complete")' in canon_block
    assert '("field-test", "complete")' in mirror_block
