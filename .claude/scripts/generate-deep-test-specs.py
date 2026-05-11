#!/usr/bin/env python3
"""Generate post-build deep test specification artifacts for a VG phase.

This command sits after /vg:build and before /vg:review. Blueprint can define
test goals, but only post-build has enough implemented routes, forms, API
handlers, generated UI, and build evidence to author lifecycle-grade tests.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".turbo",
    ".vite",
    ".cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}

SOURCE_EXTS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".php",
    ".rb",
    ".html",
    ".vue",
    ".svelte",
}

ROUTE_RE = re.compile(
    r"""(?x)
    (?:
      (?:app|router|route|server)\.(?:get|post|put|patch|delete)\s*\(\s*['"](?P<api1>/[^'"]+)['"]
      |
      @(?:app|router)\.(?:get|post|put|patch|delete)\s*\(\s*['"](?P<api2>/[^'"]+)['"]
      |
      path\s*[:=]\s*['"](?P<path>/[^'"]+)['"]
      |
      href\s*=\s*['"](?P<href>/[^'"]+)['"]
      |
      to\s*=\s*['"](?P<to>/[^'"]+)['"]
    )
    """
)

MUTATION_RE = re.compile(
    r"""(?ix)
    \b(fetch|axios|ky|client|api)\b.*?\b(POST|PUT|PATCH|DELETE)\b
    |
    \b(POST|PUT|PATCH|DELETE)\s+(/[\w./:{}?-]+)
    |
    \b(create|update|delete|remove|invite|accept|revoke|submit|save|archive|restore)\w*\b
    """
)

FORM_RE = re.compile(r"<form\b|useForm\(|Formik|react-hook-form|method=['\"]post['\"]", re.I)
TESTID_RE = re.compile(r"(data-testid|data-test-id|aria-label|role=)", re.I)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def find_phase_dir(phase: str, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise SystemExit(f"phase-dir not found: {path}")
        return path

    root = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd())
    phases_root = root / ".vg" / "phases"
    if not phases_root.is_dir():
        raise SystemExit(f"phase directory root not found: {phases_root}")

    candidates = [p for p in phases_root.iterdir() if p.is_dir()]
    exact = [p for p in candidates if p.name == phase]
    if exact:
        return exact[0]

    prefix = str(phase).zfill(2) if str(phase).isdigit() else str(phase)
    matches = [p for p in candidates if p.name == prefix or p.name.startswith(prefix + "-")]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"phase not found: {phase}")
    raise SystemExit(f"phase is ambiguous: {phase}: {', '.join(p.name for p in matches)}")


def repo_root_from_phase(phase_dir: Path) -> Path:
    env_root = os.environ.get("VG_REPO_ROOT")
    if env_root:
        return Path(env_root)
    try:
        return phase_dir.parents[2]
    except IndexError:
        return Path.cwd()


def load_lifecycle_generator() -> Any:
    here = Path(__file__).resolve().parent
    path = here / "generate-lifecycle-specs.py"
    if not path.exists():
        path = Path.cwd() / ".claude" / "scripts" / "generate-lifecycle-specs.py"
    if not path.exists():
        raise SystemExit("generate-lifecycle-specs.py not found")
    spec = importlib.util.spec_from_file_location("vg_generate_lifecycle_specs", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import lifecycle generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def has_build_evidence(phase_dir: Path) -> bool:
    return bool(
        list(phase_dir.glob("SUMMARY*.md"))
        or (phase_dir / "BUILD-LOG.md").exists()
        or (phase_dir / "BUILD-LOG").is_dir()
        or (phase_dir / ".build-progress.json").exists()
    )


def iter_source_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTS:
            continue
        files.append(path)
    return files


def scan_surfaces(root: Path, max_files: int = 1200) -> dict[str, Any]:
    routes: dict[str, dict[str, Any]] = {}
    mutations: list[dict[str, str]] = []
    forms: list[dict[str, str]] = []
    selector_files = 0

    for path in iter_source_files(root, max_files):
        text = read(path)
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        if TESTID_RE.search(text):
            selector_files += 1
        if FORM_RE.search(text):
            forms.append({"file": rel, "hint": "form or form-library usage detected"})
        if MUTATION_RE.search(text):
            mutations.append({"file": rel, "hint": "mutation verb or method detected"})
        for match in ROUTE_RE.finditer(text):
            route = next((g for g in match.groups() if g), "")
            if not route or route.startswith(("//", "http://", "https://")):
                continue
            item = routes.setdefault(route, {"route": route, "files": []})
            if rel not in item["files"]:
                item["files"].append(rel)

    return {
        "routes": sorted(routes.values(), key=lambda item: item["route"])[:300],
        "forms": forms[:300],
        "mutations": mutations[:300],
        "selector_files": selector_files,
        "files_scanned": len(iter_source_files(root, max_files)),
    }


def flatten_fixture_dag(lifecycle: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    for goal_id, spec in (lifecycle.get("goals") or {}).items():
        for actor in spec.get("actors") or []:
            node_id = f"{goal_id}:{actor.get('id')}"
            nodes[node_id] = {
                "id": node_id,
                "goal": goal_id,
                "kind": "actor",
                "role": actor.get("role"),
                "session": actor.get("session"),
                "cleanup": "revoke session/token when test owns it",
            }
        for fixture in spec.get("fixture_dag") or []:
            fixture_id = f"{goal_id}:{fixture.get('id')}"
            nodes[fixture_id] = {
                "id": fixture_id,
                "goal": goal_id,
                "kind": fixture.get("kind"),
                "cleanup": fixture.get("cleanup"),
            }
            for dep in fixture.get("depends_on") or []:
                edges.append({"from": f"{goal_id}:{dep}", "to": fixture_id})
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def render_deep_specs(phase_dir: Path, lifecycle: dict[str, Any], surfaces: dict[str, Any]) -> str:
    lines = [
        f"# Deep Test Specs — {phase_dir.name}",
        "",
        "_Generated after build and before review. Review must consume this as the test-depth contract._",
        "",
        "## Source Evidence",
        "",
        f"- Build evidence present: `{has_build_evidence(phase_dir)}`",
        f"- Source files scanned: `{surfaces['files_scanned']}`",
        f"- Routes detected: `{len(surfaces['routes'])}`",
        f"- Form surfaces detected: `{len(surfaces['forms'])}`",
        f"- Mutation candidates detected: `{len(surfaces['mutations'])}`",
        f"- Files exposing selectors/roles/labels: `{surfaces['selector_files']}`",
        "",
        "## Lifecycle Goals",
        "",
    ]
    goals = lifecycle.get("goals") or {}
    if not goals:
        lines.append("- No side-effecting or multi-actor goals detected. Read-only smoke specs still belong in `/vg:test`.")
    for goal_id, spec in goals.items():
        stages = [step.get("stage") for step in spec.get("steps") or []]
        lines.extend(
            [
                f"### {goal_id} — {spec.get('title', '')}",
                "",
                f"- Type: `{spec.get('goal_type', 'mutation')}`",
                f"- Actors: `{', '.join(str(a.get('id')) for a in spec.get('actors') or [])}`",
                f"- Fixture count: `{len(spec.get('fixture_dag') or [])}`",
                f"- RCRURDR stages: `{', '.join(stages)}`",
                f"- Artifact capture: `{len(spec.get('artifact_capture') or [])}` item(s)",
                f"- Cleanup: `{len(spec.get('cleanup') or [])}` item(s)",
                "",
            ]
        )
    lines.extend(["## Runtime Surface Hints", ""])
    for item in surfaces["routes"][:60]:
        lines.append(f"- `{item['route']}` — {', '.join(item['files'][:3])}")
    if len(surfaces["routes"]) > 60:
        lines.append(f"- ... +{len(surfaces['routes']) - 60} routes")
    lines.extend(["", "## Required Review Usage", ""])
    lines.extend(
        [
            "- `/vg:review` must compare browser discovery against these lifecycle goals.",
            "- Runtime blockers stay in review/debug; missing executable specs route to `/vg:test` only after runtime is clean.",
            "- Mutation goals require read-before, create, read-after-create, update, read-after-update, delete, read-after-delete evidence.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_playwright_plan(lifecycle: dict[str, Any], surfaces: dict[str, Any]) -> str:
    lines = [
        "# Playwright Spec Plan",
        "",
        "## Global Requirements",
        "",
        "- Capture console errors and failed network responses for every scenario.",
        "- Use stable selectors: data-testid, role, label, name, or route-bound locators.",
        "- Seed through fixture DAG order, cleanup in reverse order.",
        "- Assert UI, API response, and fresh re-read state after every mutation.",
        "",
        "## Spec Skeletons",
        "",
    ]
    for goal_id, spec in (lifecycle.get("goals") or {}).items():
        title = spec.get("title", "")
        lines.extend(
            [
                f"### `{goal_id}` — {title}",
                "",
                f"- File: `tests/e2e/{goal_id.lower().replace('.', '-')}.lifecycle.spec.ts`",
                f"- Actors: `{', '.join(str(a.get('id')) for a in spec.get('actors') or [])}`",
                f"- Fixtures: `{', '.join(str(f.get('id')) for f in spec.get('fixture_dag') or [])}`",
                "- Steps:",
            ]
        )
        for step in spec.get("steps") or []:
            lines.append(f"  - `{step.get('stage')}`: {step.get('action')}")
        lines.append("")
    lines.extend(["## Surface Hints", ""])
    for form in surfaces["forms"][:80]:
        lines.append(f"- Form candidate: `{form['file']}`")
    for mutation in surfaces["mutations"][:80]:
        lines.append(f"- Mutation candidate: `{mutation['file']}`")
    return "\n".join(lines).rstrip() + "\n"


def render_gaps(lifecycle: dict[str, Any], surfaces: dict[str, Any], phase_dir: Path) -> str:
    gaps: list[str] = []
    if not has_build_evidence(phase_dir):
        gaps.append("Build evidence missing; run `/vg:build` first.")
    if not (phase_dir / "TEST-GOALS.md").exists() and not (phase_dir / "TEST-GOALS").is_dir():
        gaps.append("TEST-GOALS missing; run `/vg:blueprint` first.")
    if not lifecycle.get("goals"):
        gaps.append("No lifecycle goals emitted; verify mutation/multi-actor goals are tagged in TEST-GOALS.")
    if surfaces["mutations"] and not lifecycle.get("goals"):
        gaps.append("Mutation code exists but TEST-GOALS did not produce lifecycle contracts.")
    if surfaces["forms"] and surfaces["selector_files"] == 0:
        gaps.append("Forms detected but no stable selector/role/label hints found in scanned files.")
    if not surfaces["routes"]:
        gaps.append("No routes detected by static scan; review must rely on runtime navigation or framework-specific scanner.")
    if not gaps:
        gaps.append("No deterministic deep-spec gaps detected.")
    return "# Test Spec Gaps\n\n" + "\n".join(f"- {gap}" for gap in gaps) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--phase-dir")
    parser.add_argument("--root")
    parser.add_argument("--max-files", type=int, default=1200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    phase_dir = find_phase_dir(args.phase, args.phase_dir)
    root = Path(args.root) if args.root else repo_root_from_phase(phase_dir)

    if not has_build_evidence(phase_dir):
        raise SystemExit(f"build evidence missing for {phase_dir}; run /vg:build first")

    lifecycle_module = load_lifecycle_generator()
    lifecycle = lifecycle_module.generate(phase_dir)
    surfaces = scan_surfaces(root, max_files=args.max_files)
    fixture_dag = flatten_fixture_dag(lifecycle)

    write_json(phase_dir / "LIFECYCLE-SPECS.json", lifecycle)
    write_json(phase_dir / "TEST-FIXTURE-DAG.json", fixture_dag)
    (phase_dir / "DEEP-TEST-SPECS.md").write_text(
        render_deep_specs(phase_dir, lifecycle, surfaces),
        encoding="utf-8",
    )
    (phase_dir / "PLAYWRIGHT-SPEC-PLAN.md").write_text(
        render_playwright_plan(lifecycle, surfaces),
        encoding="utf-8",
    )
    (phase_dir / "TEST-SPEC-GAPS.md").write_text(
        render_gaps(lifecycle, surfaces, phase_dir),
        encoding="utf-8",
    )

    summary = {
        "phase_dir": str(phase_dir),
        "root": str(root),
        "lifecycle_goals": len(lifecycle.get("goals") or {}),
        "fixture_nodes": len(fixture_dag["nodes"]),
        "fixture_edges": len(fixture_dag["edges"]),
        "routes": len(surfaces["routes"]),
        "forms": len(surfaces["forms"]),
        "mutations": len(surfaces["mutations"]),
        "artifacts": [
            "DEEP-TEST-SPECS.md",
            "LIFECYCLE-SPECS.json",
            "TEST-FIXTURE-DAG.json",
            "PLAYWRIGHT-SPEC-PLAN.md",
            "TEST-SPEC-GAPS.md",
        ],
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(
            "wrote deep test specs "
            f"({summary['lifecycle_goals']} lifecycle goals, "
            f"{summary['routes']} routes, {summary['forms']} forms)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
