"""tests/test_batch25_old_4step_upgraded.py — Batch 25 old 4-step references upgraded."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_no_old_4step_remaining():
    """No command file should reference the old 4-step pipeline without test-spec."""
    bad_pattern = re.compile(r"build\s*→\s*review\s*→\s*test\s*→\s*accept")
    misses = []
    for p in (REPO / "commands" / "vg").glob("*.md"):
        body = p.read_text(encoding="utf-8")
        if bad_pattern.search(body):
            misses.append(p.name)
    assert not misses, (
        f"Batch 25: old 4-step pipeline (no test-spec) found in: {misses}. "
        f"Must insert test-spec: 'build → review → test-spec → test → accept'"
    )
