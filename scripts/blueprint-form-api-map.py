#!/usr/bin/env python3
"""F3 v2.62.0 — FORM-API-MAP generator.

Run during `/vg:blueprint` after BLOCK 5 (FE consumer contract). Parses
structural.html files in design assets, extracts <form> action/method +
<input>/<select>/<textarea> name attrs + types, then cross-references with
API-CONTRACTS request schema field names. Emits ${PHASE_DIR}/FORM-API-MAP.md.

Drift point fixed: D4 — RTB save-form 422 errors (FE sends `user_email`,
BE expects `email`). Existing validators check URL/method match (call-graph)
and BLOCK 5 schema completeness, but no field-level cross-reference.

Match strategy:
  1. Exact match
  2. Case-insensitive
  3. snake_case ↔ camelCase normalize
  4. Otherwise NAME-DRIFT.

Hidden inputs (`type="hidden"`) prefixed with _csrf|_token|_method are flagged
HEADER. Forms without `action=` are skipped (client-side only).

Usage:
    blueprint-form-api-map.py --phase {N} [--phase-dir {path}] [--strict]

Exit codes:
  0 = OK (no drift, or drift but --strict not passed → WARN-only)
  1 = drift detected with --strict (BLOCK)
  2 = invocation error / missing inputs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

HEADER_PREFIXES = ("_csrf", "_token", "_method")


class FormParser(HTMLParser):
    """Stack-based parser to extract forms + nested input/select/textarea."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self._stack: list[dict] = []  # form stack (track nested for safety)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "form":
            form = {
                "id": a.get("id", ""),
                "action": a.get("action", ""),
                "method": (a.get("method", "GET") or "GET").upper(),
                "inputs": [],
            }
            self.forms.append(form)
            self._stack.append(form)
            return
        if tag.lower() in ("input", "select", "textarea") and self._stack:
            field = {
                "tag": tag.lower(),
                "name": a.get("name", ""),
                "type": a.get("type", "text" if tag.lower() != "select" else "select"),
                "required": "required" in a,
                "pattern": a.get("pattern", ""),
            }
            if field["name"]:
                self._stack[-1]["inputs"].append(field)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._stack:
            self._stack.pop()


def parse_forms(html_text: str) -> list[dict]:
    p = FormParser()
    try:
        p.feed(html_text)
    except Exception:
        pass
    return p.forms


def parse_api_contract_fields(contract_text: str) -> tuple[str | None, str | None, list[str]]:
    """Extract method, path, and request body field names from BLOCK 1.

    Looks for a top-level heading like `# POST /auth/login` (method + path),
    then any ```typescript fenced block under BLOCK 1 (request schema).
    Returns (method, path, [field_names]).
    """
    method = None
    path = None
    m_h = re.search(r"^#\s+(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", contract_text, re.MULTILINE)
    if m_h:
        method = m_h.group(1).upper()
        path = m_h.group(2)

    fields: list[str] = []
    # Try BLOCK 1 first
    block1 = re.search(
        r"##\s+BLOCK\s+1[^\n]*\n+```(?:typescript|ts)\n(?P<body>.+?)\n```",
        contract_text, re.DOTALL,
    )
    body = block1.group("body") if block1 else None
    if body is None:
        # Fallback: any typescript fenced block
        m_any = re.search(r"```(?:typescript|ts)\n(?P<body>.+?)\n```", contract_text, re.DOTALL)
        if m_any:
            body = m_any.group("body")
    if body:
        # Strip outer braces and split fields liberally — handle both
        # multi-line and single-line schemas like `{ aB: string }`.
        # Tokenize by commas / newlines, then match `name?: type` per chunk.
        chunks = re.split(r"[,\n]", body)
        for chunk in chunks:
            chunk = chunk.strip().strip("{}").strip().rstrip(",;")
            if not chunk or chunk.startswith("//"):
                continue
            m_field = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\??\s*:", chunk)
            if m_field:
                fields.append(m_field.group(1))
    return method, path, fields


def snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def camel_to_snake(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def field_match(html_name: str, api_fields: list[str]) -> tuple[str | None, str]:
    """Return (matched_api_field_or_None, status). Status one of:
    EXACT | CI | NORMALIZED | DRIFT | NO-API.
    """
    if not api_fields:
        return None, "NO-API"
    if html_name in api_fields:
        return html_name, "EXACT"
    lower_map = {f.lower(): f for f in api_fields}
    if html_name.lower() in lower_map:
        return lower_map[html_name.lower()], "CI"
    # Normalize both directions
    cm = snake_to_camel(html_name)
    sn = camel_to_snake(html_name)
    if cm in api_fields:
        return cm, "NORMALIZED"
    if sn in api_fields:
        return sn, "NORMALIZED"
    # Try reverse: any api field whose normalized form equals html_name
    for f in api_fields:
        if snake_to_camel(f) == html_name or camel_to_snake(f) == html_name:
            return f, "NORMALIZED"
    return None, "DRIFT"


def find_structural_html_files(phase_dir: Path) -> list[Path]:
    """Locate structural.html files under design/refs/ in the phase dir."""
    files: list[Path] = []
    for sub in ("design", "designs"):
        refs = phase_dir / sub / "refs"
        if refs.is_dir():
            files.extend(sorted(refs.glob("*.structural.html")))
    return files


def find_api_contracts(phase_dir: Path) -> list[Path]:
    """Locate API-CONTRACTS/*.md files (skip index.md)."""
    contracts_dir = phase_dir / "API-CONTRACTS"
    if not contracts_dir.is_dir():
        return []
    return sorted(p for p in contracts_dir.glob("*.md") if p.name != "index.md")


def match_form_to_endpoint(form: dict, contracts: list[tuple[Path, str | None, str | None, list[str]]]):
    """Best-effort match of a form's (method, action) to an API contract.
    Returns the contract tuple or None.
    """
    f_method = form.get("method", "POST").upper()
    f_action = form.get("action", "").strip()
    if not f_action:
        return None
    # Normalize action — strip trailing slash, leading ./
    norm_action = f_action.rstrip("/").lstrip("./") or "/"
    if not norm_action.startswith("/"):
        norm_action = "/" + norm_action
    for ct in contracts:
        _, c_method, c_path, _ = ct
        if not c_method or not c_path:
            continue
        c_norm = c_path.rstrip("/")
        if not c_norm.startswith("/"):
            c_norm = "/" + c_norm
        # Exact match (after path-param normalize on BE side)
        be_param = re.sub(r":[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\}", ":param", c_norm)
        fe_param = re.sub(r":[A-Za-z_][A-Za-z0-9_]*|\{[^}]+\}", ":param", norm_action)
        if c_method == f_method and (c_norm == norm_action or be_param == fe_param):
            return ct
    # Fallback: if only one contract is available with extractable fields, use
    # it for cross-reference even if method/path heading was missing. Avoids
    # silent NO-API status when contract clearly exists but lacks `# METHOD /path`.
    contracts_with_fields = [c for c in contracts if c[3]]
    if len(contracts_with_fields) == 1:
        return contracts_with_fields[0]
    return None


def render_field_row(html_field: dict, api_field: str | None, status: str) -> str:
    name = html_field["name"]
    htype = html_field["type"]
    required = "yes" if html_field["required"] else "no"
    pattern = html_field["pattern"] or "—"
    if htype == "hidden" and any(name.startswith(p) for p in HEADER_PREFIXES):
        marker = "◇ HEADER"
        api_repr = f"(header: X-{name.lstrip('_').upper()}-Token)" if "csrf" in name else "(header)"
        api_type = "—"
    elif status == "EXACT" or status == "CI":
        marker = "✓"
        api_repr = api_field or name
        api_type = "string"
    elif status == "NORMALIZED":
        # snake_case ↔ camelCase mismatch is a real drift at runtime —
        # browsers send exactly what the HTML name attr says, no normalization.
        marker = "⚠ NAME-DRIFT (case)"
        api_repr = api_field or name
        api_type = "string"
    elif status == "DRIFT":
        marker = "⚠ NAME-DRIFT"
        api_repr = "(no match)"
        api_type = "—"
    else:  # NO-API
        marker = "◇ NO-API-CONTRACT"
        api_repr = "—"
        api_type = "—"
    return f"| {name} | {htype} | {required} | {pattern} | {api_repr} | {api_type} | {marker} |"


def render_form_section(form: dict, contract_match: tuple | None, slug: str) -> tuple[str, int]:
    """Return (markdown, drift_count) for one form."""
    lines: list[str] = []
    fid = form.get("id") or "(unnamed)"
    lines.append(f"## {fid} (from {slug})")
    lines.append("")
    lines.append(f"**Form action:** `{form.get('action', '')}`  ")
    lines.append(f"**Form method:** `{form.get('method', 'POST')}`  ")

    if contract_match:
        path, c_method, c_path, api_fields = contract_match
        lines.append(
            f"**Mapped endpoint:** `{c_method} {c_path}` (from API-CONTRACTS/{path.name})"
        )
    else:
        api_fields = []
        lines.append("**Mapped endpoint:** (no API-CONTRACTS file matches form action)")

    lines.append("")
    lines.append("| HTML name attr | HTML type | required | pattern | API field | API type | Match |")
    lines.append("|---|---|---|---|---|---|---|")

    drift_count = 0
    header_count = 0
    for inp in form.get("inputs", []):
        if inp["type"] == "hidden" and any(inp["name"].startswith(p) for p in HEADER_PREFIXES):
            row = render_field_row(inp, None, "HEADER")
            header_count += 1
        else:
            api_match, status = field_match(inp["name"], api_fields)
            if status in ("DRIFT", "NORMALIZED"):
                drift_count += 1
            row = render_field_row(inp, api_match, status)
        lines.append(row)

    lines.append("")
    if drift_count:
        lines.append(f"**Drift detected:** {drift_count} NAME-DRIFT row(s)")
        lines.append(
            "**Resolution hint:** Either rename HTML form fields to match API "
            "contract OR add API contract field aliases (e.g. "
            "`displayName: alias_for=display_name`)."
        )
        lines.append("")
    return "\n".join(lines), drift_count


def main() -> int:
    p = argparse.ArgumentParser(description="Generate FORM-API-MAP.md for a phase")
    p.add_argument("--phase", required=True, help="Phase number (e.g. 1.0)")
    p.add_argument("--phase-dir", help="Explicit phase directory (auto-derived if omitted)")
    p.add_argument("--strict", action="store_true",
                   help="Block (rc=1) on any NAME-DRIFT row")
    p.add_argument("--out", help="Override output path (default: ${PHASE_DIR}/FORM-API-MAP.md)")
    args = p.parse_args()

    if args.phase_dir:
        phase_dir = Path(args.phase_dir)
    else:
        phase_dir = REPO_ROOT / ".vg" / "phases" / args.phase

    if not phase_dir.is_dir():
        print(f"ERROR: phase dir not found: {phase_dir}", file=sys.stderr)
        return 2

    structural_files = find_structural_html_files(phase_dir)
    contract_files = find_api_contracts(phase_dir)

    contracts_parsed: list[tuple[Path, str | None, str | None, list[str]]] = []
    for cf in contract_files:
        try:
            text = cf.read_text(encoding="utf-8")
        except Exception as e:
            print(f"WARN: cannot read {cf}: {e}", file=sys.stderr)
            continue
        method, path, fields = parse_api_contract_fields(text)
        contracts_parsed.append((cf, method, path, fields))

    out_lines: list[str] = []
    out_lines.append(f"# Form ↔ API field map — Phase {args.phase}")
    out_lines.append("")
    out_lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    out_lines.append("Source: structural.html × API-CONTRACTS/<endpoint>.md")
    out_lines.append("")

    total_drift = 0
    forms_emitted = 0
    skipped_no_action = 0

    for sf in structural_files:
        slug = sf.name.removesuffix(".structural.html")
        try:
            html_text = sf.read_text(encoding="utf-8")
        except Exception as e:
            print(f"WARN: cannot read {sf}: {e}", file=sys.stderr)
            continue
        forms = parse_forms(html_text)
        for form in forms:
            if not form.get("action"):
                skipped_no_action += 1
                continue
            cm = match_form_to_endpoint(form, contracts_parsed)
            section, drift_count = render_form_section(form, cm, slug)
            out_lines.append(section)
            forms_emitted += 1
            total_drift += drift_count

    if forms_emitted == 0:
        out_lines.append("_No mappable forms found (all forms either lacked `action=` "
                         "or no structural.html files exist)._")
        if skipped_no_action:
            out_lines.append(f"_Skipped {skipped_no_action} form(s) without action= attribute._")
        out_lines.append("")

    out_lines.append("---")
    out_lines.append(f"_Forms emitted: {forms_emitted} | "
                     f"Skipped (no action): {skipped_no_action} | "
                     f"Total NAME-DRIFT rows: {total_drift}_")

    out_path = Path(args.out) if args.out else phase_dir / "FORM-API-MAP.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"FORM-API-MAP written: {out_path} (forms={forms_emitted}, drift={total_drift})")

    if args.strict and total_drift > 0:
        print(f"BLOCK: {total_drift} NAME-DRIFT row(s) detected with --strict",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
