#!/usr/bin/env python3
"""
verify-ui-structure.py — so sánh cây component thực tế vs kế hoạch.

CÔNG CỤ: Gate (cổng chặn) sau khi executor xây xong phase UI. Nhận 2 cây JSON:
  - expected: cây kế hoạch do planner viết trong UI-MAP.md (file markdown,
    script extract code block JSON từ đó)
  - actual: cây thực tế do generate-ui-map.mjs quét từ code vừa viết

PHÂN LOẠI LỆCH (drift):
  - MISSING: component xuất hiện trong expected nhưng không có trong actual
             → executor quên thực hiện
  - UNEXPECTED: component xuất hiện trong actual nhưng không có trong expected
                → executor tự thêm ngoài kế hoạch
  - LAYOUT_SHIFT: cùng component nhưng class layout khác (flex vs grid...)
                  → có thể cố ý, có thể bug
  - STRUCTURE_SHIFT: thứ tự children thay đổi
                     → thường cosmetic, warn only

EXIT:
  0 — không lệch quá ngưỡng cho phép
  2 — BLOCK (vượt ngưỡng MISSING/UNEXPECTED)
  1 — lỗi script (không đọc được file...)

USAGE:
  python verify-ui-structure.py \
      --expected .vg/phases/11-settings/UI-MAP.md \
      --actual .vg/phases/11-settings/.ui-map-actual.json \
      --max-missing 0 --max-unexpected 3 --layout-advisory
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def extract_json_from_markdown(md_path: Path) -> dict | None:
    """Extract first ```json code block from markdown file."""
    if not md_path.exists():
        return None
    txt = md_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"```json\s*\n([\s\S]*?)\n```", txt)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"⛔ UI-MAP.md chứa JSON không hợp lệ: {e}", file=sys.stderr)
        return None


def load_tree(path: Path) -> dict | None:
    if not path.exists():
        return None
    if path.suffix == ".md":
        return extract_json_from_markdown(path)
    txt = path.read_text(encoding="utf-8", errors="ignore")
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def flatten(node: dict, parent: str = "(root)", out: list | None = None) -> list:
    """Flatten tree to list of {name, parent, layout, file} — order-preserving."""
    if out is None:
        out = []
    entry = {
        "name": node.get("name", "?"),
        "parent": parent,
        "layout": node.get("layout") or "",
        "file": node.get("file") or "",
        "kind": node.get("kind", "component"),
    }
    out.append(entry)
    children = node.get("children") or []
    for c in children:
        flatten(c, node.get("name", "?"), out)
    return out


def compare(expected: dict, actual: dict, layout_advisory: bool) -> dict:
    exp_flat = flatten(expected)
    act_flat = flatten(actual)

    # Build (name, parent) → layout map for each side
    exp_map = {(e["name"], e["parent"]): e["layout"] for e in exp_flat if e["kind"] == "component"}
    act_map = {(e["name"], e["parent"]): e["layout"] for e in act_flat if e["kind"] == "component"}

    missing = []
    unexpected = []
    layout_shift = []

    # MISSING: trong expected nhưng không trong actual
    for key, exp_layout in exp_map.items():
        if key not in act_map:
            missing.append({"name": key[0], "parent": key[1], "expected_layout": exp_layout})

    # UNEXPECTED: trong actual nhưng không trong expected
    for key, act_layout in act_map.items():
        if key not in exp_map:
            unexpected.append({"name": key[0], "parent": key[1], "actual_layout": act_layout})

    # LAYOUT_SHIFT: cùng (name, parent) nhưng layout khác
    for key, exp_layout in exp_map.items():
        if key in act_map and exp_layout != act_map[key]:
            # Chỉ flag nếu expected có layout (planner viết rõ) và khác
            if exp_layout.strip():
                layout_shift.append({
                    "name": key[0],
                    "parent": key[1],
                    "expected_layout": exp_layout,
                    "actual_layout": act_map[key],
                })

    return {
        "summary": {
            "expected_components": len(exp_map),
            "actual_components": len(act_map),
            "missing": len(missing),
            "unexpected": len(unexpected),
            "layout_shift": len(layout_shift),
        },
        "missing": missing,
        "unexpected": unexpected,
        "layout_shift": layout_shift,
    }


def print_report(diff: dict, thresholds: dict) -> None:
    s = diff["summary"]
    print("# UI Structure Drift Report\n")
    print(f"**Expected components:** {s['expected_components']}")
    print(f"**Actual components:** {s['actual_components']}")
    print(f"**MISSING (thiếu):** {s['missing']} (ngưỡng: {thresholds['max_missing']})")
    print(f"**UNEXPECTED (dư thừa):** {s['unexpected']} (ngưỡng: {thresholds['max_unexpected']})")
    print(f"**LAYOUT_SHIFT (lệch bố cục):** {s['layout_shift']} ({'advisory' if thresholds['layout_advisory'] else 'block'})\n")

    if diff["missing"]:
        print("## ⛔ MISSING — các component kế hoạch có nhưng code không có\n")
        for m in diff["missing"]:
            print(f"- `{m['name']}` dưới `{m['parent']}` (layout kế hoạch: {m['expected_layout'] or '—'})")
        print()

    if diff["unexpected"]:
        print("## ⚠ UNEXPECTED — code có thêm component ngoài kế hoạch\n")
        for u in diff["unexpected"]:
            print(f"- `{u['name']}` dưới `{u['parent']}` (layout thực tế: {u['actual_layout'] or '—'})")
        print()

    if diff["layout_shift"]:
        print("## ⚠ LAYOUT_SHIFT — bố cục khác kế hoạch\n")
        for l in diff["layout_shift"]:
            print(f"- `{l['name']}` dưới `{l['parent']}`")
            print(f"    kế hoạch: `{l['expected_layout']}`")
            print(f"    thực tế:  `{l['actual_layout']}`")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--expected", required=True, help="Path tới UI-MAP.md (kế hoạch) hoặc .json")
    ap.add_argument("--actual", required=True, help="Path tới cây thực tế (.json)")
    ap.add_argument("--max-missing", type=int, default=0, help="Số MISSING tối đa cho phép (default 0)")
    ap.add_argument("--max-unexpected", type=int, default=0, help="Số UNEXPECTED tối đa cho phép (default 0)")
    ap.add_argument("--layout-advisory", action="store_true", help="LAYOUT_SHIFT chỉ cảnh báo, không BLOCK")
    ap.add_argument("--json", action="store_true", help="In report dạng JSON")
    args = ap.parse_args()

    expected = load_tree(Path(args.expected))
    actual = load_tree(Path(args.actual))

    if expected is None:
        print(f"⛔ Không đọc được cây kế hoạch: {args.expected}", file=sys.stderr)
        print("   File phải là JSON trực tiếp hoặc markdown có ```json``` code block.", file=sys.stderr)
        return 1
    if actual is None:
        print(f"⛔ Không đọc được cây thực tế: {args.actual}", file=sys.stderr)
        print("   Sinh bằng: node .claude/scripts/generate-ui-map.mjs --format json --output <path>", file=sys.stderr)
        return 1

    diff = compare(expected, actual, args.layout_advisory)

    thresholds = {
        "max_missing": args.max_missing,
        "max_unexpected": args.max_unexpected,
        "layout_advisory": args.layout_advisory,
    }

    if args.json:
        print(json.dumps(diff, indent=2, ensure_ascii=False))
    else:
        print_report(diff, thresholds)

    # Exit policy
    s = diff["summary"]
    over_missing = s["missing"] > args.max_missing
    over_unexpected = s["unexpected"] > args.max_unexpected
    over_layout = s["layout_shift"] > 0 and not args.layout_advisory

    if over_missing or over_unexpected or over_layout:
        if not args.json:
            print("\n⛔ BLOCK: cấu trúc UI lệch so với kế hoạch.", file=sys.stderr)
            if over_missing:
                print(f"   MISSING {s['missing']} > ngưỡng {args.max_missing}", file=sys.stderr)
            if over_unexpected:
                print(f"   UNEXPECTED {s['unexpected']} > ngưỡng {args.max_unexpected}", file=sys.stderr)
            if over_layout:
                print(f"   LAYOUT_SHIFT {s['layout_shift']} > 0 (không advisory)", file=sys.stderr)
            print("   Fix: sửa code để khớp UI-MAP.md, HOẶC cập nhật UI-MAP.md nếu kế hoạch thay đổi.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
