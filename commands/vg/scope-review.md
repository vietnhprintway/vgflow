---
name: vg:scope-review
description: Cross-phase scope validation — detect conflicts, overlaps, and gaps across all scoped phases
argument-hint: "[--skip-crossai] [--phases=7.6,7.8,7.10]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
---

<rules>
1. **VG-native** — no GSD delegation. This command is self-contained.
2. **Config-driven** — read .claude/vg.config.md for project paths, profile, models.
3. **Run AFTER scoping, BEFORE blueprint** — this is a cross-phase gate between scope and blueprint.
4. **Automated checks first** — 5 deterministic checks run before any AI review.
5. **DISCUSSION-LOG.md is APPEND-ONLY** — never overwrite, never delete existing content.
6. **Resolution is interactive** — conflicts and gaps require user decision, not AI auto-fix.
7. **Minimum 2 phases** — warn (not block) if only 1 phase scoped.
</rules>

<objective>
Cross-phase scope validation gate. Run after scoping all (or multiple) phases, before starting blueprint on any of them.
Detects decision conflicts, module overlaps, endpoint collisions, dependency gaps, and scope creep across phases.

Output: .planning/SCOPE-REVIEW.md (report with gate verdict)

Pipeline position: specs -> scope -> **scope-review** -> blueprint -> build -> review -> test -> accept
</objective>

<process>

**Config:** Read .claude/commands/vg/_shared/config-loader.md first. Use config variables ($PLANNING_DIR, $PHASES_DIR).

<step name="0_parse_and_collect">
## Step 0: Parse arguments + collect phase data

```bash
# Parse arguments
SKIP_CROSSAI=false
PHASE_FILTER=""

for arg in $ARGUMENTS; do
  case "$arg" in
    --skip-crossai) SKIP_CROSSAI=true ;;
    --phases=*) PHASE_FILTER="${arg#--phases=}" ;;
  esac
done
```

**Scan for scoped phases:**
```bash
SCOPED_PHASES=()
for dir in ${PHASES_DIR}/*/; do
  if [ -f "${dir}CONTEXT.md" ]; then
    PHASE_NAME=$(basename "$dir")
    # If --phases filter provided, only include matching phases
    if [ -n "$PHASE_FILTER" ]; then
      PHASE_NUM=$(echo "$PHASE_NAME" | grep -oE '^[0-9]+(\.[0-9]+)*')
      if echo ",$PHASE_FILTER," | grep -q ",${PHASE_NUM},"; then
        SCOPED_PHASES+=("$dir")
      fi
    else
      SCOPED_PHASES+=("$dir")
    fi
  fi
done
```

**Validate:**
- If 0 phases found -> BLOCK: "No phases with CONTEXT.md found. Run /vg:scope first."
- If 1 phase found -> WARN: "Only 1 phase scoped ({phase}). Cross-phase review works best with 2+ phases. Proceeding with single-phase structural check."

**Extract from each CONTEXT.md:**
For every scoped phase, parse and collect:
- **Decisions:** D-XX title, category, full text
- **Endpoints:** method + path + auth role + purpose (from decision Endpoints: sub-sections)
- **Module names:** inferred from endpoint paths (e.g., `/api/v1/sites` -> sites module) and UI component names
- **Test scenarios:** TS-XX descriptions
- **Dependencies:** any "Depends on Phase X" or "Requires output from Phase X" mentions
- **Files/directories likely touched:** inferred from module names + `config.code_patterns` paths

Store all extracted data in a structured format for cross-referencing in Step 1.

**Also check for DONE phases:**
Scan for phases with completed PIPELINE-STATE.json (`steps.accept.status = "done"`) or existing UAT.md. These are "shipped" phases — used for scope creep detection (Check E).
</step>

<step name="1_cross_reference">
## Step 1: CROSS-REFERENCE (automated, fast)

Run 5 deterministic checks. No AI reasoning — pure string matching and comparison.

### Check A — DECISION CONFLICTS

Compare decisions across phases. Look for:
- Same technology mentioned with different approaches (e.g., Phase 7.6 says "Redis caching", Phase 7.8 says "in-memory caching")
- Same module/service with conflicting architecture (e.g., Phase 7.6 says "monolith handler", Phase 7.8 says "microservice")
- Contradictory business rules (e.g., Phase 7.6 says "admin-only", Phase 7.8 says "public access" for same resource)

For each pair of phases, compare decision text for keyword overlap + contradiction signals.

**Output format:**
```
Check A — Decision Conflicts: {N found | CLEAN}
```
If found, collect: `{ id: "C-XX", phase_a, phase_b, decision_a, decision_b, issue, recommendation }`

### Check B — MODULE OVERLAP

Two or more phases modify the same file or module directory. Compare:
- Endpoint paths: same `/api/v1/{module}/` prefix in 2+ phases
- UI component names: same component name in 2+ phases
- Inferred directories: same `apps/api/src/modules/{name}` or `apps/web/src/pages/{name}`

This is not always a problem (phases can extend the same module), but must be flagged for review.

**Output format:**
```
Check B — Module Overlap: {N found | CLEAN}
```
If found, collect: `{ id: "O-XX", phases: [], shared_resource, recommendation }`

### Check C — ENDPOINT COLLISION

Same HTTP method + path defined in 2 different phases. This is always a conflict.

Compare all extracted endpoints: `${METHOD} ${PATH}` pairs across phases.

**Output format:**
```
Check C — Endpoint Collision: {N found | CLEAN}
```
If found, collect: `{ id: "EC-XX", phase_a, phase_b, method, path, recommendation }`

### Check D — DEPENDENCY GAPS

Phase A assumes output from Phase B, but Phase B's CONTEXT.md doesn't define that output.
Or: Phase A references a module/service that no phase creates.

Check:
- Explicit dependencies ("Depends on Phase X" in CONTEXT.md)
- Implicit dependencies (Phase A endpoint references a collection/service that only Phase B creates)

**Output format:**
```
Check D — Dependency Gaps: {N found | CLEAN}
```
If found, collect: `{ id: "DG-XX", phase, missing_dependency, recommendation }`

### Check E — SCOPE CREEP

Decisions in scoped phases overlap with already-DONE phases.
Compare decision endpoints and module names against shipped phases.

Check:
- Endpoint in a new phase already exists in a DONE phase (re-implementation risk)
- UI component in a new phase duplicates one from a DONE phase
- Business rule contradicts a shipped decision

**Output format:**
```
Check E — Scope Creep: {N found | CLEAN}
```
If found, collect: `{ id: "SC-XX", new_phase, done_phase, overlap, recommendation }`

### Summary after all checks:
```
Cross-Reference Results:
  Check A (decision conflicts):  {N} found
  Check B (module overlap):      {N} found
  Check C (endpoint collision):  {N} found
  Check D (dependency gaps):     {N} found
  Check E (scope creep):         {N} found
  Total issues: {sum}
```
</step>

<step name="2_crossai_review">
## Step 2: CROSSAI REVIEW (config-driven)

**Skip if:** `$SKIP_CROSSAI` flag is set, OR `config.crossai_clis` is empty, OR only 1 phase scoped.

Prepare context file at `${VG_TMP}/vg-crossai-scope-review.md`:

```markdown
# CrossAI Cross-Phase Scope Review

Review these {N} phase scopes for conflicts, overlaps, gaps, and inconsistencies.

## Focus Areas
1. Architectural consistency across phases
2. Data model evolution (does Phase B's schema break Phase A's assumptions?)
3. Auth model consistency (same role, same permissions across phases?)
4. Integration points (do phases that must connect actually define compatible interfaces?)
5. Ordering risks (does Phase B NEED Phase A to ship first? Is that captured?)

## Verdict Rules
- pass: no critical conflicts, all integration points compatible
- flag: minor inconsistencies that are manageable
- block: critical conflict or missing dependency that will cause build failure

## Phase Artifacts
---
{For each scoped phase: include full CONTEXT.md content, separated by phase headers}
---
```

Set `$CONTEXT_FILE`, `$OUTPUT_DIR="${PLANNING_DIR}/crossai"`, `$LABEL="scope-review"`.
Read and follow `.claude/commands/vg/_shared/crossai-invoke.md`.

Collect CrossAI findings into the report.
</step>

<step name="3_write_report">
## Step 3: WRITE REPORT

Write to `${PLANNING_DIR}/SCOPE-REVIEW.md`:

```markdown
# Scope Review — {ISO date}

Phases reviewed: {phase list with names}
Total decisions across phases: {N}
Total endpoints across phases: {N}

## Conflicts (MUST RESOLVE)

| ID | Phase A | Phase B | Issue | Recommendation |
|----|---------|---------|-------|----------------|
| C-01 | {phase} D-{XX} | {phase} D-{XX} | {description} | {recommendation} |

{If no conflicts: "No decision conflicts found."}

## Endpoint Collisions (MUST RESOLVE)

| ID | Phase A | Phase B | Endpoint | Recommendation |
|----|---------|---------|----------|----------------|
| EC-01 | {phase} | {phase} | {METHOD /path} | {recommendation} |

{If no collisions: "No endpoint collisions found."}

## Overlaps (REVIEW)

| ID | Phases | Shared Resource | Recommendation |
|----|--------|-----------------|----------------|
| O-01 | {phases} | {module/file/component} | {recommendation} |

{If no overlaps: "No module overlaps found."}

## Dependency Gaps (MUST FILL)

| ID | Phase | Missing Dependency | Recommendation |
|----|-------|--------------------|----------------|
| DG-01 | {phase} | {what's missing} | {recommendation} |

{If no gaps: "No dependency gaps found."}

## Scope Creep (REVIEW)

| ID | New Phase | Done Phase | Overlap | Recommendation |
|----|-----------|------------|---------|----------------|
| SC-01 | {phase} | {done_phase} | {description} | {recommendation} |

{If no creep: "No scope creep detected."}

## CrossAI Findings

{CrossAI consensus results, or "Skipped (--skip-crossai or no CLIs configured)"}

## Gate

**Status: {PASS | BLOCK}**

Criteria:
- Conflicts (Check A): {N} — {MUST be 0 for PASS}
- Endpoint Collisions (Check C): {N} — {MUST be 0 for PASS}
- Dependency Gaps (Check D): {N} — {MUST be 0 for PASS}
- Overlaps (Check B): {N} — {reviewed, may be intentional}
- Scope Creep (Check E): {N} — {reviewed, may be intentional}
- CrossAI: {verdict} — {block verdicts count toward BLOCK}

**Verdict: {PASS — ready for blueprint | BLOCK — resolve {N} issues first}**
```

**Gate logic:**
- PASS if: 0 conflicts (A) + 0 endpoint collisions (C) + 0 dependency gaps (D) + CrossAI not "block"
- BLOCK if: any conflict OR any collision OR any dependency gap OR CrossAI "block"
- Overlaps (B) and Scope Creep (E) are informational — do not block, but must be reviewed
</step>

<step name="4_resolution">
## Step 4: RESOLUTION (if BLOCK)

If gate status is BLOCK, for each blocking issue:

```
AskUserQuestion:
  header: "Resolve: {issue_id} — {short description}"
  question: |
    **Issue:** {full description}
    **Phase A:** {phase} — {decision}
    **Phase B:** {phase} — {decision}
    **Recommendation:** {AI recommendation}

    How to resolve?
  options:
    - "Update Phase A scope — will need /vg:scope {phase_a} to re-discuss"
    - "Update Phase B scope — will need /vg:scope {phase_b} to re-discuss"
    - "Add dependency — update ROADMAP.md with ordering constraint"
    - "Accept as-is — mark as acknowledged risk"
```

Track resolutions:
- "Update Phase X" -> note which phases need re-scoping, suggest commands at end
- "Add dependency" -> append dependency note to ROADMAP.md (if exists)
- "Accept as-is" -> mark issue as "acknowledged" in SCOPE-REVIEW.md, downgrade from BLOCK

**After all resolutions:**
Re-evaluate gate. If all blocking issues resolved (updated scope or acknowledged):
- Update SCOPE-REVIEW.md gate status to PASS (with "acknowledged" notes)
- If any phases need re-scoping, do NOT auto-pass — list them:
  ```
  Gate conditionally PASS. Phases requiring re-scope:
    - /vg:scope {phase_a} (conflict C-01)
    - /vg:scope {phase_b} (gap DG-02)

  After re-scoping, run /vg:scope-review again to verify.
  ```
</step>

<step name="5_commit_and_next">
## Step 5: Commit + suggest next

```bash
git add "${PLANNING_DIR}/SCOPE-REVIEW.md"
git commit -m "scope-review: ${#SCOPED_PHASES[@]} phases — ${GATE_VERDICT}"
```

**Display:**
```
Scope Review Complete.
  Phases: {N} reviewed
  Conflicts: {N} | Collisions: {N} | Overlaps: {N} | Gaps: {N} | Creep: {N}
  CrossAI: {verdict | skipped}
  Gate: {PASS | BLOCK}
```

**If PASS:**
```
  Ready for blueprint. Start with:
    /vg:blueprint {first-unblueprinted-phase}
```

**If BLOCK (still unresolved):**
```
  Resolve blocking issues before proceeding to blueprint.
  Re-run: /vg:scope-review after fixes.
```

**If conditional PASS (acknowledged risks):**
```
  Proceeding with acknowledged risks.
  {N} issues marked as accepted. See SCOPE-REVIEW.md for details.
  
  Next: /vg:blueprint {first-unblueprinted-phase}
```
</step>

</process>

<success_criteria>
- All phases with CONTEXT.md collected and parsed
- 5 automated cross-reference checks executed (A through E)
- CrossAI review ran (or skipped if flagged/no CLIs/single phase)
- SCOPE-REVIEW.md written with structured report + gate verdict
- All blocking issues presented to user with resolution options
- Gate resolves to PASS (clean, conditional, or all-acknowledged) before suggesting blueprint
- Report committed to git
- Next step guidance shows /vg:blueprint for first unblueprinted phase
</success_criteria>
