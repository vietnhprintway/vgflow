#!/usr/bin/env python3
"""v2.77.0 Stage 2.2 — generate `.gitignore` patterns for v3 `.vg/` layout.

Emits blanket-ignore + whitelist patterns to stdout. Used by:
  - Migration script `vg-migrate-v3.sh` to append to project `.gitignore`
  - First-run `/vg:install` to seed `.vg/` whitelist
  - Tests (idempotency, completeness)

Output is grouped by responsibility (header, blanket, tracked docs, phases,
bootstrap, deploy, re-ignores) for human readability when appended to an
existing `.gitignore`.

Source plan: docs/plans/2026-05-09-vg-global-install-implementation.md Stage 2.2
"""
from __future__ import annotations

import sys


HEADER = "# === VGFlow v3 layout (.vg/) — managed; do not edit manually ==="
FOOTER = "# === end VGFlow v3 layout ==="

BLANKET = [".vg/*"]

TRACKED_DOCS = [
    "!.vg/ROADMAP.md",
    "!.vg/FOUNDATION.md",
    "!.vg/config.md",
    "!.vg/OVERRIDE-DEBT.md",
    "!.vg/.install-target",
]

TRACKED_PHASES = [
    "!.vg/phases/",
    "!.vg/phases/**/*.md",
    "!.vg/phases/**/*.json",
]

TRACKED_BOOTSTRAP = [
    "!.vg/bootstrap/",
    "!.vg/bootstrap/ACCEPTED.md",
    "!.vg/bootstrap/REJECTED.md",
    "!.vg/bootstrap/RETRACTED.md",
    "!.vg/bootstrap/CONSOLIDATION-LOG.md",
    "!.vg/bootstrap/MEMORY.md",
    "!.vg/bootstrap/rules/",
    "!.vg/bootstrap/rules/*.md",
    "!.vg/bootstrap/overlay.yml",
    "!.vg/bootstrap/topics/",
    "!.vg/bootstrap/topics/*.md",
]

TRACKED_DEPLOY = [
    "!.vg/deploy/",
    "!.vg/deploy/STATE.json",
    "!.vg/deploy/history.jsonl",
]

RE_IGNORE_UNTRACKED = [
    "# Re-ignore subpaths that should never be tracked",
    ".vg/phases/**/.runtime-state.json",
    ".vg/bootstrap/CANDIDATES.md",
    ".vg/bootstrap/state.json",
    ".vg/bootstrap/.consolidation.lock",
    ".vg/deploy/deploy-log.*",
    ".vg/deploy/.deploy.lock",
]


def render() -> str:
    sections = [
        [HEADER],
        ["# Blanket ignore — every .vg/ entry off by default"],
        BLANKET,
        ["", "# Tracked: top-level docs"],
        TRACKED_DOCS,
        ["", "# Tracked: per-phase artifacts"],
        TRACKED_PHASES,
        ["", "# Tracked: bootstrap / meta-memory persisted state"],
        TRACKED_BOOTSTRAP,
        ["", "# Tracked: project-level deploy state"],
        TRACKED_DEPLOY,
        [""],
        RE_IGNORE_UNTRACKED,
        [FOOTER],
    ]
    lines: list[str] = []
    for sec in sections:
        lines.extend(sec)
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
