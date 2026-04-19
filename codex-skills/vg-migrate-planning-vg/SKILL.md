---
name: "vg-migrate-planning-vg"
description: "Migrate .planning/ → .vg/ (VG canonical path). Idempotent — re-run scans + updates. Skips GSD-owned files."
metadata:
  short-description: "Migrate .planning/ → .vg/ (VG canonical path). Idempotent — re-run scans + updates. Skips GSD-owned files."
---

<codex_skill_adapter>
## Codex ⇆ Claude Code tool mapping

This skill was originally designed for Claude Code. When running in Codex CLI, translate tool calls using the table + patterns below.

### Tool mapping table

| Claude tool | Codex equivalent | Notes |
|---|---|---|
| AskUserQuestion | request_user_input (free-form text, or number-prefix choices) | For multi-select, format as "1. Option / 2. Option" and parse reply |
| Task (agent spawn) | `codex exec --model <model> "<prompt>"` subprocess | Foreground: `codex exec ... > /tmp/out.txt`. Parallel: launch N subprocesses + `wait`. See "Agent spawn" below |
| TaskCreate/TaskUpdate/TodoWrite | N/A — use inline markdown headers + status narration | Codex does not have a persistent task tail UI. Write `## ━━━ Phase X: step ━━━` in stdout instead |
| Monitor | Bash loop with `echo` + `sleep 3` polling | Codex streams stdout directly, no separate monitor channel |
| ScheduleWakeup | N/A — Codex is one-shot; user must re-invoke | Skill must tolerate single-execution model; no sleeping |
| WebFetch | `curl -sfL <url>` or `gh api <path>` | For GitHub URLs prefer `gh` for auth handling |
| mcp__playwright{1-5}__* | See "Playwright MCP" below | Playwright MCP tools ARE available in Codex's main orchestrator |
| mcp__graphify__* | `python -c "from graphify import ..."` inline | Graphify CLI/module works identically in Codex |
| mcp__context7__*, mcp__exa__*, mcp__firecrawl__* | Skip or fall back to WebFetch | Only available via SDK; not bundled in Codex CLI |
| Bash/Read/Write/Edit/Glob/Grep | Same — Codex supports these natively | No adapter needed |

### Agent spawn (Task → codex exec)

Claude Code spawns isolated agents via `Task(subagent_type=..., prompt=...)`. Codex equivalent:

```bash
# Single agent, foreground (wait for completion + read output)
codex exec --model gpt-5 "<full isolated prompt>" > /tmp/agent-result.txt 2>&1
RESULT=$(cat /tmp/agent-result.txt)

# Multiple agents, parallel (Claude's pattern of 1 message with N Task calls)
codex exec --model gpt-5 "<prompt 1>" > /tmp/agent-1.txt 2>&1 &
PID1=$!
codex exec --model gpt-5 "<prompt 2>" > /tmp/agent-2.txt 2>&1 &
PID2=$!
wait $PID1 $PID2
R1=$(cat /tmp/agent-1.txt); R2=$(cat /tmp/agent-2.txt)
```

**Critical constraints when spawning:**
- Subagent inherits working directory + env vars, but **no MCP server access** (Codex exec spawns fresh CLI instance without `--mcp` wired). Subagent CANNOT call `mcp__playwright*__`, `mcp__graphify__`, etc.
- Model mapping for this project: `models.planner` opus → `gpt-5`, `models.executor` sonnet → `gpt-4o`, `models.scanner` haiku → `gpt-4o-mini` (or project-configured equivalent). Check `.claude/vg.config.md` `models` section for actual values and adapt.
- Timeout: wrap in `timeout 600s codex exec ...` to prevent hung subagents.
- Return schema: if skill expects structured JSON back, prompt subagent with "Return ONLY a single JSON object with keys: {...}". Parse with `jq` or `python -c "import json,sys; ..."`.

### Playwright MCP — orchestrator-only rule

Playwright MCP tools (`mcp__playwright1__browser_navigate`, `_snapshot`, `_click`, etc.) ARE available to the main Codex orchestrator (same MCP servers as Claude Code). **BUT subagents spawned via `codex exec` do NOT inherit MCP access** — they are fresh CLI instances.

Implication for skills using Haiku scanner pattern (scanner spawns → uses Playwright):
- **Claude model:** spawn haiku agent with prompt → agent calls `mcp__playwright__` tools directly
- **Codex model:** TWO options:
  1. **Orchestrator-driven:** main orchestrator calls Playwright tools + passes snapshots/results to subagent as text → subagent returns instructions/analysis only (no tool calls). Slower but preserves parallelism benefit.
  2. **Single-agent:** orchestrator runs scanner workflow inline (no spawn). Simpler but no parallelism; suitable for 1-2 view scans but slow for 14+ views.

Default: **single-agent inline** unless skill explicitly documents the orchestrator-driven pattern for that step.

### Persistence probe (Layer 4) — execution model

For review/test skills that verify mutation persistence:
- Main orchestrator holds Playwright session (claimed via lock manager)
- Pre-snapshot + submit + refresh + re-read all run in orchestrator Playwright calls (not spawned)
- If skill delegates analysis to subagent, orchestrator must capture snapshots + pass text to subagent; subagent returns verdict JSON `{persisted: bool, pre: ..., post: ...}`

### Lock manager (Playwright)

Same as Claude:
```bash
SESSION_ID="codex-${skill}-${phase}-$$"
PLAYWRIGHT_SERVER=$(bash "${HOME}/.claude/playwright-locks/playwright-lock.sh" claim "$SESSION_ID")
trap "bash '${HOME}/.claude/playwright-locks/playwright-lock.sh' release \"$SESSION_ID\" 2>/dev/null" EXIT INT TERM
```

Pool name in Codex: `codex` (separate from Claude's `claude` pool). Lock manager handles both without collision.

## Invocation

This skill is invoked by mentioning `$vg-migrate-planning-vg`. Treat all user text after `$vg-migrate-planning-vg` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<rules>
1. **Idempotent** — safe to re-run. Compares hashes, only updates changed files.
2. **Comprehensive** — walks ALL files in .planning/. Doesn't silently skip unknowns.
3. **GSD-aware** — auto-classifies and SKIPS GSD-owned files (debug/, quick/, research/, codebase/, *.gsd, gsd-* paths).
4. **User-edit safe** — if target file in .vg/ has been user-edited since last migration, creates `.user-edit.<ts>` backup before overwriting.
5. **Default keep-original** — `.planning/` preserved by default. Use `--no-keep` to delete after successful migration.
6. **Dry-run first** — always preview before applying when in doubt.
</rules>

<objective>
Migrate VG-owned artifacts từ legacy `.planning/` → canonical `.vg/`. GSD continues using `.planning/`. After migration, all VG commands read/write `.vg/` (per `paths.planning_dir` config).

Modes:
- `--dry-run` — preview classification + actions, no files written
- `--no-keep` — delete `.planning/` after successful migration (default: keep)
- `--source=<path>` — override source (default `.planning`)
- `--target=<path>` — override target (default `.vg`)
- `--auto-promote` (v1.14.2+) — promote `.vg/_legacy/_extractions/*.extracted.md` → `.vg/` proper slot using deterministic name-based rules. Never overwrites existing `.vg/` content. Adds banner for review.
- `--full-auto` (v1.14.2+) — run migrate + auto-promote + verify-convergence in one pass. Short-circuit end-to-end.
- `--archive-planning` (v1.14.2+) — after successful migrate+promote+verify, tar.gz `.planning/` → `.vg/_archives/planning-{ts}.tar.gz` then remove `.planning/`. Safer than `--no-keep` (preserves evidence). Compose with `--full-auto`.

Idempotent — running multiple times is SAFE and EXPECTED:
- New files in source → copied to target
- Changed files in source → updated in target (with backup if user edited)
- Already-synced files → no-op
- GSD files → skipped consistently

Convergence guarantee (`--full-auto` only):
- After migrate + promote, dry-run re-check MUST produce 0 NEW + 0 UPDATED
- If not converged, command exits non-zero (signals drift somewhere)
</objective>

<process>

**Source:**
```bash
source "${REPO_ROOT}/.claude/commands/vg/_shared/lib/planning-migrator.sh"
```

<step name="0_parse">
Parse flags from `$ARGUMENTS`:
```bash
ARGS=""
FULL_AUTO=false
AUTO_PROMOTE=false
for arg in $ARGUMENTS; do
  case "$arg" in
    --dry-run|--no-keep|--source=*|--target=*) ARGS="$ARGS $arg" ;;
    --full-auto) FULL_AUTO=true ;;
    --auto-promote) AUTO_PROMOTE=true ;;
  esac
done
```
</step>

<step name="1_run">
Three modes:

**(A) Full-auto (v1.14.2+ NEW):** migrate → promote → verify in one pass.
```bash
if [ "$FULL_AUTO" = "true" ]; then
  planning_migrator_full_auto $ARGS
  # Exit here — full_auto handles everything including commit suggestion
  exit $?
fi
```

**(B) Migrate + promote (without full verify):**
```bash
if [ "$AUTO_PROMOTE" = "true" ]; then
  planning_migrator_run $ARGS
  # Run promote AFTER migrate completes
  DRY_RUN_FLAG=false
  [[ "$ARGS" =~ --dry-run ]] && DRY_RUN_FLAG=true
  planning_migrator_promote_extractions $DRY_RUN_FLAG
fi
```

**(C) Classic (migrate only):**
```bash
if [ "$FULL_AUTO" != "true" ] && [ "$AUTO_PROMOTE" != "true" ]; then
  planning_migrator_run $ARGS
fi
```

Output shows per-file classification + final summary table.
</step>

<step name="2_post_migration_config">
After successful migration, update vg.config.md to point at `.vg`:

```bash
if [ ! -f ".claude/vg.config.md" ]; then
  echo "⚠ No vg.config.md — skipping config update"
  exit 0
fi

if grep -qE "^\s*planning_dir:\s*\".vg\"" .claude/vg.config.md; then
  echo "✓ Config already points at .vg"
else
  ${PYTHON_BIN:-python3} -c "
import re
p = '.claude/vg.config.md'
txt = open(p, encoding='utf-8').read()
# Update or insert paths.planning_dir
if re.search(r'^paths:\s*\n', txt, re.M):
    if re.search(r'planning_dir:', txt):
        txt = re.sub(r'(planning_dir:)\s*\"[^\"]*\"', r'\1 \".vg\"', txt)
    else:
        txt = re.sub(r'(^paths:\s*\n)', r'\\1  planning_dir: \".vg\"\\n', txt, flags=re.M)
else:
    txt += '\\n# v1.12.0 — paths.planning_dir set via /vg:migrate-planning-vg\\npaths:\\n  planning_dir: \".vg\"\\n'
open(p, 'w', encoding='utf-8').write(txt)
print('✓ vg.config.md updated: paths.planning_dir = .vg')
"
fi
```
</step>

<step name="3_summary">
Display next-steps:
```
Migration complete. .vg/ is now canonical for VG workflow.

Next:
- All VG commands now read .vg/ (auto-detected via config)
- .planning/ preserved (used by GSD if installed)
- Re-run /vg:migrate-planning-vg anytime to sync new .planning/ → .vg/
- After confirming .vg/ is correct, optionally delete .planning/:
    /vg:migrate-planning-vg --no-keep
```
</step>

</process>

<success_criteria>
- All non-GSD files in .planning/ present in .vg/
- GSD files (*.gsd, debug/, quick/, research/, codebase/) skipped
- Hash equality between corresponding source/target files
- Re-run produces 0 NEW + 0 UPDATED (idempotent)
- vg.config.md `paths.planning_dir: ".vg"` set
- User edits in .vg/ preserved via .user-edit.<ts> backup
</success_criteria>
