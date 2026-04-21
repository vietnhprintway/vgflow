"""
Content-aware evidence checks. Beats the "echo TODO > PLAN.md" bypass
where an empty file passes basic file-exists gate.
"""
from __future__ import annotations

from pathlib import Path


def check_artifact(path: Path, min_bytes: int = 1,
                   required_sections: list[str] | None = None) -> dict:
    """
    Returns {"ok": bool, "reason": str|None}.
    Checks:
    - file exists
    - size >= min_bytes
    - contains every string in required_sections (substring match)
    """
    if not path.exists():
        return {"ok": False, "reason": "missing"}
    size = path.stat().st_size
    if size < min_bytes:
        return {"ok": False, "reason": f"too-small ({size} < {min_bytes})"}

    if required_sections:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"ok": False, "reason": f"unreadable: {e}"}
        missing = [s for s in required_sections if s not in text]
        if missing:
            return {"ok": False, "reason": f"missing-sections: {missing}"}

    return {"ok": True, "reason": None}


def check_telemetry(expected: list[dict], events: list[dict]) -> list[str]:
    """
    Returns list of missing telemetry event types (strings for error messages).
    Supports must_pair_with: event X requires matching event Y.
    """
    # Index events by type for fast lookup
    type_counts = {}
    for evt in events:
        et = evt.get("event_type")
        if et:
            type_counts[et] = type_counts.get(et, 0) + 1

    missing = []
    for spec in expected:
        event_type = spec["event_type"]
        min_count = int(spec.get("min_count", 1))
        actual_count = type_counts.get(event_type, 0)
        if actual_count < min_count:
            missing.append(
                f"{event_type} (expected ≥{min_count}, got {actual_count})"
            )
            continue

        pair = spec.get("must_pair_with")
        if pair:
            pair_count = type_counts.get(pair, 0)
            if pair_count < actual_count:
                missing.append(
                    f"{event_type} unpaired — {actual_count} without matching {pair}"
                )

    return missing
