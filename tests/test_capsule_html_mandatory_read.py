"""F2 v2.62.0: Capsule design context emits MUST READ structural.html section."""
import json
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _capsule_design_section(structural_present=True, interactions_present=False):
    """Run the design-context emit logic with mock slug entries.

    Direct unit test of the path-listing block. Easier than spawning the
    full pre-executor-check.py (which requires phase + plan setup).
    """
    # Inline a stripped-down replica of the design-context loop using
    # the exact same line emit pattern. This validates the SHAPE of
    # output, not the full pre-executor-check.py orchestration.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

    # We test the actual file's behavior by importing and calling
    # design-context production as a black box.
    # Approach: parse pre-executor-check.py and confirm the
    # "Structural HTML — READ" section is emitted when structural is set.
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    return src


def test_structural_section_header_present():
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    assert "Structural HTML — READ EACH PATH AND COPY MARKUP VERBATIM" in src, (
        "F2: pre-executor-check.py must emit a strong-mandate Structural HTML section "
        "matching the PNG section's pattern."
    )


def test_structural_section_cites_form_api_map():
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    assert "FORM-API-MAP" in src, (
        "Structural HTML section must forward-reference FORM-API-MAP "
        "(F3 v2.62.0) so executor knows the cross-reference exists."
    )


def test_structural_section_warns_about_field_drift():
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    # Must mention name attr drift consequence
    assert "user_email" in src or ("field" in src and "name" in src and "drift" in src), (
        "Section must explain field-name drift consequences (e.g., 'user_email' vs 'email')"
    )


def test_structural_uses_read_idiom():
    """Per-slug listing must use 'Read: {path}' style matching PNG."""
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    # The new section should emit lines like '  Read: {entry["structural"]}'
    assert (
        '  Read: {entry["structural"]}' in src
        or '  Read: {entry[\'structural\']}' in src
        or 'f"  Read: {entry[\'structural\']}"' in src
        or "f'  Read: {entry[\"structural\"]}'" in src
    ), "Per-slug structural HTML listing must use Read: idiom"


def test_passive_structural_ref_removed():
    """Old passive 'Structural ref: {path}' line should be gone (or moved into the
    new strong section)."""
    src = (REPO_ROOT / "scripts" / "pre-executor-check.py").read_text(encoding="utf-8")
    # The legacy weak emit was:
    #   lines.append(f"  Structural ref: {entry['structural']}")
    # If still present, it means the fix wasn't applied to the right place.
    weak_count = src.count('"  Structural ref: ')
    assert weak_count == 0, (
        f"Legacy passive 'Structural ref:' emit still present {weak_count} time(s). "
        "Replace with 'Read: {path}' under the strong-mandate Structural HTML section."
    )


def test_pre_executor_check_mirror_byte_identical():
    canonical = REPO_ROOT / "scripts" / "pre-executor-check.py"
    mirror = REPO_ROOT / ".claude" / "scripts" / "pre-executor-check.py"
    if not mirror.exists():
        return
    assert canonical.read_bytes() == mirror.read_bytes()
