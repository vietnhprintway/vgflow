---
name: "vg-progress"
description: "Show detailed pipeline progress across all phases — artifact status, current step, next action"
metadata:
  short-description: "Pipeline progress dashboard — artifact status per phase"
---

<codex_skill_adapter>
## A. Skill Invocation
- This skill is invoked by mentioning `$vg-progress`.
- Treat all user text after `$vg-progress` as arguments: `[phase] [--all]`
- No phase = show current phase + overview of all phases.

## B. AskUserQuestion → request_user_input Mapping
GSD workflows use `AskUserQuestion`. Translate to Codex `request_user_input`:
- AskUserQuestion(question="X") → request_user_input(prompt="X")

## C. No browser needed
This skill only reads files — no Playwright required.
</codex_skill_adapter>

<rules>
1. **Read-only** — no writes, no mutations, no browser.
2. **Zero hardcode** — all paths from config.
3. **Prefer PIPELINE-STATE.json** — more accurate than artifact detection.
4. **Don't auto-invoke** — suggest next action, don't run it.
</rules>

<objective>
Show detailed progress dashboard for the VG pipeline.

Pipeline steps: specs → scope → blueprint → build → review → test → accept
</objective>

<process>

## Step 0: Config Loading

Read `.claude/vg.config.md` — parse YAML frontmatter.
Extract: `paths.planning`, `paths.phases`, `profile`.

```
PLANNING_DIR = config.paths.planning   # e.g., .planning
PHASES_DIR   = config.paths.phases     # e.g., .planning/phases
PROFILE      = config.profile          # e.g., web-fullstack
```

Display `Profile: {PROFILE}` at top of output. Profile gates which steps apply per command.

## Step 1: Scan Phase Directories

```
List all directories in ${PHASES_DIR}/

For each phase_dir:
  phase_number = extract from dir name (e.g., "07.6-publisher-polish" → "7.6")
  phase_name   = extract from dir name (e.g., "publisher-polish")

  Check artifacts:
    specs      = exists ${phase_dir}/SPECS.md
    context    = exists ${phase_dir}/CONTEXT.md
    plan       = count ${phase_dir}/*-PLAN*.md OR ${phase_dir}/PLAN*.md
    contracts  = exists ${phase_dir}/API-CONTRACTS.md
    test_goals = exists ${phase_dir}/TEST-GOALS.md
    summary    = count ${phase_dir}/*-SUMMARY*.md OR ${phase_dir}/SUMMARY*.md
    runtime    = exists ${phase_dir}/RUNTIME-MAP.json
    sandbox    = exists ${phase_dir}/*-SANDBOX-TEST.md
    uat        = exists ${phase_dir}/*-UAT.md
    goal_matrix = exists ${phase_dir}/GOAL-COVERAGE-MATRIX.md
    scan_files  = count ${phase_dir}/scan-*.json
    probe_files = count ${phase_dir}/probe-*.json
    crossai     = count ${phase_dir}/crossai/*.xml
    pipeline_state = read ${phase_dir}/PIPELINE-STATE.json (if exists)
    step_markers = count ${phase_dir}/.step-markers/*.done
    callers     = read ${phase_dir}/.callers.json (if exists) — extract affected_callers count

  Determine current step:
    IF pipeline_state exists:
      Find first step with status != "done" and status != "skipped"
    ELSE (artifact fallback):
      IF no specs     → step 0
      IF no context   → step 1
      IF no plan      → step 2
      IF no summary   → step 3
      IF no runtime   → step 4
      IF no sandbox   → step 5
      IF no uat       → step 6
      ELSE            → step 7 (done)
```

## Step 2: Identify Active Phase

Read `${PLANNING_DIR}/STATE.md` for `current_phase`.
If missing → active phase = first phase with step < 7.

## Step 3: Display Overview

```
## VG Pipeline Progress

### Per-phase blocks (one block per phase, top-down by phase number)

For EACH phase, render this block:

```
────────────────────────────────────────────────────────────────
Phase {N}: {name}   [{step}/7]   {status_label}

Pipeline: {s0} specs → {s1} scope → {s2} blueprint → {s3} build → {s4} review → {s5} test → {s6} accept

Markers: {step_markers_done}/{step_markers_expected_for_profile}
Callers tracked: {callers_count} (from .callers.json, blank if none)
Next: {next_command_or_dash}
────────────────────────────────────────────────────────────────
```

**Status icon per step:**

| Step | Icon logic |
|------|-----------|
| 0 (specs)     | ✅ if SPECS.md exists, ⬜ otherwise |
| 1 (scope)     | ✅ if CONTEXT.md exists, 🔄 if SPECS only, ⬜ if none |
| 2 (blueprint) | ✅ if PLAN*.md + API-CONTRACTS.md, 🔄 partial, ⬜ none |
| 3 (build)     | ✅ if SUMMARY*.md exists, ⬜ otherwise |
| 4 (review)    | ✅ if RUNTIME-MAP + gate=PASS, 🔄 if gate=BLOCK, ❌ if FAILED, ⬜ if missing |
| 5 (test)      | ✅ if SANDBOX-TEST verdict=PASSED, 🔄 GAPS_FOUND, ❌ FAILED, ⬜ missing |
| 6 (accept)    | ✅ if UAT verdict=ACCEPTED, ⬜ otherwise |

**status_label:** `✅ DONE` | `🔄 IN PROGRESS` | `⏸ NOT STARTED` | `❌ BLOCKED`

**next_command:** use Step 5 mapping table.

- Print TOP-DOWN by phase number
- Each phase = own visual block (NOT a table)
- Include ALL phases from ROADMAP.md

## Step 4: Display Active Phase Detail (ONLY when specific phase arg provided — else skip)

```
### Phase {N}: {name}

Pipeline: ✅ specs → ✅ scope → ✅ blueprint → ✅ build → 🔄 review → ⬜ test → ⬜ accept

#### Artifacts
| Step | Artifact | Status | Detail |
|------|----------|--------|--------|
| 1 | SPECS.md | ✅ | Created |
| 2 | CONTEXT.md | ✅ | {N} decisions |
| 3 | PLAN*.md | ✅ | {N} plans |
| 3 | API-CONTRACTS.md | ✅ | {N} endpoints |
| 3 | TEST-GOALS.md | ✅ | {N} goals |
| 4 | SUMMARY*.md | ✅ | {N} summaries |
| 5 | RUNTIME-MAP.json | 🔄 | {N} views, {M} elements |
| 5 | GOAL-COVERAGE-MATRIX.md | 🔄 | {ready}/{total} goals ready |
| 5 | scan-*.json | — | {N} scan results |
| 6 | SANDBOX-TEST.md | ⬜ | Not started |
| 7 | UAT.md | ⬜ | Not started |

#### CrossAI
- Results: {N} XML files in crossai/

#### Git Activity
- git log --oneline -5 -- {phase_dir}
```

Status icons: ✅ done | 🔄 in progress | ⬜ not started | ❌ blocked

## Step 5: Suggest Next Action

**ALWAYS use $vg-* or /vg:* commands. NEVER suggest /gsd-* or /gsd:* commands.**

**Step-to-command mapping (MANDATORY):**

| Current step (missing artifact) | Command to suggest |
|---|---|
| 0 (no SPECS.md) | `/vg:specs {phase}` |
| 1 (no CONTEXT.md) | `/vg:scope {phase}` |
| 2 (no PLAN*.md or API-CONTRACTS.md) | `/vg:blueprint {phase}` |
| 3 (no SUMMARY*.md) | `/vg:build {phase}` |
| 3b (goals UNREACHABLE after review) | `/vg:build {phase} --gaps-only` |
| 4 (no RUNTIME-MAP.json) | `$vg-review {phase}` or `/vg:review {phase}` |
| 4b (gate BLOCK, goals failed) | `$vg-next {phase}` — auto-classifies UNREACHABLE vs BLOCKED |
| 5 (no SANDBOX-TEST.md) | `$vg-test {phase}` or `/vg:test {phase}` |
| 5b (test gaps, deeper UAT) | `$vg-test {phase}` or `$vg-accept {phase}` |
| 6 (no UAT.md) | `$vg-accept {phase}` |
| 7 (UAT complete, next phase) | `/vg:scope {next_phase}` after `/vg:specs {next_phase}` |
| 7 (all phases done) | `/gsd:complete-milestone` (milestone wrap-up only) |

**Forbidden (do NOT emit):**
- ❌ `/gsd-plan-phase` → use `/vg:blueprint`
- ❌ `/gsd-verify-work` → use `$vg-test` or `$vg-accept`
- ❌ `/gsd-discuss-phase` → use `/vg:scope`
- ❌ `/gsd-execute-phase` → use `/vg:build`

**Output format:**

```
#### What's Next

▶ {command from table above} — {description}

Also available:
  $vg-next   — auto-detect + show next command
```

If argument = specific phase → detail for that phase only.
If argument = `--all` → detail for ALL phases.

</process>
