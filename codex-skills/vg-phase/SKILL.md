---
name: "vg-phase"
description: "Run full 7-step phase pipeline — specs → scope → blueprint → build → review → test → accept"
metadata:
  short-description: "Run full 7-step phase pipeline — specs → scope → blueprint → build → review → test → accept"
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

This skill is invoked by mentioning `$vg-phase`. Treat all user text after `$vg-phase` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<objective>
Orchestrate the full VG pipeline for a phase. Runs steps sequentially, stopping on failure with resume guidance.

Full pipeline (3 stages):
```
Project init:     /vg:project → /vg:roadmap → /vg:map (optional)
Phase planning:   /vg:prioritize → /vg:specs → /vg:scope → /vg:scope-review
Phase execution:  /vg:blueprint → /vg:build → /vg:review → /vg:test → /vg:accept
```

This command runs the **phase execution** stage (7 steps): specs → scope → blueprint → build → review → test → accept.
For project init (`/vg:init` → `/vg:project` → `/vg:roadmap` → `/vg:map`) or phase planning (`/vg:prioritize`), use the individual commands listed above.

Flags:
- `--from={step}` — resume from specific step (e.g., `--from=review`)
- `--auto` — auto-advance through steps without pausing between them
</objective>

<process>

<step name="0_load_config">
Read .claude/commands/vg/_shared/config-loader.md.
</step>

<step name="1_parse_args">
Parse `$ARGUMENTS`:
- First positional token → `PHASE_ARG`
- Optional `--from={step}` → `START_STEP` (default: auto-detect)
- Optional `--auto` → auto-advance mode

Valid step names: `specs`, `scope`, `blueprint`, `build`, `review`, `test`, `accept`

Resolve `PHASE_DIR` from `PHASE_ARG`:
```bash
PHASE_DIR=$(find ${PLANNING_DIR}/phases -maxdepth 1 -type d \( -name "${PHASE_ARG}*" -o -name "0${PHASE_ARG}*" \) 2>/dev/null | head -1)
if [ -z "$PHASE_DIR" ]; then
  echo "Phase dir not found for: $PHASE_ARG"
  exit 1
fi

# Warn if phase dir contains non-ASCII characters (Windows/git compatibility)
if echo "${PHASE_DIR}" | LC_ALL=C grep -q '[^[:print:][:space:]]'; then
  echo "WARNING: Phase directory contains non-ASCII characters: ${PHASE_DIR}"
  echo "  This may cause issues on Windows or in git. Consider renaming."
fi
```
</step>

<step name="1b_phase_recon">
**Phase Reconnaissance — inventory + classify + recommend BEFORE routing.**

Follow `.claude/commands/vg/_shared/phase-recon.md`.

This step runs `phase-recon.py` against the phase dir, classifies every file
(V6 canonical / V5 numbered / legacy GSD / versioned rot / orphan), determines
pipeline position, and if legacy/hybrid → presents interactive migration menu.

```bash
${PYTHON_BIN} .claude/scripts/phase-recon.py \
  --phase-dir "${PHASE_DIR}" --profile "${PROFILE}" ${RECON_FRESH:+--fresh}

PHASE_TYPE=$(${PYTHON_BIN} -c "
import json; s=json.load(open('${PHASE_DIR}/.recon-state.json', encoding='utf-8'))
print(s['phase_type'])
")
```

If `PHASE_TYPE ∈ {legacy_gsd, v5_iterative, hybrid}`:
- Show `.recon-report.md` summary
- Present migration menu per `_shared/phase-recon.md` step R3b
- Apply user choice (consolidate → migrate → archive)
- Re-recon after mutations

After recon, read the recommended_action:
```bash
RECON_STEP=$(${PYTHON_BIN} -c "
import json; s=json.load(open('${PHASE_DIR}/.recon-state.json', encoding='utf-8'))
print(s['recommended_action']['step'])
")
```

If `--from` was specified, `START_STEP = --from` (user override).
Otherwise, `START_STEP = ${RECON_STEP}` (recon-driven).
</step>

<step name="2_detect_start">
`START_STEP` is now set by step 1b (recon-driven) or `--from` (user override).

If `START_STEP == "complete"` → phase done, skip pipeline execution.

Display:
```
## VG Phase {N} — V6 Pipeline

Phase type:   {PHASE_TYPE} (from recon)
Starting from: {START_STEP} (step {N}/6)
Mode: {auto|interactive}
```
</step>

<step name="2b_create_task_tracker">
**Create visual task list for pipeline progress tracking.**

Create 6 tasks — one per pipeline step. Mark already-completed steps immediately.
Steps before `START_STEP` that have artifacts → mark as `completed`.
The `START_STEP` itself → leave as `pending` (will be marked `in_progress` when it runs).

```
TaskCreate: "Step 1/6: scope — extract decisions"        (activeForm: "Running scope...")
TaskCreate: "Step 2/6: blueprint — plan + API contracts"  (activeForm: "Running blueprint...")
TaskCreate: "Step 3/6: build — execute code"              (activeForm: "Running build...")
TaskCreate: "Step 4/6: review — discovery + fix loop"      (activeForm: "Running review...")
TaskCreate: "Step 5/6: test — goal verification"           (activeForm: "Running test...")
TaskCreate: "Step 6/6: accept — human UAT"                (activeForm: "Running accept...")
```

Store task IDs as: `TASK_SCOPE`, `TASK_BLUEPRINT`, `TASK_BUILD`, `TASK_REVIEW`, `TASK_TEST`, `TASK_ACCEPT`.

For each step with existing artifact (before START_STEP):
```
TaskUpdate: taskId={TASK_ID}, status="completed"
```
</step>

<step name="3_execute_pipeline">
Run steps sequentially. **For each step:**

1. `TaskUpdate: taskId={TASK_ID}, status="in_progress"` — spinner shows activeForm
2. Invoke the command via SlashCommand
3. Check step succeeded (artifact created)
4. If **failed** → STOP:
   - `TaskUpdate: taskId={TASK_ID}, status="pending"` (reset, not completed)
   - Display: "Resume with `/vg:phase {phase} --from={current_step}`"
5. If **succeeded**:
   - `TaskUpdate: taskId={TASK_ID}, status="completed"`
   - If auto mode → proceed to next step
   - If interactive mode → pause:
     ```
     Step {N}/6 ({step_name}) complete.
     Continue to {next_step}? (y/skip/stop)
     ```
   - If user says "skip":
     - **⛔ PREREQUISITE GATE (tightened 2026-04-17):** check if the step AFTER the skipped one depends on artifacts produced by the skipped step. If yes, BLOCK the skip and force the step to run.

     Dependency rules (hardcoded — see "Step sequence" table below):
     | Skipping | Next step needs | Block if missing |
     |----------|-----------------|-------------------|
     | scope | blueprint needs CONTEXT.md | CONTEXT.md |
     | blueprint | build needs PLAN*.md + API-CONTRACTS.md | any PLAN*.md |
     | build | review needs commits (git log) | phase commits count > 0 |
     | review | test needs RUNTIME-MAP.json + GOAL-COVERAGE-MATRIX.md | either file |
     | test | accept needs *-SANDBOX-TEST.md (verdict != FAILED) | SANDBOX-TEST.md |

     ```bash
     # Run before TaskUpdate completed. If block triggered, display:
     echo "⛔ Cannot skip ${step_name} — downstream step ${next_step} requires artifacts that haven't been built:"
     echo "   Missing: ${MISSING_ARTIFACTS}"
     echo "   Options:"
     echo "     (a) Run ${step_name} to produce the artifacts"
     echo "     (b) Provide artifacts manually, then /vg:${next_step} {phase}"
     echo "     (c) Exit pipeline"
     # Do NOT mark task completed. Do NOT advance.
     ```

     - If prerequisites ARE satisfied (e.g., artifacts from prior manual work exist) → `TaskUpdate: taskId={NEXT_TASK_ID}, status="completed"` and move to step after.

**Step sequence:**

| # | Step | Command | Task ID | Success = artifact exists |
|---|------|---------|---------|--------------------------|
| 1 | scope | `/vg:scope {phase}` | TASK_SCOPE | CONTEXT.md |
| 2 | blueprint | `/vg:blueprint {phase}` | TASK_BLUEPRINT | PLAN*.md + API-CONTRACTS.md |
| 3 | build | `/vg:build {phase}` | TASK_BUILD | SUMMARY*.md |
| 4 | review | `/vg:review {phase}` | TASK_REVIEW | RUNTIME-MAP.json + RUNTIME-MAP.md |
| 5 | test | `/vg:test {phase}` | TASK_TEST | *-SANDBOX-TEST.md with verdict != FAILED |
| 6 | accept | `/vg:accept {phase}` | TASK_ACCEPT | *-UAT.md with status "complete" |

**Fast-path (AI-recommended):**
Before starting, assess scope complexity:
- Small change (1-2 files, no new pages) → **⛔ forced user pause** (review skip = fewer gates, higher risk of missed drift):
  Invoke `AskUserQuestion`:
    - header: "Skip review step?"
    - question: "Phase scope nhỏ (1-2 files). Recommend bỏ qua /vg:review → chạy: specs → scope → blueprint → build → test → accept. Review giúp phát hiện runtime drift, bỏ qua nhanh hơn nhưng rủi ro hơn. Approve skip?"
    - options:
      - "Yes — skip review (phase nhỏ, ít drift risk)"
      - "No — chạy full pipeline có review (safer)"
  Không auto-skip. Nếu user chọn Yes → `TaskUpdate: taskId=TASK_REVIEW, status="completed"` (mark skipped + log reason to override-debt: "user-approved skip for small scope").
- Medium/large change → full pipeline (không hỏi, review luôn chạy)
</step>

<step name="4_complete">
After all steps:
```
Phase {N} — V5 Pipeline COMPLETE

Steps completed: {N}/6
Artifacts:
  ✓ SPECS.md → CONTEXT.md → PLAN.md + API-CONTRACTS.md
  ✓ SUMMARY.md → RUNTIME-MAP.json + RUNTIME-MAP.md
  ✓ SANDBOX-TEST.md → UAT.md
  
Generated tests: {N} .spec.ts files (CI-ready)

▶ /vg:next (advance to next phase)
```
</step>

</process>
