#!/usr/bin/env python3
"""Batch 55: emit runSeedRecipe / cleanup helper stub per phase.

Codegen subagent (Batch 52) wraps test.each(variant) with
`await runSeedRecipe(variant.id)` / `await cleanup(variant.id)`. But
those helper functions DON'T EXIST unless humans hand-write them →
test runtime fails with `runSeedRecipe is not defined` OR silently
no-ops if the project shimmed an empty fn.

This script reads SEED-RECIPE.md and emits a switch/case helper stub
per variant_id. Each branch THROWS by default ("seed handler not
implemented — fill from SEED-RECIPE.md") so the failure is LOUD at
test runtime instead of silent drift.

Output (default):
  ${PHASE_DIR}/tests/_helpers/seed-recipes.ts
  (or .js with --lang js)

Schema (TypeScript):
  export async function runSeedRecipe(variantId, ctx?) { switch... }
  export async function cleanup(variantId, ctx?) { switch... }

Each variant case has:
  - kind comment
  - requires_state comment
  - seed_action / cleanup placeholder
  - observed_state JSON comment (Batch 54) when present
  - throw new Error stub (AI replaces with concrete SQL/API)

Usage:
  generate-seed-helper-stub.py --phase 7
  generate-seed-helper-stub.py --phase 7 --lang ts --force
  generate-seed-helper-stub.py --phase 7 --out custom/path.ts
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


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


YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)


def _parse_recipes(text: str) -> list[dict]:
    """Parse ```yaml fences from SEED-RECIPE.md. Returns list of dicts.

    Each recipe has: variant_id, goal_id, kind, requires_state,
    seed_action, cleanup, idempotent, observed_state (optional).
    """
    recipes: list[dict] = []
    for m in YAML_FENCE_RE.finditer(text):
        block = m.group(1)
        rec = _parse_yaml_block(block)
        if rec.get("variant_id"):
            recipes.append(rec)
    return recipes


def _parse_yaml_block(block: str) -> dict:
    """Tiny YAML subset parser — handles flat keys + observed_state JSON.

    Format produced by generate-seed-recipes.py:
      variant_id: G-01-b1
      goal_id: G-01
      kind: boundary
      requires_state: "..."
      seed_action: |
        multi-line
      cleanup: |
        multi-line
      idempotent: true
      observed_state:
        {JSON}
    """
    rec: dict = {}
    lines = block.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln:
            i += 1
            continue
        m = re.match(r"^([\w_]+):\s*(.*)$", ln)
        if not m:
            i += 1
            continue
        key = m.group(1)
        val = m.group(2)
        if val == "|":
            # block scalar — consume indented lines
            chunks: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t") or not lines[i].strip()):
                chunks.append(re.sub(r"^  ", "", lines[i]))
                i += 1
            rec[key] = "\n".join(chunks).strip()
            continue
        if key == "observed_state":
            # consume indented JSON until indent breaks
            json_lines: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                json_lines.append(re.sub(r"^  ", "", lines[i]))
                i += 1
            try:
                rec["observed_state"] = json.loads("\n".join(json_lines))
            except json.JSONDecodeError:
                rec["observed_state"] = None
            continue
        # plain scalar — strip quotes
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        if val.lower() in ("true", "false"):
            rec[key] = val.lower() == "true"
        else:
            rec[key] = val
        i += 1
    return rec


def _ts_string_literal(s: str) -> str:
    """Escape string for TypeScript single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _format_case(rec: dict, action_field: str, lang: str) -> str:
    """Format one switch/case branch for runSeedRecipe or cleanup."""
    variant_id = rec.get("variant_id", "?")
    kind = rec.get("kind", "?")
    requires = rec.get("requires_state", "")
    action = rec.get(action_field) or "<PLACEHOLDER>"
    observed = rec.get("observed_state")

    lines: list[str] = []
    lines.append(f"    case '{_ts_string_literal(variant_id)}': {{")
    lines.append(f"      // kind: {kind}")
    if requires:
        lines.append(f"      // requires_state: {requires}")
    # split action across lines as comment
    for ln in action.splitlines() or [action]:
        lines.append(f"      // {action_field}: {ln}")
    if observed:
        obs_json = json.dumps(observed, ensure_ascii=False)
        # truncate noisy long JSON in comment to keep stub readable
        if len(obs_json) > 200:
            obs_json = obs_json[:200] + "…"
        lines.append(f"      // observed_state: {obs_json}")
    # decide stub body — runSeedRecipe throws, cleanup returns (idempotent)
    if action_field == "seed_action":
        lines.append(f"      throw new Error('Seed handler for {variant_id} not implemented — fill from SEED-RECIPE.md');")
    else:
        lines.append(f"      // TODO: implement cleanup (idempotent: {str(rec.get('idempotent', True)).lower()})")
        lines.append(f"      return;")
    lines.append(f"    }}")
    return "\n".join(lines)


def render_ts(recipes: list[dict], phase: str) -> str:
    """Render TypeScript helper module."""
    if not recipes:
        return _render_empty_ts(phase)
    seed_cases = "\n".join(_format_case(r, "seed_action", "ts") for r in recipes)
    cleanup_cases = "\n".join(_format_case(r, "cleanup", "ts") for r in recipes)
    return f"""// Auto-generated by Batch 55 (scripts/generate-seed-helper-stub.py).
// Phase: {phase}
// Re-run after SEED-RECIPE.md changes:
//   python scripts/generate-seed-helper-stub.py --phase {phase} --force
//
// Codegen wraps test.each(variant) with:
//   await runSeedRecipe(variant.id);
//   try {{ ... }} finally {{ await cleanup(variant.id); }}
//
// AI follow-up MUST replace `throw new Error(...)` stubs with concrete
// SQL/API/CLI per SEED-RECIPE.md seed_action + observed_state.
//
// DO NOT remove the `throw` to silence failures — loud failure is the
// point; silent drift in test seed state is what Batch 51-55 prevents.

import type {{ APIRequestContext, Page }} from '@playwright/test';

export interface SeedContext {{
  page?: Page;
  request?: APIRequestContext;
  variantId: string;
}}

export async function runSeedRecipe(variantId: string, ctx?: SeedContext): Promise<void> {{
  switch (variantId) {{
{seed_cases}
    default:
      throw new Error(`runSeedRecipe: unknown variant '${{variantId}}' — re-run generate-seed-helper-stub.py`);
  }}
}}

export async function cleanup(variantId: string, ctx?: SeedContext): Promise<void> {{
  switch (variantId) {{
{cleanup_cases}
    default:
      return;
  }}
}}
"""


def render_js(recipes: list[dict], phase: str) -> str:
    """Render JavaScript helper module (no types)."""
    if not recipes:
        return _render_empty_js(phase)
    seed_cases = "\n".join(_format_case(r, "seed_action", "js") for r in recipes)
    cleanup_cases = "\n".join(_format_case(r, "cleanup", "js") for r in recipes)
    return f"""// Auto-generated by Batch 55 (scripts/generate-seed-helper-stub.py).
// Phase: {phase}
// Re-run after SEED-RECIPE.md changes:
//   python scripts/generate-seed-helper-stub.py --phase {phase} --lang js --force

async function runSeedRecipe(variantId, ctx) {{
  switch (variantId) {{
{seed_cases}
    default:
      throw new Error(`runSeedRecipe: unknown variant '${{variantId}}' — re-run generate-seed-helper-stub.py`);
  }}
}}

async function cleanup(variantId, ctx) {{
  switch (variantId) {{
{cleanup_cases}
    default:
      return;
  }}
}}

module.exports = {{ runSeedRecipe, cleanup }};
"""


def _render_empty_ts(phase: str) -> str:
    return (f"// Auto-generated by Batch 55. Phase {phase} has no SEED-RECIPE variants.\n"
            f"export async function runSeedRecipe(variantId: string): Promise<void> {{\n"
            f"  throw new Error(`runSeedRecipe: no variants generated for phase {phase}`);\n"
            f"}}\n"
            f"export async function cleanup(_variantId: string): Promise<void> {{ return; }}\n")


def _render_empty_js(phase: str) -> str:
    return (f"// Auto-generated by Batch 55. Phase {phase} has no SEED-RECIPE variants.\n"
            f"async function runSeedRecipe(variantId) {{\n"
            f"  throw new Error(`runSeedRecipe: no variants generated for phase {phase}`);\n"
            f"}}\n"
            f"async function cleanup(_variantId) {{ return; }}\n"
            f"module.exports = {{ runSeedRecipe, cleanup }};\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--phase-dir")
    ap.add_argument("--lang", choices=["ts", "js"], default="ts")
    ap.add_argument("--out", help="override output path (default: PHASE_DIR/tests/_helpers/seed-recipes.{ts|js})")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    phase_dir = _find_phase_dir(args.phase, args.phase_dir)
    recipe_path = phase_dir / "SEED-RECIPE.md"
    if not recipe_path.is_file():
        print(f"⛔ Batch 55: SEED-RECIPE.md missing at {recipe_path}", file=sys.stderr)
        print(f"   Run: scripts/generate-seed-recipes.py --phase {args.phase}", file=sys.stderr)
        return 1

    text = recipe_path.read_text(encoding="utf-8")
    recipes = _parse_recipes(text)

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = phase_dir / "tests" / "_helpers" / f"seed-recipes.{args.lang}"

    if out_path.is_file() and not args.force:
        print(f"ℹ Batch 55: {out_path} exists (use --force to overwrite)")
        return 0

    body = render_ts(recipes, args.phase) if args.lang == "ts" else render_js(recipes, args.phase)
    if args.dry_run:
        print(body)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
    print(f"✓ Batch 55: wrote {len(recipes)} seed handler stubs to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
