#!/usr/bin/env python3
"""
vg-tasklist-snapshot.py — Capture latest TodoWrite state per active VG run.

Schema v2 (B71a, v4.63.0): accepts payload with `content` field and optional
`match_class` so emit-tasklist.py:_restore_mode can re-overlay statuses on
contract step_ids even when the AI emits free-form display labels (e.g.
"↳ 0 Parse And Validate" instead of "0_parse_and_validate").

Resolution from display label → contract step_id is performed by the CALLER
(scripts/hooks/vg-post-tool-use-todowrite.sh via scripts/tasklist_id_resolver.py)
BEFORE piping to this writer. This file remains a thin persister.

Schema v1 backward-compat: legacy callers pipe {"items":[{"id":..., "status":...}]}
without content. This is accepted; restore-mode handles legacy fallback.

Usage:
  echo '{"schema_version": 2, "items":[
    {"id":"0_parse_and_validate", "content":"↳ 0 Parse And Validate",
     "status":"completed", "match_class":"normalized"}]}' \\
    | python vg-tasklist-snapshot.py --write --run-id RID

Exit codes:
  0 — snapshot written (or input was empty/no-op)
  1 — invalid args
  2 — input JSON malformed
  3 — write failed (filesystem error)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()

SCHEMA_VERSION = 2

_VALID_MATCH_CLASSES = frozenset({
    "exact", "normalized", "strip-cmd", "strip-decimal",
    "substring", "slug", "unresolved",
})


def _snapshot_path(run_id: str) -> Path:
    return REPO_ROOT / ".vg" / "runs" / run_id / ".todowrite-snapshot.json"


def _validate_payload(data: object) -> dict | None:
    """Accept v2 payload {"schema_version":2, "items":[{id, content, status, match_class}]}
    OR v1 legacy {"items":[{id, status}]} OR raw list (v1 list form).

    Returns normalized v2 dict, or None if invalid.

    v1 inputs are auto-upgraded: schema_version added, content defaults to id,
    match_class defaults to "exact" (caller asserted id is already a step_id).
    """
    if isinstance(data, list):
        items = data
        provenance = {}
    elif isinstance(data, dict):
        items = data.get("items")
        provenance = data.get("id_map_provenance") or {}
    else:
        return None
    if not isinstance(items, list):
        return None
    cleaned: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sid = str(it.get("id") or it.get("content") or "").strip()
        sstatus = str(it.get("status") or "").strip()
        if not (sid and sstatus):
            continue
        # B71a: preserve content (display label) so restore-mode can re-resolve
        # if legacy v1 snapshot reader needs to bridge to v2.
        content = it.get("content")
        if content is None:
            # v1 fallback: use id as content.
            content = sid
        match_class = it.get("match_class") or "exact"
        if match_class not in _VALID_MATCH_CLASSES:
            match_class = "unresolved"
        cleaned.append({
            "id": sid,
            "content": str(content),
            "status": sstatus,
            "match_class": match_class,
        })
    payload = {
        "schema_version": SCHEMA_VERSION,
        "items": cleaned,
    }
    if provenance and isinstance(provenance, dict):
        payload["id_map_provenance"] = provenance
    return payload


def _write_snapshot(run_id: str, raw_stdin: str) -> int:
    if not run_id:
        print("vg-tasklist-snapshot: --run-id required", file=sys.stderr)
        return 1
    if not raw_stdin.strip():
        print("vg-tasklist-snapshot: empty stdin — no-op (prior snapshot preserved)",
              file=sys.stderr)
        return 0
    try:
        data = json.loads(raw_stdin)
    except json.JSONDecodeError as exc:
        print(f"vg-tasklist-snapshot: malformed JSON ({exc})", file=sys.stderr)
        return 2
    payload = _validate_payload(data)
    if payload is None:
        print("vg-tasklist-snapshot: payload missing items[]", file=sys.stderr)
        return 2
    if not payload["items"]:
        print("vg-tasklist-snapshot: items[] empty — no-op (prior snapshot preserved)",
              file=sys.stderr)
        return 0
    # B71a: stamp resolved_at into provenance for audit trail.
    payload.setdefault("id_map_provenance", {})
    payload["id_map_provenance"].setdefault(
        "resolved_at", datetime.utcnow().isoformat() + "Z"
    )
    payload["id_map_provenance"]["snapshot_hash"] = (
        "sha256:" + hashlib.sha256(
            json.dumps(payload["items"], sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
    )
    out = _snapshot_path(run_id)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(out))
    except OSError as exc:
        print(f"vg-tasklist-snapshot: write failed ({exc})", file=sys.stderr)
        return 3
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="Write stdin JSON to .vg/runs/{run_id}/.todowrite-snapshot.json")
    ap.add_argument("--run-id", required=False, default="",
                    help="Active run ID")
    args = ap.parse_args()
    if not args.write:
        print("vg-tasklist-snapshot: pass --write (F1 v2.60.0 placeholder)",
              file=sys.stderr)
        return 1
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    return _write_snapshot(args.run_id.strip(), raw)


if __name__ == "__main__":
    sys.exit(main())
