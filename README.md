# VGFlow

Config-driven AI development pipeline. 6 steps — `scope → blueprint → build → review → test → accept`. Works với Claude Code, Codex CLI, Gemini CLI. Zero hardcoded stack values — mọi thứ đến từ `vg.config.md`.

**Version:** 1.0.0 · **Language:** Vietnamese (chat) + English (code/docs) · **License:** MIT

---

## Install (fresh project)

**Quick (curl | bash):**
```bash
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/vietdev99/vgflow/main/install.sh -o /tmp/vgflow-install.sh
bash /tmp/vgflow-install.sh .
```

**Manual clone:**
```bash
git clone https://github.com/vietdev99/vgflow.git /tmp/vgflow
bash /tmp/vgflow/install.sh /path/to/your-project
```

Install script will:
- Copy `commands/vg/` → `.claude/commands/vg/`
- Copy `skills/api-contract/` + `skills/vg-*/` → `.claude/skills/`
- Copy scripts + templates
- Deploy Codex skills → `.codex/skills/vg-*/` (optional) + `~/.codex/skills/` (global)
- Generate `.claude/vg.config.md` from template (với defaults)

## Update existing install

Check for updates:
```
/vg:update --check
```

Apply latest release:
```
/vg:update
```

Update does:
1. Query `api.github.com/repos/vietdev99/vgflow/releases/latest`
2. Compare with `.claude/VGFLOW-VERSION`
3. Download tarball + verify SHA256
4. 3-way merge per file (ancestor = installed version, current = user edits, upstream = latest)
5. Clean merges apply silently
6. Conflicts parked in `.claude/vgflow-patches/` with `.patches-manifest.json`

Resolve conflicts:
```
/vg:reapply-patches
```

Breaking changes (major version bump) require explicit opt-in:
```
/vg:update --accept-breaking
```

## Commands

| Command | Purpose |
|---------|---------|
| `/vg:init` | Generate `vg.config.md` for new project |
| `/vg:project` | Define PROJECT.md + REQUIREMENTS.md |
| `/vg:roadmap` | Derive phases → ROADMAP.md |
| `/vg:specs {X}` | SPECS.md cho phase |
| `/vg:scope {X}` | 5-round discussion → enriched CONTEXT.md |
| `/vg:blueprint {X}` | PLAN.md + API-CONTRACTS.md + TEST-GOALS.md + CrossAI |
| `/vg:build {X}` | Wave-based parallel execution → SUMMARY.md |
| `/vg:review {X}` | Code scan + browser discovery → RUNTIME-MAP.json |
| `/vg:test {X}` | Goal verification + codegen → SANDBOX-TEST.md |
| `/vg:accept {X}` | Human UAT → UAT.md |
| `/vg:phase {X}` | Run full pipeline specs→accept |
| `/vg:next` | Auto-advance to next step |
| `/vg:progress` | Status all phases + update check |
| `/vg:update` | Pull latest release from GitHub |
| `/vg:reapply-patches` | Resolve conflicts from `/vg:update` |
| `/vg:sync` | Dev-side source↔mirror sync |
| `/vg:telemetry` | Summarize workflow telemetry |
| `/vg:security-audit-milestone` | Cross-phase security audit |

Full list: `ls commands/vg/`

## Repository layout

```
vgflow/
├── VERSION                   ← SemVer, cut per release
├── CHANGELOG.md              ← curated per release
├── commands/vg/              ← Claude Code slash commands
├── skills/                   ← api-contract, vg-* skills
├── codex-skills/             ← Codex CLI parity (vg-review, vg-test)
├── gemini-skills/            ← Gemini CLI parity
├── scripts/                  ← Python helpers (graphify, visual-diff, vg_update)
├── templates/vg/             ← commit-msg hook template
├── vg.config.template.md     ← schema seed for new projects
├── migrations/               ← vN_to_vN+1.md (breaking-change guides)
├── install.sh                ← fresh install entrypoint
└── sync.sh                   ← dev-side source↔mirror
```

## Release channel

- **Tags:** SemVer — `v1.2.3`
- **Tarballs:** GitHub Releases page, attached to each tag (auto-built via `.github/workflows/release.yml`)
- **Changelog:** `CHANGELOG.md` in repo, also in Release body
- **Breaking changes:** `migrations/vN_to_vN+1.md` — required reading when major version bumps

## Contributing

Public repo maintained by [@vietdev99](https://github.com/vietdev99). Not accepting external PRs for now — feel free to open issues for bug reports or questions.

## License

MIT — see [LICENSE](LICENSE)
