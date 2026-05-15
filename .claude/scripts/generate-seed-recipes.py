#!/usr/bin/env python3
"""Batch 51: derive SEED-RECIPE.md per phase from LIFECYCLE-SPECS.

Test specs without seed contract drift at runtime — empty_state test
runs on env with 15 rows, pagination_edge on env with 5 rows, etc.

This generator reads LIFECYCLE-SPECS.json (Batches 36-37) +
state_observations from scan-*.json (Batch 41) and emits per-variant
seed recipes. AI subagent fills concrete SQL/API in a follow-up pass.

Batch 54: now also reads phase_dir/scan-*.json files (Haiku scanner
output) and attaches an `observed_state` block per recipe when scan
signals match the variant kind:
  - filter_combination → real filter names + options
  - pagination_edge    → observed total_pages / row_count
  - empty_string / boundary → observed state_observations
  - not_found_404      → scan.state_observations.error_state_4xx

The static template still ships as fallback; observed_state augments
(it does NOT replace) so AI follow-up always has both.

Output: ${PHASE_DIR}/SEED-RECIPE.md with one recipe per variant_id.

Schema per recipe:
  - variant_id: G-NN-{kind}{idx}
  - requires_state: human-readable precondition
  - seed_action: <PLACEHOLDER> for AI to fill (SQL/API/CLI)
  - cleanup: <PLACEHOLDER> for AI to fill
  - idempotent: bool (whether re-run is safe)
  - observed_state: dict of real values pulled from scan-*.json (Batch 54)

Usage:
  generate-seed-recipes.py --phase 7
  generate-seed-recipes.py --phase 7 --force
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


# Map edge_case.kind / negative_spec.kind → seed pattern hint.
KIND_TO_RECIPE = {
    # Edge cases (Batch 37)
    "boundary":          {"req": "field value at min/max boundary",
                          "seed": "<INSERT row with field = boundary value>",
                          "cleanup": "<DELETE seeded row>",
                          "idempotent": True},
    "empty_string":      {"req": "field with empty string for optional field",
                          "seed": "<INSERT row with optional field = ''>",
                          "cleanup": "<DELETE seeded row>",
                          "idempotent": True},
    "unicode_special":   {"req": "field with unicode/emoji/RTL/special chars",
                          "seed": "<INSERT row with field = '包含中文 🎉 العربية'>",
                          "cleanup": "<DELETE seeded row>",
                          "idempotent": True},
    "large_payload":     {"req": "row at max payload size",
                          "seed": "<INSERT row with field = repeat('a', MAX_LENGTH)>",
                          "cleanup": "<DELETE seeded row>",
                          "idempotent": True},
    "filter_combination":{"req": ">=2 rows matching different filter combinations",
                          "seed": "<INSERT 5 rows with varied status+owner combos>",
                          "cleanup": "<DELETE WHERE name LIKE 'seed-filter-%'>",
                          "idempotent": True},
    "pagination_edge":   {"req": ">=31 rows visible to test user (>=2 pages at default page_size=30)",
                          "seed": "<INSERT 35 rows: e.g. INSERT INTO {table} SELECT generate_series(1,35), ...>",
                          "cleanup": "<DELETE WHERE name LIKE 'seed-pag-%'>",
                          "idempotent": True},
    # Negative specs (Batch 37)
    "unauthorized_401":  {"req": "unauthenticated session (no auth cookie/token)",
                          "seed": "page.context().clearCookies()",
                          "cleanup": "none (test re-authenticates via global-setup)",
                          "idempotent": True},
    "forbidden_403":     {"req": "authenticated user lacking required permission",
                          "seed": "<login as role without permission>",
                          "cleanup": "<logout + restore default test role>",
                          "idempotent": True},
    "validation_422":    {"req": "request payload with required field missing/malformed",
                          "seed": "in-test: POST with field={} or field=null",
                          "cleanup": "<DELETE any partial mutation> (usually none if 422 = no write)",
                          "idempotent": True},
    "not_found_404":     {"req": "id that doesn't exist or was deleted",
                          "seed": "use id='99999999-fake-id-probe'",
                          "cleanup": "none",
                          "idempotent": True},
    "rate_limit_429":    {"req": "burst rate above limiter threshold",
                          "seed": "in-test: rapid loop of requests beyond burst_limit",
                          "cleanup": "wait Retry-After seconds before next test",
                          "idempotent": False},
}


def _load_scans(phase_dir: Path) -> list[dict]:
    """Batch 54: load every scan-*.json under phase_dir."""
    scans: list[dict] = []
    if not phase_dir.is_dir():
        return scans
    for scan_file in sorted(phase_dir.glob("scan-*.json")):
        try:
            scans.append(json.loads(scan_file.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return scans


def _aggregate_scan_signals(scans: list[dict]) -> dict:
    """Batch 54: aggregate cross-scan signals used to inform recipes.

    Returns a dict shaped:
      {
        "filters":          [{name, options, near_table_ref, view}],
        "pagination":       [{total_pages, row_count, page_size, view}],
        "row_counts":       [{view, ref, row_count}],
        "empty_state":      {trigger, message_text, view} | None,
        "error_state_4xx":  {expected_status, trigger, view} | None,
        "error_state_5xx":  {trigger, view} | None,
        "loading_state":    {trigger, view} | None,
        "search":           [{placeholder, debounce_ms_observed, view}],
        "views_scanned":    int,
      }
    """
    agg: dict = {
        "filters": [],
        "pagination": [],
        "row_counts": [],
        "empty_state": None,
        "error_state_4xx": None,
        "error_state_5xx": None,
        "loading_state": None,
        "search": [],
        "views_scanned": len(scans),
    }
    for scan in scans:
        view = scan.get("view") or scan.get("view_slug") or "?"
        for f in scan.get("filters") or []:
            if isinstance(f, dict) and f.get("name"):
                agg["filters"].append({
                    "name": f.get("name"),
                    "options": f.get("options"),
                    "kind": f.get("kind"),
                    "near_table_ref": f.get("near_table_ref"),
                    "view": view,
                })
        pag = scan.get("pagination")
        if isinstance(pag, dict) and pag.get("present"):
            agg["pagination"].append({
                "total_pages": pag.get("total_pages"),
                "current_page": pag.get("current_page"),
                "page_size": pag.get("page_size"),
                "view": view,
            })
        for t in scan.get("tables") or []:
            if isinstance(t, dict) and t.get("row_count") is not None:
                agg["row_counts"].append({
                    "view": view,
                    "ref": t.get("ref"),
                    "row_count": t.get("row_count"),
                })
        st = scan.get("state_observations") or {}
        if isinstance(st, dict):
            es = st.get("empty_state")
            if agg["empty_state"] is None and isinstance(es, dict) and es.get("observed"):
                agg["empty_state"] = {
                    "trigger": es.get("trigger"),
                    "message_text": es.get("message_text"),
                    "view": view,
                }
            er4 = st.get("error_state_4xx")
            if agg["error_state_4xx"] is None and isinstance(er4, dict) and er4.get("observed"):
                agg["error_state_4xx"] = {
                    "expected_status": er4.get("expected_status"),
                    "actual_status": er4.get("actual_status"),
                    "trigger": er4.get("trigger"),
                    "view": view,
                }
            er5 = st.get("error_state_5xx")
            if agg["error_state_5xx"] is None and isinstance(er5, dict) and er5.get("observed"):
                agg["error_state_5xx"] = {
                    "trigger": er5.get("trigger"),
                    "view": view,
                }
            lo = st.get("loading_state")
            if agg["loading_state"] is None and isinstance(lo, dict) and lo.get("observed"):
                agg["loading_state"] = {
                    "trigger": lo.get("trigger"),
                    "view": view,
                }
        for s in scan.get("search") or []:
            if isinstance(s, dict):
                agg["search"].append({
                    "placeholder": s.get("placeholder"),
                    "debounce_ms_observed": s.get("debounce_ms_observed"),
                    "view": view,
                })
    return agg


def _observed_for_kind(kind: str, agg: dict) -> dict | None:
    """Batch 54: pick observed_state subset relevant for this kind."""
    if kind == "filter_combination":
        if not agg["filters"]:
            return None
        return {
            "real_filters": agg["filters"][:6],
            "hint": (
                "Use observed filter options to seed >=2 rows hitting "
                "different combinations; do NOT invent filter names."
            ),
        }
    if kind == "pagination_edge":
        if not agg["pagination"] and not agg["row_counts"]:
            return None
        return {
            "real_pagination": agg["pagination"][:3] or None,
            "real_row_counts": agg["row_counts"][:6] or None,
            "hint": (
                "Use observed page_size to compute required seed count "
                "(seed_count = page_size + 5). Cleanup MUST remove only the "
                "rows the test inserted."
            ),
        }
    if kind == "empty_string":
        # use observed empty_state as cross-check (informational)
        if agg["empty_state"] is None:
            return None
        return {"empty_state": agg["empty_state"]}
    if kind == "not_found_404":
        if agg["error_state_4xx"] is None:
            return None
        return {"error_state_4xx": agg["error_state_4xx"]}
    if kind == "rate_limit_429":
        # no direct scan signal; emit None so recipe stays static
        return None
    if kind == "boundary":
        # boundary uses search debounce + row count as indirect signal
        if not agg["row_counts"] and not agg["search"]:
            return None
        out: dict = {}
        if agg["row_counts"]:
            out["real_row_counts"] = agg["row_counts"][:3]
        if agg["search"]:
            out["real_search"] = agg["search"][:3]
        return out
    return None


def _find_phase_dir(phase: str, override: str | None = None) -> Path:
    if override:
        return Path(override)
    for root in (Path(".vg/phases"), Path("dev-phases"), Path("phases")):
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if p.is_dir() and (p.name == phase or p.name.startswith(f"{phase}-")):
                return p
    raise SystemExit(f"phase dir not found for {phase}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:30]


def _variant_id(goal_id: str, kind: str, idx: int) -> str:
    """Match derive-edge-cases-from-lifecycle.py (Batch 48) format."""
    letter = (kind[:1].lower() or "x")
    return f"{goal_id}-{letter}{idx}"


def _render_recipe_md(phase: str, recipes: list[dict]) -> str:
    lines = [
        f"# SEED-RECIPE — Phase {phase}",
        "",
        f"_Auto-derived by Batch 51 (generate-seed-recipes.py)._",
        f"_Source: LIFECYCLE-SPECS.json edge_cases[] + negative_specs[]._",
        "",
        f"## Purpose",
        "",
        "Each test spec variant (edge case + negative path) requires specific",
        "data state BEFORE running. Without seed contract, specs drift at runtime",
        "— empty_state expects 0 rows but env has 15, pagination_edge expects",
        ">=31 but env has 5, etc.",
        "",
        f"## Recipes ({len(recipes)} variants)",
        "",
        "Codegen subagent MUST read each recipe and wrap matching `test.each(variant)`",
        "with `beforeEach: runSeedRecipe(variant.id)` + `afterEach: cleanup(variant.id)`.",
        "",
        "AI follow-up pass fills `<PLACEHOLDER>` values with project-specific",
        "SQL/API/CLI based on CONTEXT.md, API-CONTRACTS.md, and observed schema.",
        "",
    ]
    for rec in recipes:
        lines.append(f"### {rec['variant_id']}")
        lines.append("")
        lines.append(f"- **goal**: {rec['goal_id']} — {rec.get('goal_title', '')}")
        lines.append(f"- **kind**: `{rec['kind']}` ({rec.get('source', '?')})")
        lines.append(f"- **requires_state**: {rec['requires_state']}")
        lines.append(f"- **idempotent**: {rec['idempotent']}")
        if rec.get("observed_state"):
            lines.append(f"- **observed_state**: Batch 54 — see block below for real values from scan-*.json")
        lines.append("")
        lines.append("```yaml")
        lines.append(f"variant_id: {rec['variant_id']}")
        lines.append(f"goal_id: {rec['goal_id']}")
        lines.append(f"kind: {rec['kind']}")
        lines.append(f"requires_state: \"{rec['requires_state']}\"")
        lines.append(f"seed_action: |")
        lines.append(f"  {rec['seed_action']}")
        lines.append(f"cleanup: |")
        lines.append(f"  {rec['cleanup']}")
        lines.append(f"idempotent: {str(rec['idempotent']).lower()}")
        if rec.get("observed_state"):
            obs_json = json.dumps(rec["observed_state"], ensure_ascii=False, indent=2)
            obs_indented = "\n".join("  " + ln for ln in obs_json.splitlines())
            lines.append(f"observed_state:")
            lines.append(obs_indented)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def derive_recipes(lifecycle: dict, scan_agg: dict | None = None) -> list[dict]:
    """For each goal in LIFECYCLE-SPECS, expand edge_cases + negative_specs.

    Batch 54: when scan_agg provided, attach observed_state per recipe so
    AI follow-up has real values (filter names, row counts, pagination
    sizes) instead of inventing them.
    """
    recipes: list[dict] = []
    goals = lifecycle.get("goals") or {}
    for gid, gspec in sorted(goals.items()):
        if not isinstance(gspec, dict):
            continue
        title = gspec.get("title", "")
        # Edge cases (Batch 37)
        for idx, ec in enumerate(gspec.get("edge_cases") or [], 1):
            if not isinstance(ec, dict):
                continue
            kind = ec.get("kind") or "unknown"
            template = KIND_TO_RECIPE.get(kind, {
                "req": ec.get("expected", "(see edge_cases[].expected)"),
                "seed": "<PLACEHOLDER — describe how to reach state>",
                "cleanup": "<PLACEHOLDER>",
                "idempotent": True,
            })
            rec = {
                "variant_id": _variant_id(gid, kind, idx),
                "goal_id": gid,
                "goal_title": title,
                "kind": kind,
                "source": "edge_cases",
                "requires_state": template["req"],
                "seed_action": template["seed"],
                "cleanup": template["cleanup"],
                "idempotent": template["idempotent"],
            }
            if scan_agg:
                obs = _observed_for_kind(kind, scan_agg)
                if obs:
                    rec["observed_state"] = obs
            recipes.append(rec)
        # Negative specs (Batch 37)
        for idx, neg in enumerate(gspec.get("negative_specs") or [], 1):
            if not isinstance(neg, dict):
                continue
            kind = neg.get("kind") or "unknown"
            template = KIND_TO_RECIPE.get(kind, {
                "req": neg.get("setup", "(see negative_specs[].setup)"),
                "seed": "<PLACEHOLDER>",
                "cleanup": "<PLACEHOLDER>",
                "idempotent": True,
            })
            # Use 'n' prefix for negative variants to distinguish from edge
            variant_id = f"{gid}-n{idx}"
            rec = {
                "variant_id": variant_id,
                "goal_id": gid,
                "goal_title": title,
                "kind": kind,
                "source": "negative_specs",
                "requires_state": template["req"],
                "seed_action": template["seed"],
                "cleanup": template["cleanup"],
                "idempotent": template["idempotent"],
            }
            if scan_agg:
                obs = _observed_for_kind(kind, scan_agg)
                if obs:
                    rec["observed_state"] = obs
            recipes.append(rec)
    return recipes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--phase-dir")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    phase_dir = _find_phase_dir(args.phase, args.phase_dir)
    lifecycle_path = phase_dir / "LIFECYCLE-SPECS.json"
    if not lifecycle_path.is_file():
        print(f"⛔ Batch 51: LIFECYCLE-SPECS.json missing at {lifecycle_path}", file=sys.stderr)
        return 1
    try:
        lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⛔ Batch 51: malformed LIFECYCLE-SPECS.json: {e}", file=sys.stderr)
        return 1

    out_path = phase_dir / "SEED-RECIPE.md"
    if out_path.is_file() and not args.force:
        print(f"ℹ Batch 51: {out_path} exists (use --force to overwrite)")
        return 0

    # Batch 54: aggregate scan signals to inform recipes
    scans = _load_scans(phase_dir)
    scan_agg = _aggregate_scan_signals(scans) if scans else None

    recipes = derive_recipes(lifecycle, scan_agg=scan_agg)
    if not recipes:
        print(f"ℹ Batch 51: no edge_cases/negative_specs in LIFECYCLE-SPECS — nothing to seed")
        return 0

    body = _render_recipe_md(args.phase, recipes)
    if args.dry_run:
        print(body)
    else:
        out_path.write_text(body, encoding="utf-8")
    obs_count = sum(1 for r in recipes if r.get("observed_state"))
    scan_note = f" ({len(scans)} scan files, {obs_count} recipes augmented)" if scans else ""
    print(f"✓ Batch 51: wrote {len(recipes)} seed recipes to {out_path.name}{scan_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
