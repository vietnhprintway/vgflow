from pathlib import Path

def test_amend_md_spawns_reflector_after_completion():
    """amend.md must spawn vg-reflector after phase.amend_committed event,
    gated by meta_memory_mode flag."""
    f = Path("commands/vg/amend.md").read_text(encoding="utf-8")
    assert "vg-reflector" in f, "amend.md must reference vg-reflector spawn"
    assert "phase.amend_committed" in f, "amend.md must reference phase.amend_committed event"
    assert "meta_memory_mode" in f, "amend.md spawn must be gated by meta_memory_mode flag"

def test_reflection_trigger_doc_lists_amend():
    doc = Path("commands/vg/_shared/reflection-trigger.md").read_text(encoding="utf-8")
    assert ("post-amend" in doc.lower()) or ("phase.amend_committed" in doc), \
        "reflection-trigger.md must document post-amend hook"
    assert ("type=retract" in doc) or ("type: retract" in doc), \
        "reflection-trigger.md must say type=retract for amend"

def test_mirror_byte_identical_amend():
    canonical = Path("commands/vg/amend.md").read_bytes()
    mirror = Path(".claude/commands/vg/amend.md").read_bytes()
    assert canonical == mirror, "amend.md mirror diverged from canonical"

def test_mirror_byte_identical_reflection_trigger_after_25():
    canonical = Path("commands/vg/_shared/reflection-trigger.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/reflection-trigger.md").read_bytes()
    assert canonical == mirror, "reflection-trigger.md mirror diverged from canonical"
