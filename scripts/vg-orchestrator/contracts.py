"""
Parse runtime_contract block from skill-MD frontmatter.
Substitute ${PHASE_DIR} and ${PHASE_NUMBER} template variables.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands" / "vg"
PHASES_DIR = REPO_ROOT / ".vg" / "phases"


def parse(command: str) -> dict | None:
    """
    Read .claude/commands/vg/{cmd}.md, extract runtime_contract.
    Returns parsed dict or None if absent. Validates against JSON Schema
    when PyYAML + jsonschema available — typos caught at load-time, not
    runtime. Prints schema errors to stderr but returns parsed dict for
    best-effort operation (never hard-fail a misconfigured skill-MD).
    """
    cmd_name = command.replace("vg:", "").replace("/", "")
    cmd_file = COMMANDS_DIR / f"{cmd_name}.md"
    if not cmd_file.exists():
        return None

    text = cmd_file.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None

    end = re.search(r"\n---\s*\n", text[4:])
    if not end:
        return None
    fm_text = text[4:4 + end.start()]

    try:
        import yaml  # type: ignore
        fm = yaml.safe_load(fm_text) or {}
        contract = fm.get("runtime_contract")
    except ImportError:
        contract = _fallback_parse(fm_text)

    # Schema validation — best-effort. Prints warnings to stderr, doesn't
    # block parse (preserves current behavior where skills work even if
    # PyYAML/jsonschema missing in hook env).
    if contract:
        _validate_against_schema(contract, command)

    return contract


def _validate_against_schema(contract: dict, command: str) -> None:
    """Load .claude/schemas/runtime-contract.json, validate contract, warn on errors."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return  # jsonschema not installed — skip silently

    schema_path = (COMMANDS_DIR.parent.parent / "schemas" /
                   "runtime-contract.json")
    if not schema_path.exists():
        return

    try:
        import sys
        schema = __import__("json").loads(
            schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(contract))
        if errors:
            print(
                f"⚠ runtime_contract schema issues in {command}:",
                file=sys.stderr,
            )
            for err in errors[:5]:  # cap output
                path = ".".join(str(p) for p in err.absolute_path) or "<root>"
                print(f"  [{path}] {err.message}", file=sys.stderr)
    except Exception:
        # Never block on validation infrastructure failure
        pass


def _fallback_parse(fm_text: str) -> dict | None:
    """PyYAML-free parser — subset of runtime_contract shape.
    Used when PyYAML not installed in hook environment."""
    m = re.search(r"^runtime_contract:\s*\n((?:[ \t].*\n?)+)",
                  fm_text, re.MULTILINE)
    if not m:
        return None
    block = m.group(1)
    contract: dict = {}
    current_key: str | None = None
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Top-level list key
        key_m = re.match(r"^  ([a-z_]+):\s*$", line)
        if key_m:
            current_key = key_m.group(1)
            contract[current_key] = []
            continue
        # Simple list item (string)
        item_m = re.match(r"^    -\s+\"?([^\"#]+)\"?\s*$", line)
        if item_m and current_key:
            contract[current_key].append(item_m.group(1).strip())
            continue
        # List item with nested (e.g. event_type object)
        obj_start = re.match(r"^    -\s+event_type:\s*\"?([^\"#]+)\"?\s*$",
                             line)
        if obj_start and current_key:
            contract[current_key].append({"event_type": obj_start.group(1).strip()})
            continue
        # Nested field on last object item
        nested_m = re.match(r"^      ([a-z_]+):\s*\"?([^\"#]+)\"?\s*$", line)
        if nested_m and current_key and contract[current_key]:
            last = contract[current_key][-1]
            if isinstance(last, dict):
                last[nested_m.group(1)] = nested_m.group(2).strip()
    return contract


def resolve_phase_dir(phase: str) -> Path | None:
    """Find phase dir accepting zero-padded variants."""
    if not phase or not PHASES_DIR.exists():
        return None
    candidates = list(PHASES_DIR.glob(f"{phase}-*"))
    if not candidates:
        candidates = list(PHASES_DIR.glob(f"{phase.zfill(2)}-*"))
    return candidates[0] if candidates else None


def substitute(template: str, phase: str, phase_dir: Path | None) -> str:
    """Replace ${PHASE_DIR}, ${PHASE_NUMBER} in path templates.

    When phase_dir is None (phase not yet created on disk), substitute with
    a readable glob placeholder so violation messages point users at the
    right location instead of leaking the literal ${PHASE_DIR} token.
    """
    out = template.replace("${PHASE_NUMBER}", phase)
    if phase_dir is not None:
        out = out.replace("${PHASE_DIR}", str(phase_dir))
    else:
        out = out.replace("${PHASE_DIR}", f".vg/phases/{phase}-<missing>")
    return out


def normalize_must_write(items: list) -> list[dict]:
    """Normalize mixed string/dict items to unified dict shape."""
    result = []
    for item in items or []:
        if isinstance(item, str):
            result.append({"path": item, "content_min_bytes": 1,
                           "content_required_sections": []})
        elif isinstance(item, dict) and "path" in item:
            result.append({
                "path": item["path"],
                "content_min_bytes": int(item.get("content_min_bytes", 1)),
                "content_required_sections": item.get(
                    "content_required_sections", []
                ),
            })
    return result


def normalize_markers(items: list) -> list[dict]:
    """Normalize markers to {name, namespace} shape."""
    result = []
    for item in items or []:
        if isinstance(item, str):
            result.append({"name": item, "namespace": "shared"})
        elif isinstance(item, dict) and "name" in item:
            result.append({
                "name": item["name"],
                "namespace": item.get("namespace", "shared"),
            })
    return result


def normalize_telemetry(items: list) -> list[dict]:
    """Normalize telemetry requirements to unified dict shape."""
    result = []
    for item in items or []:
        if isinstance(item, str):
            result.append({"event_type": item, "min_count": 1})
        elif isinstance(item, dict) and "event_type" in item:
            result.append({
                "event_type": item["event_type"],
                "phase": item.get("phase"),
                "min_count": int(item.get("min_count", 1)),
                "must_pair_with": item.get("must_pair_with"),
            })
    return result
