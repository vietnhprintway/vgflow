from pathlib import Path


SHARED_DEPLOY_DIR = Path("commands/vg/_shared/deploy")


def _deploy_text_full() -> str:
    """v2.73.0 — deploy logic split across deploy.md + _shared/deploy/*.md."""
    parts = [Path("commands/vg/deploy.md").read_text(encoding="utf-8")]
    if SHARED_DEPLOY_DIR.is_dir():
        for p in sorted(SHARED_DEPLOY_DIR.glob("*.md")):
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_deploy_md_spawns_reflector_after_completion():
    """deploy.md must spawn vg-reflector after phase.deploy_completed event,
    gated by meta_memory_mode flag."""
    deploy = _deploy_text_full()
    assert "vg-reflector" in deploy, "deploy.md must reference vg-reflector spawn"
    assert "phase.deploy_completed" in deploy, "deploy.md must reference phase.deploy_completed event"
    assert "meta_memory_mode" in deploy, "deploy.md spawn must be gated by meta_memory_mode flag"


def test_reflection_trigger_doc_lists_deploy():
    doc = Path("commands/vg/_shared/reflection-trigger.md").read_text(encoding="utf-8")
    assert ("post-deploy" in doc.lower()) or ("phase.deploy_completed" in doc), \
        "reflection-trigger.md must document post-deploy hook"
    assert ("vg-reflector" in doc) and ("target_step=deploy" in doc or "target_step: deploy" in doc), \
        "reflection-trigger.md must say vg-reflector spawned with target_step=deploy"


def test_mirror_byte_identical_deploy():
    canonical = Path("commands/vg/deploy.md").read_bytes()
    mirror = Path(".claude/commands/vg/deploy.md").read_bytes()
    assert canonical == mirror, "deploy.md mirror diverged from canonical"


def test_mirror_byte_identical_reflection_trigger():
    canonical = Path("commands/vg/_shared/reflection-trigger.md").read_bytes()
    mirror = Path(".claude/commands/vg/_shared/reflection-trigger.md").read_bytes()
    assert canonical == mirror, "reflection-trigger.md mirror diverged from canonical"
