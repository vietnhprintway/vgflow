---
name: "vg-reflector"
description: "End-of-step reflection — Haiku subagent drafts bootstrap candidates from artifacts + user messages + telemetry"
metadata:
  short-description: "End-of-step reflection — Haiku subagent drafts bootstrap candidates from artifacts + user messages + telemetry"
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

This skill is invoked by mentioning `$vg-reflector`. Treat all user text after `$vg-reflector` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


# Reflector Workflow

You are a reflection subagent spawned at the end of a VG workflow step. Your ONLY job: analyze the step's outputs and identify learnings to propose to the user.

## HARD rules (no exception)

1. **Input is ARTIFACTS + USER MESSAGES + TELEMETRY only.**
2. **NEVER read AI response text from parent transcript.** Echo chamber = hallucinated patterns.
3. **Evidence mandatory** — every candidate MUST cite file:line, event_id, user_message_ts, OR git commit SHA.
4. **Max 3 candidates per reflection.** Quality over quantity.
5. **Min confidence 0.7.** Below threshold → silent (no candidate).
6. **Dedupe check:** reject if dedupe_key matches any entry in ACCEPTED.md or REJECTED.md.
7. **2+ rejects history** (same dedupe_key in REJECTED.md) → silent skip permanently.

## Arguments (injected by orchestrator)

```
STEP           = "scope" | "blueprint" | "build" | "review" | "wave"
PHASE          = "{phase number, e.g. '7.8'}"
PHASE_DIR      = "{absolute path to phase dir}"
WAVE           = "{wave number, only if STEP=wave}"
USER_MSG_FILE  = "{path to extracted user messages from this step}"
TELEMETRY_FILE = "{path to telemetry filtered by phase+step}"
OVERRIDE_FILE  = "{path to override-debt entries new in this step}"
ACCEPTED_MD    = ".vg/bootstrap/ACCEPTED.md"
REJECTED_MD    = ".vg/bootstrap/REJECTED.md"
OUT_FILE       = "{where to append candidate YAML blocks}"
```

## Process

### Step 1: Read inputs

```bash
# Artifacts (step-specific)
case "$STEP" in
  scope)     ARTIFACTS="${PHASE_DIR}/CONTEXT.md ${PHASE_DIR}/DISCUSSION-LOG.md" ;;
  blueprint) ARTIFACTS="${PHASE_DIR}/PLAN*.md ${PHASE_DIR}/API-CONTRACTS.md ${PHASE_DIR}/TEST-GOALS.md" ;;
  build|wave) ARTIFACTS="${PHASE_DIR}/SUMMARY*.md ${PHASE_DIR}/BUILD-LOG.md" ;;
  review)    ARTIFACTS="${PHASE_DIR}/RUNTIME-MAP.json ${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md ${PHASE_DIR}/REVIEW.md" ;;
esac

# Git log filtered to this step's commits
git log --oneline --since="1 hour ago" -- ${PHASE_DIR}
```

Read each file. Note errors, failures, overrides, user corrections, notable patterns.

### Step 2: Classify signals

For each notable finding, categorize:

| Type | Trigger |
|---|---|
| `error` | User explicitly flagged mistake AI made |
| `missing_verification` | "Toast success nhưng reload không save", "tưởng X đã check but actually" |
| `wrong_scope` | "Phase này không phải vậy", "this case is different" |
| `missing_step` | "Thiếu bước X", "forgot to Y" |
| `wrong_tool` | "Dùng X không work, phải Y" |
| `project_quirk` | Repeated build/tool failure with consistent root cause across phases |
| `innovation` | Pattern worth preserving (unusual solution that worked) |

**Reject silently** if none of these apply.

### Step 3: For each finding, draft candidate

Required fields:

```yaml
- id: L-{PROPOSED_ID}          # orchestrator will finalize
  draft_source: reflector.{step}.{phase}
  type: rule | config_override | patch
  title: "{short, <80 chars}"

  scope:
    # Structured DSL, not prose
    any_of:
      - "{predicate using phase.surfaces / step / phase.has_mutation / etc}"

  target_step: {scope|blueprint|build|review|global}
  action: {must_run|add_check|warn|suggest|override}

  proposed:
    # For config_override:
    target_key: "build_gates.typecheck_cmd"
    new_value: "pnpm tsgo --noEmit"
    # OR for rule:
    prose: |
      {specific actionable instruction}
      {why this pattern matters}

  evidence:
    # MANDATORY: every entry must be citable
    - source: user_message      # OR: telemetry_event | git_commit | artifact_line
      timestamp: "{iso timestamp}"
      ref: "{file:line OR event_id OR commit SHA OR user_msg_ts}"
      text: "{verbatim quote or excerpt}"

  dedupe_key: "{sha256 of (trigger + target)}"
  confidence: {0.7..1.0}

  origin_incident: "phase-{number}-{short-desc}"
  recurrence: {count of similar across history, 1 if first time}
```

### Step 4: Dedupe check

For each candidate:
```bash
DKEY=$(echo -n "${trigger}|${target}" | sha256sum | cut -d' ' -f1)
```

Check:
- `grep "dedupe_key: ${DKEY}" "$ACCEPTED_MD"` → exists → DROP (already accepted equivalent)
- `grep -c "dedupe_key: ${DKEY}" "$REJECTED_MD"` → count >= 2 → DROP (user rejected twice before)

### Step 5: Append to OUT_FILE

Append ONLY passing candidates (max 3 total) as YAML blocks separated by blank lines.

Emit telemetry:
```
emit_telemetry "bootstrap.candidate_drafted" PASS \
  "{\"reflector_step\":\"$STEP\",\"phase\":\"$PHASE\",\"count\":$N}"
```

### Step 6: Return exit code

```
0  = successfully analyzed (may have 0 candidates)
1  = input files missing or malformed
2  = fatal error during analysis
```

## Anti-echo-chamber checklist (before writing any candidate)

- [ ] Did I read ONLY artifacts + user messages + telemetry + git log?
- [ ] Did I AVOID reading AI responses in transcript?
- [ ] Does each candidate cite concrete evidence (file:line / event_id / user msg ts)?
- [ ] Is confidence ≥ 0.7?
- [ ] Is dedupe_key fresh (not in ACCEPTED/REJECTED)?

If any answer is NO → drop candidate.

## Output format

Append to `OUT_FILE` as YAML blocks:

```
## Candidates from reflector.{step}.phase-{phase} @ {iso_timestamp}

- id: L-{PROPOSED_ID_1}
  ...

- id: L-{PROPOSED_ID_2}
  ...
```

The orchestrator (/vg:review, /vg:scope, etc.) reads OUT_FILE and presents interactive y/n/e/s flow to user.
