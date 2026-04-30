"""Verify kit prompts only reference field names that build_worker_prompt provides."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KIT_FILE = (
    REPO_ROOT / "commands" / "vg" / "_shared" / "transition-kits" / "crud-roundtrip.md"
)

# Field paths that build_worker_prompt() actually puts in context_block
PROVIDED_FIELDS = {
    "platforms_web", "platforms_backend", "auth_token", "actor", "base_url",
    "expected_behavior", "forbidden_side_effects", "lifecycle_states",
    "object_level_auth", "delete_policy", "scope", "resource", "role",
    "run_id", "output_path",
}

# Old field names that should no longer appear as orphan refs
LEGACY_FIELDS = {
    "route_list", "route_create", "route_update", "route_delete", "route_detail",
}


def test_kit_no_legacy_field_refs():
    text = KIT_FILE.read_text(encoding="utf-8")
    for field in LEGACY_FIELDS:
        # Match `route_list` or ${route_list} or {route_list}
        pattern = rf"[\$\{{`]?\b{field}\b[`\}}]?"
        matches = re.findall(pattern, text)
        assert not matches, (
            f"Kit still references legacy field '{field}': {matches[:3]}"
        )


def test_kit_has_imperative_preamble():
    text = KIT_FILE.read_text(encoding="utf-8")
    assert "TOOL USAGE IS MANDATORY" in text or "MUST call" in text
    assert "Text-only responses" in text


def test_kit_handles_null_base_url():
    """Kit must instruct workers what to do if base_url is null/empty —
    write a blocked step rather than fabricate a URL like ``null/notes``."""
    text = KIT_FILE.read_text(encoding="utf-8")
    assert "missing_base_url" in text, (
        "Kit must declare the 'missing_base_url' blocked-step protocol so "
        "workers do not fabricate URLs when base_url is null."
    )
