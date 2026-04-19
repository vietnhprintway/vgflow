---
name: "vg-lesson"
description: "Manual lesson capture — rare backup when reflector missed something"
metadata:
  short-description: "Manual lesson capture — rare backup when reflector missed something"
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

This skill is invoked by mentioning `$vg-lesson`. Treat all user text after `$vg-lesson` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


# /vg:lesson

Capture a learning manually. **Rare backup** — primary flow is end-of-step reflection (`/vg:scope`, `/vg:review`, etc.) which auto-drafts candidates.

Use this when:
- Reflector missed a pattern you noticed
- You want to pre-emptively seed a rule before phase starts
- Recording a convention that doesn't come from any specific failure

## Load config

Read `.claude/commands/vg/_shared/config-loader.md` first.

## Input

`$ARGUMENTS` = free-form prose describing the lesson.

Examples:
- `/vg:lesson "build web phải dùng tsgo, tsc vanilla OOM"`
- `/vg:lesson "review step nếu có mutation phải reload verify data, không trust toast"`
- `/vg:lesson "khi touch apps/rtb-engine phải rebuild cargo không dùng pnpm"`

## Process

<step name="1_parse_intent">
Classify the lesson text into one of:
- `config_override` — user is naming a specific config key + value
- `rule` — user is describing behavior / pattern (most common)
- `unclear` — need to ask user for clarification

Heuristic: if text contains words like "dùng X thay Y", "use X instead of Y", "set X to Y", or references vg.config.md keys → likely `config_override`. Otherwise → `rule`.
</step>

<step name="2_draft_candidate">
Generate candidate YAML block:

```yaml
- id: L-{next_seq}
  source: user.lesson
  raw_text: "{user text}"
  type: {classified_type}
  title: "{short generated title, <80 chars}"
  scope:
    # AI infers from text:
    # - "build web" → step == "build" AND surfaces contains "web"
    # - "review với mutation" → step == "review" AND has_mutation == true
    any_of:
      - "{inferred predicate}"
  target_step: {build | review | scope | blueprint | global}
  action: {must_run | add_check | warn | suggest}
  proposed:
    # For config_override:
    key: "build_gates.typecheck_cmd"
    value: "pnpm tsgo --noEmit"
    # For rule:
    prose: |
      {generated prose from user text}
  confidence: 0.8  # user explicit, but AI inferring scope adds uncertainty
  evidence:
    - source: user_lesson
      timestamp: {iso_now}
      text: "{user text}"
  created_at: {iso_now}
```

Compute `dedupe_key = sha256(trigger + target)`:
```bash
echo -n "{trigger}|{target}" | sha256sum | cut -d' ' -f1
```

Check `REJECTED.md` for matching `dedupe_key` — if found ≥2 times → warn user "this was rejected before, still promote?".
</step>

<step name="3_append_candidates">
Append candidate block to `.vg/bootstrap/CANDIDATES.md` under `## Candidates`.

Emit telemetry:
```
emit_telemetry "bootstrap.candidate_drafted" PASS \
  "{\"id\":\"L-{seq}\",\"source\":\"user.lesson\",\"type\":\"{type}\"}"
```

Display to user:
```
📝 Lesson captured → CANDIDATES.md (L-{seq})

  Type: {type}
  Title: {title}
  Scope (AI inferred): {scope}
  Proposed: {target}

Next: /vg:learn --review L-{seq}
  Review evidence & dry-run before promote.
```
</step>

## Output

Single candidate written to `CANDIDATES.md`. User reviews + promotes via `/vg:learn`.
