#!/usr/bin/env python3
"""identify_interesting_clickables.py — classify scan-*.json elements (14 classes).

Reads scan-*.json output from the Haiku scanner and emits a deterministic
``recursive-classification.json`` with one entry per "interesting" clickable.

Pure Python, deterministic, no LLM cost.

Element classes (per design doc 2026-04-30-v2.40-recursive-lens-probe.md):

Tier 1 — fully implemented (direct map from scan-*.json fields):
  - mutation_button   results[].network[].method ∈ {POST,PUT,PATCH,DELETE}
  - form_trigger      forms[].submit_result.status exists (no file field)
  - file_upload       forms[].fields[].type == "file"
  - tab               tabs[]
  - row_action        tables[].row_actions[]
  - bulk_action       tables[].bulk_actions[]
  - sub_view_link     sub_views_discovered[]
  - modal_trigger     modal_triggers[]

Tier 2 — STUBBED (deferred to Task 18 — spawn-recursive-probe.py):
  - redirect_url_param, url_fetch_param, path_param
  - auth_endpoint, payment_or_workflow, error_response

Tier 2 detection requires:
  1. Haiku scanner output schema to be locked (Phase 1.D) — current scan-*.json
     shape (network[], headers, response_body) is provisional.
  2. CRUD-SURFACES.category field to be confirmed (open question #5 in design
     doc) — payment_or_workflow should key off `category`, not path regex.
  3. Per-detector fixtures + tests so the heuristics don't over-spawn lenses
     (e.g. naïve "Authorization header → auth_endpoint" flags every API call
     in a modern app and blows the worker cap).

Output schema:

    {
      "clickables": [
        {
          "view": "/admin/topup-requests",
          "element_class": "mutation_button",
          "selector": "button#delete-42",
          "selector_hash": "<sha256[:8]>",
          "resource": "topup_requests",
          "action_semantic": "delete",
          "metadata": {...}
        },
        ...
      ],
      "count": <int>
    }

The selector hash is sha256 truncated to 8 hex chars per the design doc — used
as a stable, short id for cross-run memoization (collision risk is acceptable
because hashes are scoped per view).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# --- Tier 1 ------------------------------------------------------------------
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Hash truncation length — design-doc spec; documented as a constant rather
# than a magic number sprinkled in code.
SELECTOR_HASH_LEN = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def selector_hash(s: str) -> str:
    """Return sha256(s)[:SELECTOR_HASH_LEN] — deterministic short id."""
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:SELECTOR_HASH_LEN]


def _action_from_method(method: str | None, path: str | None) -> str:
    m = (method or "").upper()
    if m == "DELETE":
        return "delete"
    if m == "POST":
        return "create"
    if m in ("PUT", "PATCH"):
        return "update"
    return "mutate"


def _resource_from_path(path: str | None) -> str:
    """Best-effort resource extraction from a URL path (e.g. /api/topup/42 -> topup)."""
    if not path:
        return ""
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    # Drop common /api prefix and trailing numeric ids.
    if parts and parts[0].lower() == "api":
        parts = parts[1:]
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return parts[-1] if parts else ""


def _emit(out: list[dict], view: str, element_class: str, selector: str,
          *, action_semantic: str, resource: str = "", metadata: dict | None = None) -> None:
    out.append({
        "view": view,
        "element_class": element_class,
        "selector": selector,
        "selector_hash": selector_hash(selector),
        "resource": resource,
        "action_semantic": action_semantic,
        "metadata": metadata or {},
    })


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
def classify_scan(scan: dict) -> list[dict]:
    """Single-pass classification of one scan-*.json into clickable rows."""
    out: list[dict] = []
    view = scan.get("view", "")

    # --- Tier 1 -------------------------------------------------------------
    # mutation_button: results carrying mutating network calls.
    for r in scan.get("results", []) or []:
        for n in r.get("network", []) or []:
            method = (n.get("method") or "").upper()
            if method in MUTATION_METHODS:
                sel = r.get("selector") or r.get("action") or ""
                _emit(out, view, "mutation_button", sel,
                      action_semantic=_action_from_method(method, n.get("path")),
                      resource=_resource_from_path(n.get("path")),
                      metadata={"method": method, "path": n.get("path")})

    # form_trigger / file_upload — submitted forms.
    for f in scan.get("forms", []) or []:
        if "submit_result" not in f:
            continue
        sel = f.get("selector", "")
        fields = f.get("fields", []) or []
        has_file = any((fld.get("type") == "file") for fld in fields)
        ec = "file_upload" if has_file else "form_trigger"
        _emit(out, view, ec, sel,
              action_semantic="upload" if has_file else "submit",
              metadata={"fields": fields, "submit_result": f.get("submit_result")})

    # tabs
    for t in scan.get("tabs", []) or []:
        sel = f"tab[{t}]"
        _emit(out, view, "tab", sel, action_semantic="switch",
              metadata={"label": t})

    # row_actions / bulk_actions
    for tbl in scan.get("tables", []) or []:
        for ra in tbl.get("row_actions", []) or []:
            _emit(out, view, "row_action", f"row_action[{ra}]",
                  action_semantic=ra, metadata={})
        for ba in tbl.get("bulk_actions", []) or []:
            _emit(out, view, "bulk_action", f"bulk[{ba}]",
                  action_semantic=ba, metadata={})

    # modal triggers
    for m in scan.get("modal_triggers", []) or []:
        _emit(out, view, "modal_trigger", m,
              action_semantic="open_modal", metadata={})

    # sub_view_link
    for sv in scan.get("sub_views_discovered", []) or []:
        _emit(out, view, "sub_view_link", f"link[{sv}]",
              action_semantic="navigate", metadata={"target": sv})

    # --- Tier 2 (stubbed; see module docstring) -----------------------------
    out.extend(_tier2_url_param_classes(scan, view))
    out.extend(_tier2_endpoint_classes(scan, view))
    out.extend(_tier2_workflow_classes(scan, view))
    out.extend(_tier2_error_responses(scan, view))

    return out


# ---------------------------------------------------------------------------
# Tier 2 — STUBS (implementation deferred to Task 18)
# ---------------------------------------------------------------------------
def _tier2_url_param_classes(scan: dict, view: str) -> list[dict]:
    """TODO(task-18): URL param-based classification (redirect_url_param, url_fetch_param, path_param).

    Defer until Haiku scanner output schema is locked (Phase 1.D)."""
    return []


def _tier2_endpoint_classes(scan: dict, view: str) -> list[dict]:
    """TODO(task-18): Auth endpoint detection. Path-only pattern (NOT Authorization header — too noisy).

    Defer until Haiku scanner output schema is locked (Phase 1.D)."""
    return []


def _tier2_workflow_classes(scan: dict, view: str) -> list[dict]:
    """TODO(task-18): payment_or_workflow detection via CRUD-SURFACES.category field.

    Defer until CRUD-SURFACES schema confirms category field exists (open question #5)."""
    return []


def _tier2_error_responses(scan: dict, view: str) -> list[dict]:
    """TODO(task-18): error_response detection (status>=500 + multi-language stack markers).

    Defer until Haiku scanner output schema confirms response_body field shape."""
    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan-files", nargs="+", required=True,
                    help="One or more scan-*.json files emitted by the Haiku scanner")
    ap.add_argument("--output", default=None,
                    help="Path to write recursive-classification.json (default: stdout only)")
    ap.add_argument("--json", action="store_true",
                    help="Print the JSON payload to stdout (default if --output is omitted)")
    args = ap.parse_args()

    all_clickables: list[dict[str, Any]] = []
    for sp in args.scan_files:
        p = Path(sp)
        if not p.is_file():
            print(f"scan file not found: {p}", file=sys.stderr)
            return 1
        try:
            scan = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"invalid JSON in {p}: {e}", file=sys.stderr)
            return 1
        all_clickables.extend(classify_scan(scan))

    payload = {"clickables": all_clickables, "count": len(all_clickables)}

    if args.json or args.output is None:
        print(json.dumps(payload, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
