from pathlib import Path


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "VERSION").exists() and (parent / ".git").exists():
            return parent
    return here.parents[2]


REPO = _find_repo_root()


def test_blueprint_close_updates_state_before_marker_write() -> None:
    text = (REPO / "commands" / "vg" / "_shared" / "blueprint" / "close.md").read_text(
        encoding="utf-8"
    )
    assert '.steps_status["3_complete"] = "completed"' in text
    assert '.current_step = "complete"' in text
    assert 'mark_step "${PHASE_NUMBER:-unknown}" "3_complete"' in text

    update_idx = text.index('.steps_status["3_complete"] = "completed"')
    marker_idx = text.index('mark_step "${PHASE_NUMBER:-unknown}" "3_complete"')
    assert update_idx < marker_idx, (
        "blueprint close must sync blueprint-state.json before writing the 3_complete marker"
    )


def test_blueprint_close_mirror_stays_in_sync() -> None:
    src = REPO / "commands" / "vg" / "_shared" / "blueprint" / "close.md"
    mirror = REPO / ".claude" / "commands" / "vg" / "_shared" / "blueprint" / "close.md"
    assert src.read_bytes() == mirror.read_bytes()
