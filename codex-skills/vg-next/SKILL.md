---
name: "vg-next"
description: "Auto-detect current VG pipeline step and show what to run next"
metadata:
  short-description: "Detect pipeline position and suggest next command"
---

<codex_skill_adapter>
## A. Skill Invocation
- This skill is invoked by mentioning `$vg-next`.
- Treat all user text after `$vg-next` as arguments: `{{PHASE}}`
- If no phase given, read STATE.md to detect current phase automatically.

## B. AskUserQuestion → request_user_input Mapping
GSD workflows use `AskUserQuestion` (Claude Code syntax). Translate to Codex `request_user_input`:
- AskUserQuestion(question="X") → request_user_input(prompt="X")

## C. No browser needed
This skill only reads files — no Playwright required.
</codex_skill_adapter>

<rules>
1. Read config from `.claude/vg.config.md` (or `vg.config.md` at project root).
2. Read `${PLANNING_DIR}/STATE.md` to detect current phase if not given.
3. Evaluate routes IN ORDER — first match wins.
4. Display the exact command to run next (using `$vg-*` prefix for Codex CLI).
5. For cross-CLI options, show both Claude (`/vg:*`) and Codex (`$vg-*`) variants.
</rules>

<process>

**Step 1: Load config**
Read `.claude/vg.config.md` → extract `paths.planning`, `paths.phases`, `profile`.
- PLANNING_DIR = `{paths.planning}` (default: `.planning`)
- PHASES_DIR = `{paths.phases}` (default: `.planning/phases`)
- PROFILE = `{profile}` (default: `web-fullstack`)

Profile determines which steps apply. Use `${PYTHON_BIN} .claude/scripts/filter-steps.py --command <cmd.md> --profile $PROFILE --output-ids` to check expected steps for any command.

**Step 2: Detect phase**
If phase argument given → use it.
Else → read `${PLANNING_DIR}/STATE.md` → extract `current_phase` and `phase_dir`.

PHASE_DIR = `${PHASES_DIR}/{phase_dir}`

**Step 3: Evaluate routes**

**Route 0:** `STATE.md` has `paused_at` field
→ Display: "Work paused. Resume with: `/gsd:resume-work`"

**Route 1:** No `SPECS.md` in PHASE_DIR
→ Display: "No SPECS.md found. Start with: `$vg-specs {phase}` or `/vg:specs {phase}`"

**Route 2:** `SPECS.md` exists, no `CONTEXT.md`
→ Display: "Next: `/vg:scope {phase}` (scope requires Claude — reads SPECS + guides decisions)"

**Route 3:** `CONTEXT.md` exists, no `PLAN*.md` or no `API-CONTRACTS.md`
→ Display: "Next: `/vg:blueprint {phase}` (blueprint requires Claude)"

**Route 4:** `PLAN*.md` + `API-CONTRACTS.md` exist, no `SUMMARY*.md`
→ Display: "Next: `/vg:build {phase}` (build requires Claude)"

**Marker-based precision check (fixes drift when SUMMARY exists but steps incomplete):**
After determining candidate route, cross-check `.step-markers/` for the active command. If expected markers (per profile) are missing, show resume instruction instead:
```bash
CMD_FOR_ROUTE={review|test|accept}  # derived from current route
EXPECTED=$(${PYTHON_BIN} .claude/scripts/filter-steps.py --command .claude/commands/vg/${CMD_FOR_ROUTE}.md --profile $PROFILE --output-ids)
for step in $(echo "$EXPECTED" | tr ',' ' '); do
  if [ ! -f "${PHASE_DIR}/.step-markers/${step}.done" ]; then
    MISSING="$MISSING $step"
  fi
done
if [ -n "$MISSING" ]; then
  echo "⚠ ${CMD_FOR_ROUTE} previously ran but $(echo $MISSING | wc -w) steps missing markers:$MISSING"
  echo "   Resume with: /vg:${CMD_FOR_ROUTE} {phase} --resume"
fi
```

**Route 5:** `SUMMARY*.md` exists, no `RUNTIME-MAP.json`
→ Display:
```
Next: Review — choose mode:

A) Standard (Claude):   `/vg:review {phase}`
B) Discovery (Codex):   `$vg-review {phase} --discovery-only`
   Then evaluate (Claude): `/vg:review {phase} --evaluate-only`

Add `--full-scan` to disable snapshot pruning (full accessibility tree, slower).
Default: pruning ON — saves 50-70% tokens by filtering sidebar/header/footer.
```

**Route 5b:** `RUNTIME-MAP.json` exists + `GOAL-COVERAGE-MATRIX.md` exists + gate = BLOCK
→ Read `discovery-state.json` → `completed_phase`
→ Read `GOAL-COVERAGE-MATRIX.md` → failed goals
→ Read `RUNTIME-MAP.json` → `goal_sequences[id].start_view`

**Display to user (explain, then action):**

```
⚠ Phase {N} gate BLOCKED — {X}/{total} goals failed.

┌─ What the failure types mean ─────────────────────────────────┐
│ UNREACHABLE ({N})  Scan couldn't find the feature's view/route│
│                    → Feature likely not built yet             │
│                    → Fix: build the missing code              │
│                                                               │
│ BLOCKED ({N})      View found, but goal criteria not met      │
│                    (form didn't submit, API error, assertion  │
│                    failed, toast not shown, etc.)             │
│                    → Code has a bug — fix and re-scan         │
│                                                               │
│ INTERRUPTED        Review died mid-scan (token/timeout)       │
│                    → Just resume where it left off            │
└───────────────────────────────────────────────────────────────┘

Failed goals:
  [UNREACHABLE] {goal_id}: {goal_desc}
  [BLOCKED]     {goal_id}: {goal_desc} (view: {start_view})
  ...
```

**Then route by classification:**

```
IF completed_phase ≠ "investigate":
  → INTERRUPTED. Run: `$vg-review {phase} --resume` (or `/vg:review {phase} --resume` in Claude)

IF completed_phase == "investigate":
  Classify goals:
    UNREACHABLE = no start_view in goal_sequences
    BLOCKED     = has start_view but result=failed

  All UNREACHABLE → feature missing, build it:
    `/vg:build {phase} --gaps-only` (requires Claude)
    After build → re-run review

  All BLOCKED → code bugs, user fixes first, then:
    Option A (single-CLI):  `/vg:review {phase} --retry-failed`
    Option B (cross-CLI, cheaper):
      `$vg-review {phase} --retry-failed --discovery-only`
      → `/vg:review {phase} --evaluate-only`
    (--retry-failed re-scans ONLY failed views, 5-10x faster)

  Mix →
    Step 1: `/vg:build {phase} --gaps-only`   ← build UNREACHABLE first
    Step 2: Fix code for BLOCKED (see list above)
    Step 3: `/vg:review {phase} --retry-failed`  ← re-scan BLOCKED views
```

**Route 6:** `RUNTIME-MAP.json` + `GOAL-COVERAGE-MATRIX.md` gate = PASS, no `*-SANDBOX-TEST.md`
→ Display:
```
Next: Test/Verify — choose mode:

A) Standard (Claude):  `/vg:test {phase}`
B) Codex verify:       `$vg-test {phase}`

Add `--full-scan` to disable snapshot pruning.
```

**Route 7:** `*-SANDBOX-TEST.md` exists, no `*-UAT.md` or UAT != complete
→ Display: "Next: `/vg:accept {phase}` (human UAT — requires Claude)"

**Route 8:** UAT complete, next phase in ROADMAP
→ Display: "Next phase: `/vg:scope {next_phase}`"

**Route 9:** All phases complete
→ Display: "All phases done. Run: `/gsd:complete-milestone`"

**Step 4: Show artifact checklist**
```
## VG Next — Phase {N}

Artifacts:
  {✓/✗} SPECS.md
  {✓/✗} CONTEXT.md
  {✓/✗} PLAN*.md + API-CONTRACTS.md
  {✓/✗} SUMMARY*.md
  {✓/✗} RUNTIME-MAP.json
  {✓/✗} GOAL-COVERAGE-MATRIX.md (gate: PASS/BLOCK)
  {✓/✗} *-SANDBOX-TEST.md
  {✓/✗} *-UAT.md

→ [Next command as determined above]
```

</process>
