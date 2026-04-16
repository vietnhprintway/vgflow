# Changelog

All notable changes to VG workflow documented here. Format follows [Keep a Changelog](https://keepachangelog.com/), adheres to [SemVer](https://semver.org/).

## [1.0.0] - 2026-04-17

### Added
- Initial public release of VGFlow
- 6-step pipeline: scope → blueprint → build → review → test → accept
- Config-driven engine via `vg.config.md` — zero hardcoded stack values
- `install.sh` for fresh project install
- `sync.sh` for dev-side source↔mirror sync
- Claude Code commands (`commands/vg/`) + shared helpers
- Codex CLI skills parity (`codex-skills/vg-review`, `vg-test`)
- Gemini CLI skills parity (`gemini-skills/`)
- Python scripts for graphify, caller graph, visual diff, phase recon
- Commit-msg hook template enforcing citation + SemVer task IDs
- Infrastructure: override debt register, i18n narration, telemetry, security register, visual regression, incremental graphify
