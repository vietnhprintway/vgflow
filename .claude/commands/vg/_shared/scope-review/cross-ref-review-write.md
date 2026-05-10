<!-- v2.74.0 T1-T3 extraction — verbatim step blocks from commands/vg/scope-review.md -->
<!-- Group: cross-ref-review-write | Steps: 1_cross_reference, 2_crossai_review, 3_write_report -->

<process>

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

**Mode:** {INCREMENTAL (tăng cường theo delta) | FULL (quét toàn bộ)}
{If incremental:}
📊 Incremental scan: {CHANGED_COUNT} phases changed since {BASELINE_TS}, {NEW_COUNT} new
   Scope this run: [{SCAN_LIST}]
   Skipped (unchanged — bỏ qua vì không đổi): {len(SKIPPED_SET)} phases
   {If REMOVED_COUNT>0:}Removed from disk (xoá khỏi đĩa): {REMOVED_LIST}

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

</process>
