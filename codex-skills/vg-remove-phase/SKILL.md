---
name: "vg-remove-phase"
description: "Remove phase from ROADMAP.md + archive/delete phase directory"
metadata:
  short-description: "Remove phase from ROADMAP.md + archive/delete phase directory"
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

This skill is invoked by mentioning `$vg-remove-phase`. Treat all user text after `$vg-remove-phase` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<rules>
1. **VG-native** — no GSD delegation. This command is self-contained.
2. **Config-driven** — read .claude/vg.config.md for project paths, profile, models.
3. **ROADMAP.md required** — must exist. Missing = suggest `/vg:roadmap` first.
4. **No renumbering** — removing a phase NEVER changes existing phase numbers. Gap in numbering is acceptable.
5. **Dependency safety** — warn (not block) if other phases depend on the one being removed.
6. **Archive by default** — recommend archiving over permanent deletion. Data loss is irreversible.
</rules>

<objective>
Remove a phase from the project roadmap. Inverse of `/vg:add-phase`. Shows phase info, checks downstream dependencies, confirms action, then archives or deletes the phase directory and updates ROADMAP.md + REQUIREMENTS.md traceability.

Not part of the main pipeline — utility command run anytime.
</objective>

<process>

**Config:** Read .claude/commands/vg/_shared/config-loader.md first. Use config variables ($PLANNING_DIR, $PHASES_DIR).

<step name="0_parse_and_validate">
## Step 0: Parse phase argument + validate state

```bash
PHASE_NUMBER="$1"
ROADMAP_FILE="${PLANNING_DIR}/ROADMAP.md"
REQUIREMENTS_FILE="${PLANNING_DIR}/REQUIREMENTS.md"

# Validate ROADMAP exists
if [ ! -f "$ROADMAP_FILE" ]; then
  echo "BLOCK: ROADMAP.md not found. Nothing to remove from."
  exit 1
fi

# Resolve phase directory
PHASE_DIR=$(find ${PHASES_DIR} -maxdepth 1 -type d \( -name "${PHASE_NUMBER}*" -o -name "0${PHASE_NUMBER}*" \) 2>/dev/null | head -1)

if [ -z "$PHASE_DIR" ] || [ ! -d "$PHASE_DIR" ]; then
  echo "BLOCK: Phase ${PHASE_NUMBER} directory not found in ${PHASES_DIR}/"
  exit 1
fi

PHASE_NAME=$(basename "$PHASE_DIR")
```
</step>

<step name="1_show_phase_info">
## Step 1: Show phase info

Read ROADMAP.md and extract the phase block. Read phase directory to inventory artifacts.

```bash
# Count artifacts
ARTIFACT_COUNT=$(ls "${PHASE_DIR}"/*.md "${PHASE_DIR}"/*.json 2>/dev/null | wc -l)

# List key artifacts
ARTIFACTS=$(ls "${PHASE_DIR}"/*.md "${PHASE_DIR}"/*.json 2>/dev/null | xargs -I{} basename {})

# Check pipeline status by artifact presence
PIPELINE_STATUS="empty"
[ -f "${PHASE_DIR}/SPECS.md" ]          && PIPELINE_STATUS="specced"
[ -f "${PHASE_DIR}/CONTEXT.md" ]        && PIPELINE_STATUS="scoped"
[ -f "${PHASE_DIR}/PLAN.md" ]           && PIPELINE_STATUS="planned"
[ -f "${PHASE_DIR}/SUMMARY.md" -o -f "${PHASE_DIR}/SUMMARY-wave1.md" ] && PIPELINE_STATUS="built"
[ -f "${PHASE_DIR}/RUNTIME-MAP.json" ]  && PIPELINE_STATUS="reviewed"
[ -f "${PHASE_DIR}/SANDBOX-TEST.md" ]   && PIPELINE_STATUS="tested"
[ -f "${PHASE_DIR}/UAT.md" ]            && PIPELINE_STATUS="accepted"
```

Display:
```
Phase ${PHASE_NUMBER}: ${PHASE_NAME}
  Directory: ${PHASE_DIR}/
  Pipeline status: ${PIPELINE_STATUS}
  Artifacts: ${ARTIFACT_COUNT} files
  ${ARTIFACTS}
```

Extract dependencies from ROADMAP.md (the "Depends on" field for this phase).
</step>

<step name="2_check_dependencies">
## Step 2: Check downstream dependencies

Grep ROADMAP.md for phases that list this phase in their "Depends on" field.

```bash
# Find phases that depend on the phase being removed
DEPENDENTS=$(grep -B5 "Depends on:.*${PHASE_NUMBER}" "$ROADMAP_FILE" | grep -oP 'Phase \K[\d.]+' | grep -v "^${PHASE_NUMBER}$")
```

If dependents found:
```
WARNING: The following phases depend on Phase ${PHASE_NUMBER}:
  ${DEPENDENTS}

Removing Phase ${PHASE_NUMBER} will break their dependency chain.
These phases' "Depends on" field will be updated to remove the reference.
```

If no dependents:
```
No downstream dependencies found. Safe to remove.
```
</step>

<step name="3_confirm">
## Step 3: Confirm removal action

```
AskUserQuestion:
  header: "Remove Phase ${PHASE_NUMBER}: ${PHASE_NAME}"
  question: "How should this phase be removed?"
  options:
    - "Remove + archive (recommended) — move to ${PLANNING_DIR}/archive/${PHASE_NAME}/"
    - "Remove + delete — permanently delete phase directory"
    - "Cancel — abort removal"
```

If "Cancel" → exit without changes.

Store: `$REMOVAL_MODE` = "archive" | "delete"
</step>

<step name="4_execute">
## Step 4: Execute removal

### 4a: Remove phase entry from ROADMAP.md

Find the phase block in ROADMAP.md (from `## Phase ${PHASE_NUMBER}:` to the next `## Phase` or end of file).
Use Edit tool to remove the entire block. Do NOT rewrite the entire file.

### 4b: Move or delete phase directory

```bash
if [ "$REMOVAL_MODE" = "archive" ]; then
  ARCHIVE_DIR="${PLANNING_DIR}/archive"
  mkdir -p "$ARCHIVE_DIR"
  mv "$PHASE_DIR" "${ARCHIVE_DIR}/${PHASE_NAME}"
  echo "Archived: ${PHASE_DIR} → ${ARCHIVE_DIR}/${PHASE_NAME}/"
else
  rm -rf "$PHASE_DIR"
  echo "Deleted: ${PHASE_DIR}/"
fi
```

### 4c: Update REQUIREMENTS.md traceability

If REQUIREMENTS.md exists:
- Find rows where Phase column = `${PHASE_NUMBER}`
- Set Phase column to `---` (unmap — requirement returns to available pool)
- Use Edit tool for surgical updates

```bash
if [ -f "$REQUIREMENTS_FILE" ]; then
  # For each REQ-ID mapped to this phase, reset Phase column to "---"
  # Use Edit tool — do NOT rewrite entire file
  echo "REQUIREMENTS.md: unmapped REQ-IDs from Phase ${PHASE_NUMBER}"
fi
```

### 4d: Update dependent phases (if any)

If step 2 found dependents:
- For each dependent phase in ROADMAP.md, edit its "Depends on" field to remove `${PHASE_NUMBER}`
- If "Depends on" becomes empty after removal, set to "None"

```bash
if [ -n "$DEPENDENTS" ]; then
  for dep in $DEPENDENTS; do
    # Edit ROADMAP.md: remove PHASE_NUMBER from the "Depends on" field of phase $dep
    echo "Updated Phase ${dep}: removed dependency on Phase ${PHASE_NUMBER}"
  done
fi
```
</step>

<step name="5_commit">
## Step 5: Commit changes

```bash
# Stage all changes
git add "$ROADMAP_FILE"
[ -f "$REQUIREMENTS_FILE" ] && git add "$REQUIREMENTS_FILE"

if [ "$REMOVAL_MODE" = "archive" ]; then
  git add "${PLANNING_DIR}/archive/${PHASE_NAME}"
  # Also stage the removal of the original directory
  git add "$PHASE_DIR"
else
  git add "$PHASE_DIR"
fi

git commit -m "roadmap: remove phase ${PHASE_NUMBER} — ${PHASE_NAME}

Action: ${REMOVAL_MODE}
$([ -n "$DEPENDENTS" ] && echo "Updated dependents: ${DEPENDENTS}")

Co-Authored-By: Claude <noreply@anthropic.com>"
```

Display:
```
Phase ${PHASE_NUMBER} removed: ${PHASE_NAME}
  Action: ${REMOVAL_MODE}
  $([ "$REMOVAL_MODE" = "archive" ] && echo "Archive: ${PLANNING_DIR}/archive/${PHASE_NAME}/")
  ROADMAP.md updated (phase block removed)
  $([ -f "$REQUIREMENTS_FILE" ] && echo "REQUIREMENTS.md updated (REQ-IDs unmapped)")
  $([ -n "$DEPENDENTS" ] && echo "Dependent phases updated: ${DEPENDENTS}")
  
  Committed to git.
```
</step>

</process>

<success_criteria>
- Phase block removed from ROADMAP.md
- Phase directory archived to ${PLANNING_DIR}/archive/ or permanently deleted (per user choice)
- REQUIREMENTS.md Phase column reset to "---" for previously-mapped REQ-IDs
- Dependent phases' "Depends on" field updated to remove reference
- No existing phase numbers changed (gap in numbering is acceptable)
- All changes committed to git
- Clear summary of what was removed and where archive lives (if applicable)
</success_criteria>
