#!/usr/bin/env python3
"""F3 v2.62.0 — verify-form-api-field-match.py.

Run during /vg:build post-execution gate. Reads FORM-API-MAP.md (emitted
by blueprint-form-api-map.py) + scans FE codegen output (.tsx/.jsx/.vue/
.html). Compares actual FE input name attrs vs FORM-API-MAP expected.
Emits BuildWarningEvidence (severity=warn by default) if drift detected.

Usage:
    verify-form-api-field-match.py --phase {N} --fe-root {dir}
                                   [--phase-dir {path}]
                                   [--strict] [--evidence-out {path}]

Exit codes:
  0 = no drift detected, or drift but --strict not passed (WARN evidence)
  1 = drift detected with --strict (BLOCK)
  2 = invocation error / missing inputs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

INPUT_NAME_RE = re.compile(
    r"<\s*(?:input|select|textarea)\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
FORM_TAG_RE = re.compile(r"<\s*form\b", re.IGNORECASE)
ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*[^|]+\|\s*[^|]+\|\s*[^|]+\|\s*([^|]+?)\s*\|\s*[^|]+\|\s*([^|]+?)\s*\|"
)
H2_RE = re.compile(r"^##\s+(.+?)\s*$")


def parse_form_api_map(map_text: str) -> dict[str, list[dict]]:
    """Parse FORM-API-MAP.md into {form_id: [{html_name, api_field, match_marker}]}."""
    forms: dict[str, list[dict]] = {}
    current_form: str | None = None
    in_table = False
    for raw_line in map_text.splitlines():
        line = raw_line.rstrip()
        h2 = H2_RE.match(line)
        if h2:
            # form_id is the first whitespace-delimited token of heading
            heading = h2.group(1)
            # heading like "login-form (from login)" — take up to first " (" or whole
            current_form = heading.split(" (")[0].strip()
            forms.setdefault(current_form, [])
            in_table = False
            continue
        if line.startswith("|---"):
            in_table = True
            continue
        if not in_table or current_form is None:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        html_name = m.group(1).strip()
        api_field = m.group(2).strip()
        marker = m.group(3).strip()
        # Skip the header row (already handled by --- but be defensive)
        if html_name.lower() == "html name attr":
            continue
        forms[current_form].append({
            "html_name": html_name,
            "api_field": api_field,
            "marker": marker,
        })
    return forms


def scan_fe_for_inputs(fe_root: Path) -> list[dict]:
    """Return list of {file, line, name} for every input/select/textarea name attr."""
    findings: list[dict] = []
    exts = (".tsx", ".jsx", ".vue", ".html", ".htm")
    for path in fe_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for m in INPUT_NAME_RE.finditer(line):
                findings.append({
                    "file": str(path),
                    "line": i,
                    "name": m.group(1),
                })
    return findings


def main() -> int:
    p = argparse.ArgumentParser(description="Verify FE form fields match FORM-API-MAP.md")
    p.add_argument("--phase", required=True)
    p.add_argument("--phase-dir", help="Explicit phase directory")
    p.add_argument("--fe-root", required=True, help="Frontend codegen root to scan")
    p.add_argument("--strict", action="store_true",
                   help="Block (rc=1) on any drift instead of WARN")
    p.add_argument("--evidence-out", help="Write evidence JSON here")
    args = p.parse_args()

    if args.phase_dir:
        phase_dir = Path(args.phase_dir)
    else:
        phase_dir = REPO_ROOT / ".vg" / "phases" / args.phase

    map_path = phase_dir / "FORM-API-MAP.md"
    if not map_path.exists():
        print(f"ERROR: FORM-API-MAP.md not found at {map_path}", file=sys.stderr)
        return 2

    fe_root = Path(args.fe_root)
    if not fe_root.is_dir():
        print(f"ERROR: --fe-root not a directory: {fe_root}", file=sys.stderr)
        return 2

    map_text = map_path.read_text(encoding="utf-8")
    expected = parse_form_api_map(map_text)

    # Build set of expected html_name values (across all forms in the map).
    expected_names: set[str] = set()
    expected_api_fields: set[str] = set()
    for form_id, fields in expected.items():
        for f in fields:
            if f["html_name"]:
                expected_names.add(f["html_name"])
            if f["api_field"] and f["api_field"] not in ("—", "(no match)"):
                expected_api_fields.add(f["api_field"])

    fe_inputs = scan_fe_for_inputs(fe_root)

    mismatches: list[dict] = []
    for inp in fe_inputs:
        nm = inp["name"]
        if nm in expected_names:
            continue
        # If FE name is in expected_api_fields directly, it's a tolerated alias
        if nm in expected_api_fields and nm not in expected_names:
            mismatches.append({
                "file": inp["file"],
                "line": inp["line"],
                "actual_name": nm,
                "expected_html_names": sorted(expected_names),
                "note": "FE used api_field name directly (drift from FORM-API-MAP html_name)",
            })
            continue
        mismatches.append({
            "file": inp["file"],
            "line": inp["line"],
            "actual_name": nm,
            "expected_html_names": sorted(expected_names),
            "note": "FE input name not present in FORM-API-MAP",
        })

    if not mismatches:
        print(f"OK: {len(fe_inputs)} FE input(s) all match FORM-API-MAP expectations")
        return 0

    severity = "BLOCK" if args.strict else "warn"
    summary_lines = [
        f"{m['file']}:{m['line']} actual='{m['actual_name']}' "
        f"expected_one_of={m['expected_html_names'][:3]}{'…' if len(m['expected_html_names'])>3 else ''}"
        for m in mismatches
    ]
    summary = (
        f"{len(mismatches)} FE input(s) drift from FORM-API-MAP:\n  "
        + "\n  ".join(summary_lines)
    )

    evidence = {
        "warning_id": f"form-api-field-drift-{args.phase}-{len(mismatches)}",
        "severity": severity,
        "category": "form_api_field_match",
        "phase": args.phase,
        "evidence_refs": [
            {
                "file": m["file"],
                "line": m["line"],
                "actual_name": m["actual_name"],
                "expected_html_names": m["expected_html_names"],
                "note": m["note"],
            }
            for m in mismatches
        ],
        "summary": summary,
        "detected_by": "verify-form-api-field-match.py",
        "detected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owning_artifact": "FORM-API-MAP.md",
        "recommended_action": (
            "FE: rename input name attrs to match FORM-API-MAP html_name column; "
            "OR re-run /vg:blueprint to regenerate FORM-API-MAP.md from latest "
            "structural.html + API-CONTRACTS."
        ),
        "confidence": 0.95,
    }

    if args.evidence_out:
        Path(args.evidence_out).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(f"  Evidence: {args.evidence_out}", file=sys.stderr)

    if args.strict:
        print(f"BLOCK: {summary}", file=sys.stderr)
        return 1

    print(f"WARN: {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
