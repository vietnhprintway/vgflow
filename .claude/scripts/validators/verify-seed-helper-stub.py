#!/usr/bin/env python3
"""Batch 55: verify seed helper stub exists + covers every variant_id.

Codegen subagent (Batch 52) wraps test.each with runSeedRecipe(variant.id).
If the helper file is missing OR a variant_id has no case branch, the
test fails at runtime with `Cannot read properties of undefined` or
`runSeedRecipe: unknown variant` — either way, drift.

This gate enforces:
  1. seed-recipes.{ts|js} exists at PHASE_DIR/tests/_helpers/ (or --out)
  2. Every variant_id from LIFECYCLE-SPECS appears as `case 'ID':` in file
  3. File has both `runSeedRecipe` AND `cleanup` exports

Usage:
  verify-seed-helper-stub.py --phase 7
  verify-seed-helper-stub.py --phase 7 --strict
  verify-seed-helper-stub.py --phase 7 --lang ts
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


def _enumerate_variants(lifecycle: dict) -> list[str]:
    out: list[str] = []
    for gid, gspec in (lifecycle.get("goals") or {}).items():
        if not isinstance(gspec, dict):
            continue
        for idx, ec in enumerate(gspec.get("edge_cases") or [], 1):
            if isinstance(ec, dict):
                kind = ec.get("kind") or "unknown"
                letter = (kind[:1].lower() or "x")
                out.append(f"{gid}-{letter}{idx}")
        for idx, neg in enumerate(gspec.get("negative_specs") or [], 1):
            if isinstance(neg, dict):
                out.append(f"{gid}-n{idx}")
    return out


CASE_RE = re.compile(r"case\s+['\"]([\w.-]+)['\"]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--phase-dir")
    ap.add_argument("--lang", choices=["ts", "js"], default="ts")
    ap.add_argument("--out", help="override expected helper path")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    phase_dir = _find_phase_dir(args.phase, args.phase_dir)
    lifecycle_path = phase_dir / "LIFECYCLE-SPECS.json"
    if not lifecycle_path.is_file():
        print(f"⛔ Batch 55: LIFECYCLE-SPECS.json missing at {lifecycle_path}", file=sys.stderr)
        return 1
    try:
        lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⛔ Batch 55: malformed LIFECYCLE-SPECS.json: {e}", file=sys.stderr)
        return 1

    variants = _enumerate_variants(lifecycle)
    if not variants:
        print(f"ℹ Batch 55: no variants in LIFECYCLE-SPECS — no helper required")
        return 0

    out_path = Path(args.out) if args.out else (
        phase_dir / "tests" / "_helpers" / f"seed-recipes.{args.lang}"
    )
    if not out_path.is_file():
        print(f"⛔ Batch 55: seed helper missing at {out_path}", file=sys.stderr)
        print(f"   Run: scripts/generate-seed-helper-stub.py --phase {args.phase}", file=sys.stderr)
        return 1

    text = out_path.read_text(encoding="utf-8")
    if "runSeedRecipe" not in text:
        print(f"⛔ Batch 55: helper {out_path.name} lacks runSeedRecipe export", file=sys.stderr)
        return 1
    if "cleanup" not in text:
        print(f"⛔ Batch 55: helper {out_path.name} lacks cleanup export", file=sys.stderr)
        return 1

    cases = set(CASE_RE.findall(text))
    missing = [v for v in variants if v not in cases]

    print(f"Batch 55: {len(variants)} variants, {len(cases)} cases in helper, "
          f"{len(missing)} missing")
    if missing:
        for v in missing:
            print(f"  missing handler case: {v}", file=sys.stderr)
        if args.strict:
            return 1
        print(f"⚠ Batch 55: {len(missing)} variants without handler case (warn; --strict to BLOCK)",
              file=sys.stderr)
    else:
        print(f"✓ Batch 55: all {len(variants)} variants have handler cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
