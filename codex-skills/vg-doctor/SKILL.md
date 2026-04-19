---
name: "vg-doctor"
description: "Thin dispatcher for VG state inspection — routes to /vg:health, /vg:integrity, /vg:gate-stats, /vg:recover. Use sub-commands directly for clarity."
metadata:
  short-description: "Thin dispatcher for VG state inspection — routes to /vg:health, /vg:integrity, /vg:gate-stats, /vg:recover. Use sub-commands directly for clarity."
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

This skill is invoked by mentioning `$vg-doctor`. Treat all user text after `$vg-doctor` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<NARRATION_POLICY>
**⛔ DO NOT USE TodoWrite / TaskCreate / TaskUpdate.**

Markdown headers for progress. This command is a thin router — actual work happens in sub-commands.

**Translate English terms (RULE)** — `dispatcher (điều phối)`, `sub-command (lệnh con)`, `legacy flag (cờ cũ)`. Không áp dụng: file path, code ID.
</NARRATION_POLICY>

<rules>
1. **Pure routing** — never does health/integrity/gate/recover work directly. Invokes sub-command via Skill tool.
2. **Positional verb** — first arg parsed as verb: `health | integrity | gate-stats | recover`. Unknown verb → print help.
3. **Legacy flag compat** — `--integrity`, `--gates`, `--recover` emit a DEPRECATED warn and route to new sub-command.
4. **No arg or `help`** — print the 4-sub-command menu and exit 0.
5. **Zero heavy work** — this file stays ≤80 LOC.
</rules>

<process>

<step name="0_parse_verb">
## Step 0: Parse verb + route

```bash
# Extract first positional token + capture remaining args for forwarding.
VERB=""
FWD_ARGS=""
for arg in $ARGUMENTS; do
  case "$arg" in
    health|integrity|gate-stats|recover|help)
      [ -z "$VERB" ] && VERB="$arg" || FWD_ARGS="${FWD_ARGS} ${arg}"
      ;;
    --integrity)
      echo "⚠ DEPRECATED: --integrity flag. Use /vg:integrity instead." >&2
      VERB="integrity"
      ;;
    --gates)
      echo "⚠ DEPRECATED: --gates flag. Use /vg:gate-stats instead." >&2
      VERB="gate-stats"
      ;;
    --recover)
      echo "⚠ DEPRECATED: --recover flag. Use /vg:recover {phase} instead." >&2
      VERB="recover"
      ;;
    *)
      FWD_ARGS="${FWD_ARGS} ${arg}"
      ;;
  esac
done

# Default to help when no verb resolved
if [ -z "$VERB" ]; then
  [ -n "$FWD_ARGS" ] && VERB="health"  # bare phase arg → health deep mode (back-compat)
fi
```
</step>

<step name="1_dispatch">
## Step 1: Dispatch (or print help)

The shell block above resolves `VERB` and `FWD_ARGS`. The outer model reads the resolved values and routes via the **Skill tool**:

| Resolved VERB | Skill invocation |
|---------------|------------------|
| `health`      | `Skill(skill="vg:health", args=FWD_ARGS)` |
| `integrity`   | `Skill(skill="vg:integrity", args=FWD_ARGS)` |
| `gate-stats`  | `Skill(skill="vg:gate-stats", args=FWD_ARGS)` |
| `recover`     | `Skill(skill="vg:recover", args=FWD_ARGS)` |
| `help` / ""   | print menu below, exit 0 |

```bash
if [ -z "$VERB" ] || [ "$VERB" = "help" ]; then
  cat <<'HELP'

🩺 ━━━ /vg:doctor — VG state inspection router ━━━

This command is a thin dispatcher. Use the sub-commands directly for clarity:

  /vg:health [phase]              Project health summary, or phase deep inspect
  /vg:integrity [phase]           Hash-validate artifacts across all (or one) phase
  /vg:gate-stats [--gate-id=X]    Gate event counts + override pressure
  /vg:recover {phase} [--apply]   Classify corruption + print recovery commands

Legacy flags (DEPRECATED, still routed):
  /vg:doctor --integrity          → /vg:integrity
  /vg:doctor --gates              → /vg:gate-stats
  /vg:doctor --recover {phase}    → /vg:recover {phase}

HELP
  exit 0
fi

echo "→ Routing to /vg:${VERB}${FWD_ARGS}"
# Model side: now invoke Skill(skill="vg:${VERB}", args="${FWD_ARGS}")
```
</step>

</process>

<success_criteria>
- ≤80 LOC, no direct health/integrity/gate/recover logic.
- Legacy `--integrity | --gates | --recover` flags emit DEPRECATED warn and still route correctly.
- Unknown verb or no verb → help menu, exit 0.
- Router prints chosen target; outer model invokes via Skill tool.
</success_criteria>
</content>
</invoke>
