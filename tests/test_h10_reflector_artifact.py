"""tests/test_h10_reflector_artifact.py — H10 reflector output preserved."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
CLOSE = REPO / "commands" / "vg" / "_shared" / "test" / "close.md"


def test_reflector_output_persists_to_artifact():
    body = CLOSE.read_text(encoding="utf-8")
    # Reflector spawn must write output to REFLECTION.md
    assert "REFLECTION.md" in body, (
        "H10: vg-reflector subagent output must persist to "
        "${PHASE_DIR}/REFLECTION.md as artifact"
    )


def test_reflector_skip_flag_documented():
    body = CLOSE.read_text(encoding="utf-8")
    # --skip-reflection flag documented
    assert "--skip-reflection" in body, (
        "H10: --skip-reflection flag must be documented to allow opting out"
    )
