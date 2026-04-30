#!/usr/bin/env python3
"""generate_recursive_prompts.py — manual-mode prompt fan-out (Task 20).

Reads a plan JSON (list of {element, lens} dicts produced by
``spawn_recursive_probe.build_plan``) and renders, under ``<phase_dir>/recursive-prompts/``:

  - ``MANIFEST.md``         : human-paste runbook listing every probe in order
  - ``<lens>-<selector>.md``: one prompt file per probe (Jinja-style templates)
  - ``EXPECTED-OUTPUTS.md`` : manifest of expected ``runs/<tool>/recursive-*.json``
                              paths used by ``verify_manual_run_artifacts.py``
                              (Task 21).

Templates live under ``commands/vg/_shared/templates/MANUAL-PROBE-*.tmpl`` and
use ``{{var}}`` substitution via ``string.Template``-style (we manually expand
``{{name}}`` because string.Template uses ``$name`` and would clash with shell
docs in the templates).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()

TEMPLATE_DIR_CANDIDATES: list[Path] = [
    REPO_ROOT / "commands" / "vg" / "_shared" / "templates",
    REPO_ROOT / ".claude" / "commands" / "vg" / "_shared" / "templates",
]

# Default minimum-required probe counts per mode (matches Task 19 caps but is
# advisory for manual runs — verify_manual_run_artifacts.py enforces).
MODE_MIN_REQUIRED: dict[str, int] = {"light": 5, "deep": 15, "exhaustive": 40}


# ---------------------------------------------------------------------------
# Template loading + rendering
# ---------------------------------------------------------------------------
def _find_template(name: str) -> Path:
    for d in TEMPLATE_DIR_CANDIDATES:
        candidate = d / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Template not found in {TEMPLATE_DIR_CANDIDATES}: {name}"
    )


_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _render(template: str, context: dict[str, Any]) -> str:
    """Replace every ``{{name}}`` with ``str(context[name])`` (or empty string)."""
    def sub(m: re.Match[str]) -> str:
        return str(context.get(m.group(1), ""))
    return _VAR_RE.sub(sub, template)


# ---------------------------------------------------------------------------
# Probe rendering
# ---------------------------------------------------------------------------
def _slugify(value: str) -> str:
    """Filename-safe slug: alphanum + dash, capped at 32 chars."""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "unknown").strip("-")
    return s[:32] or "unknown"


def _per_lens_filename(lens: str, selector: str) -> str:
    return f"{_slugify(lens)}-{_slugify(selector)}.md"


def _per_lens_output_path(lens: str, selector: str) -> str:
    """Stable expected output path under runs/manual/."""
    return f"runs/manual/recursive-{_slugify(lens)}-{_slugify(selector)}-d1.json"


def render_per_lens(template: str, *, probe_index: int,
                    entry: dict[str, Any]) -> tuple[str, str, str]:
    """Render one probe → (filename, body, expected_output_path)."""
    elem = entry.get("element", {}) or {}
    lens = str(entry.get("lens", "lens-unknown"))
    selector = str(elem.get("selector", "unknown"))

    output_path = _per_lens_output_path(lens, selector)
    context_block = {
        "lens": lens,
        "element_class": elem.get("element_class"),
        "selector": elem.get("selector"),
        "view": elem.get("view"),
        "resource": elem.get("resource"),
        "metadata": elem.get("metadata", {}),
        "output_path": output_path,
    }
    rendered = _render(template, {
        "probe_index": probe_index,
        "lens": lens,
        "element_class": elem.get("element_class", ""),
        "view": elem.get("view", ""),
        "selector": selector,
        "output_path": output_path,
        "context_json": json.dumps(context_block, indent=2),
        "element_summary": json.dumps({
            "element_class": elem.get("element_class"),
            "selector": elem.get("selector"),
            "view": elem.get("view"),
            "resource": elem.get("resource"),
        }),
    })
    fname = _per_lens_filename(lens, selector)
    return fname, rendered, output_path


def render_manifest(template: str, *, phase_name: str, phase_dir: Path,
                    probes: list[dict[str, Any]], mode: str) -> str:
    lines: list[str] = []
    for i, p in enumerate(probes, start=1):
        elem = p["element"] if isinstance(p.get("element"), dict) else {}
        lines.append(
            f"### Probe {i} of {len(probes)}: {p['lens']} on "
            f"{elem.get('element_class','?')} — {elem.get('view','?')}\n"
            f"Paste content of `{p['prompt_file']}` to start.\n"
            f"Output expected: `{p['output_path']}`"
        )
    probe_list = "\n\n".join(lines) if lines else "_(no probes planned)_"
    return _render(template, {
        "phase_name": phase_name,
        "phase_dir": str(phase_dir),
        "mode": mode,
        "probe_list": probe_list,
        "probe_count": len(probes),
        "min_required": MODE_MIN_REQUIRED.get(mode, 1),
    })


def render_expected_outputs(probes: list[dict[str, Any]]) -> str:
    """Plain Markdown list — read by verify_manual_run_artifacts.py (Task 21)."""
    body = ["# EXPECTED OUTPUTS — recursive manual run\n"]
    if not probes:
        body.append("_(no probes planned)_\n")
    for i, p in enumerate(probes, start=1):
        elem = p["element"] if isinstance(p.get("element"), dict) else {}
        body.append(
            f"- {i}. lens=`{p['lens']}` element_class=`{elem.get('element_class','?')}` "
            f"selector=`{elem.get('selector','?')}` → `{p['output_path']}`"
        )
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="generate_recursive_prompts.py",
        description="Render manual-mode probe prompts under <phase>/recursive-prompts/",
    )
    ap.add_argument("--phase-dir", required=True)
    ap.add_argument("--plan-json", required=True,
                    help="JSON-encoded list of {element, lens} dicts.")
    ap.add_argument("--mode", choices=["light", "deep", "exhaustive"],
                    default="light")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    phase_dir = Path(args.phase_dir).resolve()
    if not phase_dir.is_dir():
        sys.stderr.write(f"phase dir not found: {phase_dir}\n")
        return 2

    try:
        plan = json.loads(args.plan_json)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"--plan-json is not valid JSON: {exc}\n")
        return 2
    if not isinstance(plan, list):
        sys.stderr.write("--plan-json must decode to a JSON array.\n")
        return 2

    try:
        manifest_tmpl = _find_template("MANUAL-PROBE-MANIFEST.tmpl").read_text(encoding="utf-8")
        per_lens_tmpl = _find_template("MANUAL-PROBE-PER-LENS.tmpl").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    out_dir = phase_dir / "recursive-prompts"
    out_dir.mkdir(parents=True, exist_ok=True)

    probes_meta: list[dict[str, Any]] = []
    for i, entry in enumerate(plan, start=1):
        if not isinstance(entry, dict):
            continue
        fname, body, output_path = render_per_lens(
            per_lens_tmpl, probe_index=i, entry=entry,
        )
        (out_dir / fname).write_text(body, encoding="utf-8")
        probes_meta.append({
            "lens": str(entry.get("lens", "lens-unknown")),
            "element": entry.get("element", {}),
            "prompt_file": fname,
            "output_path": output_path,
        })

    manifest = render_manifest(
        manifest_tmpl,
        phase_name=phase_dir.name,
        phase_dir=phase_dir,
        probes=probes_meta,
        mode=args.mode,
    )
    (out_dir / "MANIFEST.md").write_text(manifest, encoding="utf-8")

    expected = render_expected_outputs(probes_meta)
    (out_dir / "EXPECTED-OUTPUTS.md").write_text(expected, encoding="utf-8")

    print(
        f"Wrote {len(probes_meta)} probe prompt(s) + MANIFEST.md + "
        f"EXPECTED-OUTPUTS.md → {out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
