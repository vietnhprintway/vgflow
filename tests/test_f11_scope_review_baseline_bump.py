"""tests/test_f11_scope_review_baseline_bump.py — F11 baseline ts bump."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO / "commands" / "vg" / "_shared" / "scope-review" / "preflight.md"


def test_early_exit_bumps_baseline_ts():
    body = PREFLIGHT.read_text(encoding="utf-8")
    # Find the early-exit block
    early_idx = body.find('CHANGED_COUNT" = "0"')
    if early_idx < 0:
        early_idx = body.find("No phases changed since")
    assert early_idx > 0
    block = body[early_idx:early_idx + 1500]
    # Find the exit 0 position within the block
    exit_idx = block.find("exit 0")
    assert exit_idx > 0, "early-exit block must contain exit 0"
    # Must have actual baseline write code BEFORE exit 0
    pre_exit = block[:exit_idx]
    has_write = ("json.dump" in pre_exit or
                 "p.write_text" in pre_exit or
                 ".write_text(" in pre_exit or
                 "baseline_path.write" in pre_exit or
                 "write_baseline" in pre_exit)
    assert has_write, (
        "F11: scope-review early-exit must write updated baseline timestamp "
        "before exit 0 (json.dump / p.write_text / baseline_path.write). "
        "Currently exits without bump → stale 'last checked' on subsequent runs."
    )
