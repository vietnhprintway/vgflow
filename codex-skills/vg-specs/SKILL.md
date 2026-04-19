---
name: "vg-specs"
description: "Create SPECS.md for a phase — AI-draft or user-guided mode"
metadata:
  short-description: "Create SPECS.md for a phase — AI-draft or user-guided mode"
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

This skill is invoked by mentioning `$vg-specs`. Treat all user text after `$vg-specs` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<objective>
Generate a concise SPECS.md defining phase goal, scope, constraints, and success criteria. This is the FIRST step of the VG pipeline — specs must be locked before scope, blueprint, or build can proceed.

Output: `${PLANNING_DIR}/phases/{phase_dir}/SPECS.md`
</objective>

<process>

**Config:** Read .claude/commands/vg/_shared/config-loader.md first.

<step name="parse_args">
## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- **phase_number** — Required. e.g., "7.4", "8", "3.1"
- **--auto flag** — Optional. If present, skip interactive questions and AI-draft directly.

**Validate:**
1. Read `${PLANNING_DIR}/ROADMAP.md` — confirm the phase exists
2. Extract the phase goal and success criteria from ROADMAP
3. Determine the phase directory name (e.g., `07.4-some-slug`) by scanning `${PHASES_DIR}/`
4. If phase dir doesn't exist, create it: `${PHASES_DIR}/{phase_dir}/`

**Fail fast:** If phase not found in ROADMAP.md, tell user and stop.
</step>

<step name="check_existing">
## Step 2: Check Existing SPECS.md

If `${PHASES_DIR}/{phase_dir}/SPECS.md` already exists:

Ask user:
```
SPECS.md already exists for Phase {N}.
1. View — Show current contents
2. Edit — Keep existing, modify specific sections
3. Overwrite — Start fresh
```

Act on their choice. If "View", show contents then re-ask. If "Edit", proceed to guided editing of specific sections. If "Overwrite", continue to step 3.

If SPECS.md does not exist, continue to step 3.
</step>

<step name="load_context">
## Step 3: Load Context

Read these files to build context for spec generation:

1. **ROADMAP.md** — Phase goal, success criteria, dependencies
2. **PROJECT.md** — Project constraints, stack, architecture decisions
3. **STATE.md** — Current progress, what's already done
4. **Prior SPECS.md files** — Scan `${PHASES_DIR}/*/SPECS.md` for style and depth reference (read 1-2 most recent)

Store extracted context:
- `phase_goal`: from ROADMAP
- `phase_success_criteria`: from ROADMAP
- `project_constraints`: from PROJECT.md
- `prior_phases_done`: from STATE.md
- `spec_style`: from prior SPECS.md files
</step>

<step name="choose_mode">
## Step 4: Choose Mode

If `--auto` flag is set, skip to step 6 (generate_draft).

Otherwise, ask user:

```
Phase {N}: {phase_goal}

Ban muon tao SPECS theo cach nao?
1. AI Draft — Toi tu draft dua tren ROADMAP + PROJECT.md
2. Guided — Toi hoi 4-5 cau de ban mo ta
```

- If "1" or "AI Draft" → go to step 6 (generate_draft)
- If "2" or "Guided" → go to step 5 (guided_questions)
</step>

<step name="guided_questions">
## Step 5: Guided Questions (User-Guided Mode)

Ask questions ONE AT A TIME. After each answer, save it immediately to avoid context loss.

**Q1: Goal**
```
Muc tieu chinh cua phase nay la gi? (1-2 cau)
(ROADMAP noi: "{phase_goal}")
```
Save answer → proceed.

**Q2: Scope IN**
```
Nhung gi NAM TRONG scope? (liet ke features/tasks)
```
Save answer → proceed.

**Q3: Scope OUT**
```
Nhung gi KHONG lam trong phase nay? (exclusions ro rang)
```
Save answer → proceed.

**Q4: Constraints**
```
Rang buoc ky thuat hoac business nao can luu y?
(VD: latency, compatibility, dependencies)
```
Save answer → proceed.

**Q5: Success Criteria**
```
Lam sao biet phase nay DONE? (tieu chi do luong duoc)
```
Save answer → proceed to step 6 with user answers as primary input.
</step>

<step name="generate_draft">
## Step 6: Generate Draft

**If AI Draft mode (--auto or user chose option 1):**
- Generate SPECS.md content from ROADMAP phase goal + PROJECT.md constraints
- Infer scope, constraints, and success criteria from available context
- Match style of prior SPECS.md files if they exist

**If Guided mode:**
- Use user's answers from step 5 as primary content
- Supplement with ROADMAP and PROJECT.md context where user answers are sparse
- Do NOT override user's explicit answers with AI inference

**Show the full draft to the user:**
```
--- SPECS.md Preview ---
{full content}
--- End Preview ---

Approve? (y/edit/n)
- y: Write file
- edit: Tell me what to change
- n: Discard
```

If "edit": ask what to change, regenerate, show again.
If "n": stop.
If "y": proceed to step 7.
</step>

<step name="write_specs">
## Step 7: Write SPECS.md

Write to `${PHASES_DIR}/{phase_dir}/SPECS.md` with this exact format:

```markdown
---
phase: {X}
status: approved
created: {YYYY-MM-DD}
source: ai-draft|user-guided
---

## Goal

{1-2 sentence phase objective}

## Scope

### In Scope
- {feature/task 1}
- {feature/task 2}
- ...

### Out of Scope
- {exclusion 1}
- {exclusion 2}
- ...

## Constraints
- {constraint 1}
- {constraint 2}
- ...

## Success Criteria
- [ ] {measurable criterion 1}
- [ ] {measurable criterion 2}
- ...

## Dependencies
- {dependency on prior phase or external system}
- ...
```

**source** field: `ai-draft` if --auto or user chose option 1, `user-guided` if user answered questions.
**created** field: today's date in YYYY-MM-DD format.
</step>

<step name="commit_and_next">
## Step 8: Commit and Next Step

1. Git add and commit:
   ```
   git add ${PHASES_DIR}/{phase_dir}/SPECS.md
   git commit -m "specs({phase}): create SPECS.md for phase {N}"
   ```

2. Display completion:
   ```
   SPECS.md created for Phase {N}.
   Next: /vg:scope {phase}
   ```
</step>

</process>

<success_criteria>
- SPECS.md written to `${PHASES_DIR}/{phase_dir}/SPECS.md`
- Contains ALL sections: Goal, Scope (In/Out), Constraints, Success Criteria, Dependencies
- Frontmatter includes phase, status, created, source fields
- User explicitly approved the content before writing
- Git committed
</success_criteria>
