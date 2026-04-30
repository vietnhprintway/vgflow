#!/usr/bin/env python3
"""roam-discover-surfaces.py (v1.0 stub)

Discover CRUD-bearing surfaces in a phase by reading PLAN.md, CONTEXT.md,
RUNTIME-MAP.md. Emit SURFACES.md table with: id | url | role | entity | crud | sub_views.

v1.0 stub: parses obvious markers (route paths in PLAN.md, role mentions
in CONTEXT.md). Real impl in v1.1 will use graphify edges + RUNTIME-MAP
parser. For now this gets ENOUGH structure for the commander to compose
briefs.

Spec: .vg/research/ROAM-RFC-v1.md section 3, Phase 0.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CRUD_KEYWORDS = {
    "create": "C",
    "new": "C",
    "add": "C",
    "list": "R",
    "view": "R",
    "show": "R",
    "edit": "U",
    "update": "U",
    "delete": "D",
    "remove": "D",
}


def extract_routes(text: str) -> list[str]:
    """Find route-like strings: /admin/foo, /merchant/bar/{id}, etc.

    Filter out filesystem paths that share the prefix (e.g. apps/admin/src/...,
    /admin/src/api/foo.api.ts). Routes do not contain file extensions and
    don't have segments matching common code-tree dirs.
    """
    candidates = set(re.findall(r"/(?:admin|merchant|vendor|api|app|user|m)/[\w/{}\-:.]+", text))

    # Reject candidates that look like filesystem paths
    code_segments = {"src", "dist", "node_modules", "build", "public", "static", "assets",
                     "lib", "tests", "test", "__tests__", "components", "pages"}
    file_ext_re = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|css|scss|sass|json|html|md|sql|py|rs|go|rb|java)\b")

    filtered = []
    for c in candidates:
        # Reject if any path segment matches a code-tree directory
        segs = [s for s in c.split("/") if s]
        if any(seg in code_segments for seg in segs):
            continue
        # Reject if has a file extension
        if file_ext_re.search(c):
            continue
        # Strip trailing dots/dashes (regex artifact)
        c = c.rstrip(".").rstrip("-")
        if c:
            filtered.append(c)
    return list(set(filtered))


def extract_entities(text: str) -> set[str]:
    """Pull noun phrases that look like entities (heuristic)."""
    # Look for "the {entity}" or "{entity} record" or "{entity}.id" patterns
    candidates = set()
    for m in re.finditer(r"\b(invoice|order|product|user|customer|account|payment|credit|design|task|review|comment|payout|shipment|vendor|merchant|inventory|catalog|listing|coupon|discount|notification|webhook|setting|preference|role|permission|tag|category|brand|file|attachment|message|thread)s?\b", text, re.I):
        candidates.add(m.group(1).lower())
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-surfaces", type=int, default=50)
    args = ap.parse_args()

    phase_dir = Path(args.phase_dir)
    sources = []
    for f in ("PLAN.md", "CONTEXT.md", "RUNTIME-MAP.md", "RUNTIME-MAP-DRAFT.md", "API-CONTRACTS.md"):
        p = phase_dir / f
        if p.exists():
            sources.append((f, p.read_text(encoding="utf-8", errors="replace")))

    if not sources:
        print(f"[roam-discover] no source artifacts in {phase_dir} — phase too early?", file=sys.stderr)
        return 2

    all_text = "\n".join(t for _, t in sources)
    routes = extract_routes(all_text)
    entities = extract_entities(all_text)

    # Build surfaces table — heuristic: each route × associated entity → 1 surface
    surfaces = []
    for i, route in enumerate(sorted(routes)[: args.max_surfaces], 1):
        # Infer role from route prefix
        role = "admin" if "/admin/" in route else "merchant" if "/merchant/" in route else "vendor" if "/vendor/" in route else "user"
        # Infer entity from path segment
        entity = next((e for e in entities if e in route.lower()), "?")
        # Infer CRUD ops from route path keywords
        crud = ""
        for kw, op in CRUD_KEYWORDS.items():
            if kw in route.lower() and op not in crud:
                crud += op
        if not crud:
            crud = "R"  # default — at minimum, surface is readable
        surfaces.append({
            "id": f"S{i:02d}",
            "url": route,
            "role": role,
            "entity": entity,
            "crud": crud,
            "sub_views": "",
        })

    # Write SURFACES.md
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Surfaces — Phase {phase_dir.name}",
        "",
        f"Auto-discovered from: {', '.join(name for name, _ in sources)}",
        f"Total: {len(surfaces)} (max cap: {args.max_surfaces})",
        "",
        "| ID  | URL | Role | Entity | CRUD | Sub-views |",
        "|-----|-----|------|--------|------|-----------|",
    ]
    for s in surfaces:
        lines.append(f"| {s['id']} | `{s['url']}` | {s['role']} | {s['entity']} | {s['crud']} | {s['sub_views']} |")

    lines += [
        "",
        "**Note (v1.0 stub):** route + entity inference is heuristic. Edit this file manually to refine before composing briefs. v1.1 will wire to graphify edges for ground-truth.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[roam-discover] wrote {len(surfaces)} surfaces to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
