# VGFlow

> **Languages:** [English](README.md) · [Tiếng Việt](README.vi.md)

Config-driven AI development pipeline for Claude Code, Codex CLI, and Gemini CLI. Zero hardcoded stack values — everything flows from `vg.config.md`.

**Version:** 1.1.0 · **License:** MIT

---

## The Pipeline (Two Tiers)

### Project-level setup (once per project / milestone)

```
/vg:project       →  /vg:roadmap   →  /vg:map          →  /vg:prioritize
(7-round            (ROADMAP.md,     (optional —          (which phase
discussion →        phase list,      graphify              to work next)
PROJECT.md +        soft drift       codebase)
FOUNDATION.md +     warning)
vg.config.md
ATOMIC)
```

**v1.6.0 entry point change**: `/vg:project` is the single entry point. It captures your free-form description, derives FOUNDATION (8 dimensions: platform/runtime/data/auth/hosting/distribution/scale/compliance), then auto-generates `vg.config.md`. Config is downstream of foundation, not upstream.

`/vg:init` is preserved as a backward-compat soft alias → `/vg:project --init-only`.

### Per-phase execution (7 steps)

```
/vg:specs  →  /vg:scope  →  /vg:blueprint  →  /vg:build  →  /vg:review  →  /vg:test  →  /vg:accept
(goal,        (discussion    (PLAN.md +        (wave-based     (scan + fix    (goal verify    (human UAT
scope,        → CONTEXT.md   API-CONTRACTS +    parallel        loop →         + codegen       → UAT.md)
constraints)   with D-XX)    TEST-GOALS)        execute)        RUNTIME-MAP)   regression)
```

Full pipeline shortcut: `/vg:phase {X}` runs all 7 per-phase steps with resume support.
Advance step-by-step: `/vg:next` auto-detects current position and invokes the next command.

---

## Install (fresh project)

```bash
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/vietdev99/vgflow/main/install.sh -o /tmp/vgflow-install.sh
bash /tmp/vgflow-install.sh .
```

Or manual:
```bash
git clone https://github.com/vietdev99/vgflow.git /tmp/vgflow
bash /tmp/vgflow/install.sh /path/to/your-project
```

The installer copies commands, skills, scripts, templates, and generates `.claude/vg.config.md` from the template. Codex + Gemini CLI skills are deployed to `.codex/skills/` and `~/.codex/skills/` (global) when detected.

## Update existing install

```
/vg:update --check                   # peek at latest version without applying
/vg:update                           # apply latest release
/vg:update --accept-breaking         # required for major version bumps
/vg:reapply-patches                  # resolve conflicts from /vg:update
```

Update flow: query GitHub API → download tarball + SHA256 verify → 3-way merge (preserves your local edits) → park conflicts in `.claude/vgflow-patches/`.

## Command reference

### Project setup
| Command | Purpose |
|---------|---------|
| `/vg:project` | **ENTRY POINT** — 7-round discussion → PROJECT.md + FOUNDATION.md + vg.config.md (atomic) |
| `/vg:project --view` | Pretty-print current artifacts (read-only) |
| `/vg:project --update` | MERGE-preserving update of existing artifacts |
| `/vg:project --milestone` | Append new milestone (foundation untouched) |
| `/vg:project --rewrite` | Destructive reset with backup → `.archive/{ts}/` |
| `/vg:project --migrate` | Extract FOUNDATION.md from legacy v1 PROJECT.md + codebase scan |
| `/vg:project --init-only` | Re-derive vg.config.md from existing FOUNDATION.md |
| `/vg:init` | [DEPRECATED] Soft alias → `/vg:project --init-only` |
| `/vg:roadmap` | Derive phases from PROJECT + FOUNDATION → ROADMAP.md (soft drift warning) |
| `/vg:map` | Rebuild graphify knowledge graph → `codebase-map.md` |
| `/vg:prioritize` | Rank phases by impact + readiness |

### Phase execution (7-step pipeline)
| Step | Command | Output |
|------|---------|--------|
| 1 | `/vg:specs {X}` | SPECS.md (goal, scope, constraints, success criteria) |
| 2 | `/vg:scope {X}` | CONTEXT.md (enriched with decisions D-XX) + DISCUSSION-LOG.md |
| 3 | `/vg:blueprint {X}` | PLAN.md + API-CONTRACTS.md + TEST-GOALS.md + CrossAI review |
| 4 | `/vg:build {X}` | Code + SUMMARY.md (wave-based parallel execution) |
| 5 | `/vg:review {X}` | RUNTIME-MAP.json (browser discovery + fix loop) |
| 6 | `/vg:test {X}` | SANDBOX-TEST.md (goal verification + codegen regression) |
| 7 | `/vg:accept {X}` | UAT.md (human acceptance) |

### Management
| Command | Purpose |
|---------|---------|
| `/vg:phase {X}` | Run full 7-step phase pipeline with resume support |
| `/vg:next` | Auto-detect + advance to next step |
| `/vg:progress` | Status across all phases + update check |
| `/vg:amend {X}` | Mid-phase change — update CONTEXT.md, cascade impact |
| `/vg:add-phase` | Insert a new phase into ROADMAP.md |
| `/vg:remove-phase` | Archive + delete a phase |
| `/vg:regression` | Re-run all tests from accepted phases |
| `/vg:migrate {X}` | Convert legacy GSD artifacts to VG format (also backfills infra registers) |

### Distribution + infra
| Command | Purpose |
|---------|---------|
| `/vg:update` | Pull latest release from GitHub |
| `/vg:reapply-patches` | Resolve conflicts from `/vg:update` |
| `/vg:sync` | Dev-side source↔mirror sync (maintainer only) |
| `/vg:telemetry` | Summarize workflow telemetry |
| `/vg:security-audit-milestone` | Cross-phase security correlation |

## Repository layout

```
vgflow/
├── VERSION                   ← SemVer (e.g. "1.1.0")
├── CHANGELOG.md              ← curated per release
├── commands/vg/              ← Claude Code slash commands
├── skills/                   ← api-contract, vg-* skills
├── codex-skills/             ← Codex CLI parity
├── gemini-skills/            ← Gemini CLI parity
├── scripts/                  ← Python helpers (vg_update, graphify, visual-diff, …)
├── templates/vg/             ← commit-msg hook template
├── vg.config.template.md     ← schema seed for new projects
├── migrations/               ← vN_to_vN+1.md breaking-change guides
├── install.sh                ← fresh install entrypoint
└── sync.sh                   ← dev-side source↔mirror (maintainer)
```

## Release channel

- **Tags:** SemVer — `v1.2.3`
- **Tarballs:** attached to each GitHub Release (auto-built via `.github/workflows/release.yml`)
- **Changelog:** `CHANGELOG.md` + rendered in each Release body
- **Breaking changes:** `migrations/vN_to_vN+1.md` shown before update proceeds

## Contributing

Maintained by [@vietdev99](https://github.com/vietdev99). Not accepting external PRs at this stage — bug reports welcome as issues.

## License

MIT — see [LICENSE](LICENSE)
