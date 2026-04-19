---
name: "vg-bootstrap"
description: "Bootstrap overlay inspection — view merged config, diff vs vanilla, health report, test fixtures, export/import"
metadata:
  short-description: "Bootstrap overlay inspection — view merged config, diff vs vanilla, health report, test fixtures, export/import"
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

This skill is invoked by mentioning `$vg-bootstrap`. Treat all user text after `$vg-bootstrap` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


# /vg:bootstrap

Inspect and manage the project's bootstrap zone (`.vg/bootstrap/`).

**DOES NOT modify rules.** Use `/vg:learn` for modification.

## Load config

Read `.claude/commands/vg/_shared/config-loader.md` first.

## Subcommands

### `/vg:bootstrap --view`

Show the effective config (vanilla + overlay) currently applied.

```bash
PYTHONIOENCODING=utf-8 ${PYTHON_BIN} .claude/scripts/bootstrap-loader.py \
  --command bootstrap --emit overlay \
  | python -c "import json,sys; d=json.load(sys.stdin); print('\n--- Overlay ---'); import pprint; pprint.pprint(d.get('overlay',{})); print('\n--- Rejected ---'); [print(r) for r in d.get('overlay_rejected',[])]"
```

Also list active rules:
```bash
${PYTHON_BIN} .claude/scripts/bootstrap-loader.py --command bootstrap --emit rules
```

### `/vg:bootstrap --diff`

Show delta between vanilla vg.config.md and effective config.

Implementation:
1. Load vanilla `.claude/vg.config.md` (ignore overlay)
2. Load with overlay merged
3. Diff — show keys changed/added/removed

### `/vg:bootstrap --health`

Full report:
- Active rules count by status (active/dormant/retracted/experimental)
- Rules with `hits==0` and older than 5 phases → dormant candidates
- Rules with `fail_count > success_count` → regression candidates
- Conflicting rules (same target key, opposite values)
- Patches approaching limit (5 max)
- Recent candidates pending review count

```bash
${PYTHON_BIN} .claude/scripts/bootstrap-loader.py --emit trace --command bootstrap
```

### `/vg:bootstrap --trace <rule-id>`

Show firing history of one rule. Reads `${PLANNING_DIR}/telemetry.jsonl` for events with `event_type=bootstrap.rule_fired` and `rule_id=<id>`.

```bash
grep '"rule_id":"L-042"' "${PLANNING_DIR}/telemetry.jsonl" | python -m json.tool
```

### `/vg:bootstrap --test`

Run bootstrap fixture regression tests in `.vg/bootstrap/tests/*.yml`.

Each fixture YAML declares:
```yaml
name: "scenario-1-playwright"
given:
  phase_metadata:
    surfaces: [api]
  override:
    id: OD-X
    scope: "phase.surfaces does_not_contain 'web'"
when:
  phase_changes_to:
    surfaces: [web]
then:
  override_status: EXPIRED
  gate_active: true
```

### `/vg:bootstrap --export`

Package bootstrap zone into `bootstrap-{project}-{date}.tar.gz` for opt-in sharing to other projects.

```bash
tar -czf "bootstrap-${PROJECT_NAME}-$(date +%Y%m%d).tar.gz" .vg/bootstrap/
```

### `/vg:bootstrap --import <file>`

Import a bootstrap tar.gz into current project. **Destructive** — merges onto existing zone, prompts for conflicts.

## Output

Plain stdout. Not meant to be piped into other commands.
