# Pipeline v4.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor VGFlow pipeline so `/vg:test-spec` owns full test artifact generation (8 docs + `.spec.ts` codegen + lens routing), `/vg:review` becomes discovery-only, and `/vg:test` absorbs fix-loop + matrix verdict. Keep claude + codex CLI mirror parity 100%. Release as v4.0.0.

**Architecture:** Single PR, breaking change semver. 3 source skills modified, 4 codex mirrors regenerated, chain order swap (`build → review → test-spec → test → accept`). Codegen subagent spawn moves from `/vg:test STEP 5` to `/vg:test-spec Step 4_codegen`. Fix-loop + matrix verdict relocate from `/vg:review` Phase 3+4 to `/vg:test` Step 3+5.

**Tech Stack:** Bash, Python 3 (`scripts/`), Playwright TypeScript (`tests/e2e/`), Claude commands (`.md` files in `commands/vg/`), Codex skill mirror (`codex-skills/`), `scripts/generate-codex-skills.sh`, `scripts/verify-codex-mirror-equivalence.py`.

**Design ref:** `docs/plans/2026-05-12-pipeline-v4-test-spec-codegen-design.md`

---

## Pre-flight

Before Task 1, confirm:
- Working tree clean (no uncommitted edits except this plan)
- On branch `main`
- Last commit: `eaa58ae` (design doc)
- Tests baseline: `bash tests/run-ci.sh` passes (capture output for diff)

---

### Task 1: Baseline audit + snapshot current state

**Files:**
- Create: `docs/plans/v4-baseline-snapshot.md` (gitignored, audit only)

**Step 1: Capture line counts**

```bash
wc -l commands/vg/{review,test-spec,test,phase}.md \
     commands/vg/_shared/review/fix-loop-and-goals.md \
     commands/vg/_shared/test/codegen/{delegation,overview}.md \
     > docs/plans/v4-baseline-snapshot.md
```

**Step 2: Capture current chain order**

```bash
grep -n "Phase execution:" commands/vg/phase.md >> docs/plans/v4-baseline-snapshot.md
grep -n "test-spec\|review\|test\|accept" commands/vg/phase.md | head -20 >> docs/plans/v4-baseline-snapshot.md
```

**Step 3: Run baseline CI**

```bash
bash scripts/verify-codex-mirror-equivalence.py 2>&1 | tee -a docs/plans/v4-baseline-snapshot.md
```

Expected: PASS (must be green before starting).

**Step 4: Commit snapshot**

```bash
git add docs/plans/v4-baseline-snapshot.md
git commit -m "chore(v4): capture baseline snapshot before pipeline refactor"
```

---

### Task 2: Add `/vg:test-spec` Step 4_codegen contract

**Files:**
- Modify: `commands/vg/test-spec.md` (insert after Step 3.5 CrossAI sweep block, around line 420)

**Step 1: Read current frontmatter must_write block**

```bash
sed -n '1,40p' commands/vg/test-spec.md
```

Note: current marker list ends at `3_validate_deep_specs` + `3_crossai_sweep` + `4_complete` (line 34-37).

**Step 2: Update frontmatter markers**

Edit `commands/vg/test-spec.md` line ~34 — replace marker list:

```yaml
markers:
  - "1_load_context"
  - "2_gen_docs"
  - "3_validate_deep_specs"
  - "3_crossai_sweep"
  - "4_codegen"         # NEW
  - "4_self_review"     # NEW
  - "5_complete"        # renamed from 4_complete
```

**Step 3: Update must_write contract**

Add entries to `must_write:` block at line 13:

```yaml
must_write:
  # existing 8 docs preserved
  - path: "tests/e2e/lifecycle/"
    min_files: 1
    pattern: "*.spec.ts"
  - path: "${PHASE_DIR}/CODEGEN-MANIFEST.json"
    min_bytes: 100
```

**Step 4: Smoke check frontmatter parse**

```bash
python3 -c "import yaml; yaml.safe_load(open('commands/vg/test-spec.md').read().split('---')[1])"
```

Expected: no exception.

**Step 5: Commit**

```bash
git add commands/vg/test-spec.md
git commit -m "feat(test-spec): add 4_codegen + 4_self_review markers and must_write entries"
```

---

### Task 3: Add `/vg:test-spec` Step 4_codegen body

**Files:**
- Modify: `commands/vg/test-spec.md` (insert new step section after line ~422 CrossAI close block)

**Step 1: Insert Step 4_codegen body**

After the CrossAI sweep section (after the line containing `Test-Spec is the ONLY post-build artifact phase without CrossAI semantic review.` block close, approx line 420), insert:

````markdown
## Step 4: codegen (`4_codegen`)

Spawn `vg-test-codegen` subagent to generate Playwright lifecycle specs per goal. Smart-routing applies lens set per `goal_type` from `GOAL-COVERAGE-MATRIX.json`.

**Smart-routing lens map:**

| `goal_type` | Lens set |
|---|---|
| `mutation` | `idor` + `mass-assignment` + `authz-negative` + `business-logic` |
| `read` | `authz` + `info-disclosure` + `tenant-boundary` |
| `auth` | `auth-jwt` + `csrf` + `duplicate-submit` |
| `default` | `business-coherence` + `input-injection` |

**Subagent invocation:**

Read `commands/vg/_shared/test/codegen/delegation.md` and `commands/vg/_shared/test/codegen/overview.md` (existing files, no change). Then:

```
Agent(
  subagent_type="vg-test-codegen",
  prompt=<from delegation.md template>,
  input={
    phase_dir: "${PHASE_DIR}",
    phase_number: "${PHASE_NUMBER}",
    phase_profile: "${PHASE_PROFILE}",
    runtime_map_path: "${PHASE_DIR}/RUNTIME-MAP.json",
    goal_coverage_matrix_path: "${PHASE_DIR}/GOAL-COVERAGE-MATRIX.json",
    generated_tests_dir: "tests/e2e/lifecycle/",
    lens_routing_map: <smart-routing map above>
  }
)
```

**Output contract:**
- `tests/e2e/lifecycle/G-XX.{lens}.spec.ts` — one file per goal × lens
- `${PHASE_DIR}/CODEGEN-MANIFEST.json` — list of generated files + their L1/L2 binding state

**Mark step:**
```bash
"${PYTHON_BIN:-python3}" "$ORCH" mark-step test-spec 4_codegen 2>/dev/null || true
```
````

**Step 2: Verify section present**

```bash
grep -n "## Step 4: codegen" commands/vg/test-spec.md
```

Expected: 1 line match.

**Step 3: Commit**

```bash
git add commands/vg/test-spec.md
git commit -m "feat(test-spec): add Step 4_codegen — spawn vg-test-codegen subagent with lens smart-routing"
```

---

### Task 4: Add `/vg:test-spec` Step 4.5 self-review

**Files:**
- Modify: `commands/vg/test-spec.md` (insert after Step 4_codegen block)

**Step 1: Insert Step 4.5 body**

````markdown
## Step 4.5: codegen self-review (`4_self_review`)

After codegen, verify generated `.spec.ts` files compile via `npx playwright --list`. Catch syntax errors before `/vg:test` Step 2 execute time.

**Run check:**

```bash
SELF_REVIEW_LOG="${PHASE_DIR}/.step-markers/test-spec/4_self_review.log"
mkdir -p "$(dirname "$SELF_REVIEW_LOG")"

RETRY=0
MAX_RETRY=2
while [ $RETRY -le $MAX_RETRY ]; do
  if npx playwright --list tests/e2e/lifecycle/ > "$SELF_REVIEW_LOG" 2>&1; then
    echo "✓ Codegen self-review PASS (retry=$RETRY)"
    break
  fi
  RETRY=$((RETRY + 1))
  if [ $RETRY -gt $MAX_RETRY ]; then
    echo "⛔ Codegen self-review FAIL after $MAX_RETRY retries — see $SELF_REVIEW_LOG"
    echo "Escalate to user. Manual fix or rollback codegen."
    exit 1
  fi
  echo "⚠ Self-review FAIL (retry=$RETRY) — re-running codegen subagent"
  # Re-spawn vg-test-codegen with prior output context
done

"${PYTHON_BIN:-python3}" "$ORCH" mark-step test-spec 4_self_review 2>/dev/null || true
```
````

**Step 2: Verify**

```bash
grep -n "## Step 4.5: codegen self-review" commands/vg/test-spec.md
```

Expected: 1 match.

**Step 3: Commit**

```bash
git add commands/vg/test-spec.md
git commit -m "feat(test-spec): add Step 4.5 self-review — npx playwright --list with retry × 2"
```

---

### Task 5: Move fix-loop shared file from review to test path

**Files:**
- Move: `commands/vg/_shared/review/fix-loop-and-goals.md` → `commands/vg/_shared/test/fix-loop-and-verdict.md`

**Step 1: Move file**

```bash
mkdir -p commands/vg/_shared/test/
git mv commands/vg/_shared/review/fix-loop-and-goals.md commands/vg/_shared/test/fix-loop-and-verdict.md
```

**Step 2: Update internal refs in moved file**

```bash
grep -n "review/fix-loop\|phase3_fix_loop\|phase4_goal_comparison" commands/vg/_shared/test/fix-loop-and-verdict.md
```

For each match, replace step naming:
- `phase3_fix_loop` → `step3_fix_loop`
- `phase4_goal_comparison` → `step5_matrix_verdict`
- `Phase 3 — FIX LOOP` → `Step 3 — FIX LOOP (post-test execute)`
- `Phase 4 — GOAL COMPARISON` → `Step 5 — MATRIX VERDICT`

Use:
```bash
sed -i.bak 's/phase3_fix_loop/step3_fix_loop/g; s/phase4_goal_comparison/step5_matrix_verdict/g' \
  commands/vg/_shared/test/fix-loop-and-verdict.md
sed -i.bak 's/Phase 3 — FIX LOOP/Step 3 — FIX LOOP (post-test execute)/g; s/Phase 4 — GOAL COMPARISON/Step 5 — MATRIX VERDICT/g' \
  commands/vg/_shared/test/fix-loop-and-verdict.md
rm commands/vg/_shared/test/fix-loop-and-verdict.md.bak
```

**Step 3: Verify renames complete**

```bash
grep -n "phase3_fix_loop\|phase4_goal_comparison" commands/vg/_shared/test/fix-loop-and-verdict.md
```

Expected: 0 matches.

**Step 4: Commit**

```bash
git add commands/vg/_shared/test/fix-loop-and-verdict.md
git rm commands/vg/_shared/review/fix-loop-and-goals.md
git commit -m "refactor(v4): move fix-loop-and-goals from review/ to test/ — rename steps"
```

---

### Task 6: Strip review Phase 3 + Phase 4 references

**Files:**
- Modify: `commands/vg/review.md` (lines 160, 317, 448, 455, 521-524, 538)

**Step 1: Update review description**

Line 3:
```yaml
description: Post-build review — code scan + browser discovery → RUNTIME-MAP (discovery-only)
```

(Strip "+ fix loop + goal comparison")

**Step 2: Update review markers**

Line ~160 — remove `phase3_fix_loop` marker entry. Keep `phase1_*`, `phase2_*`, `phase2.5_matrix_intent` (new).

**Step 3: Update review body fix-loop section**

Lines 521-524 — replace:

```markdown
### Fix loop + goal comparison (extracted v2.70.0 T8 — largest section)

Read `_shared/review/fix-loop-and-goals.md` and follow it exactly.
Includes 2 steps: phase3_fix_loop (max 5 iterations), phase4_goal_comparison.
```

With:

```markdown
### Matrix INTENT (discovery-only, v4.0)

Compute 3-verdict intent: `READY` / `BLOCKED` / `NOT_SCANNED`. Fix-loop + final verdict deferred to `/vg:test` (Step 3 + Step 5).

Read `_shared/review/matrix-intent.md` (created in Task 7).
```

**Step 4: Update auto-chain target**

Find auto-chain block (search for `next_command`):

```bash
grep -n "next_command\|auto-chain" commands/vg/review.md | head
```

Replace next_command from `/vg:test` → `/vg:test-spec`.

**Step 5: Verify review body coherent**

```bash
grep -n "fix-loop\|phase3\|phase4\|goal comparison" commands/vg/review.md
```

Expected: 0 matches (or only inside historical comments — review case-by-case).

**Step 6: Commit**

```bash
git add commands/vg/review.md
git commit -m "feat(review): discovery-only scope — strip Phase 3 fix-loop + Phase 4 verdict refs, auto-chain → test-spec"
```

---

### Task 7: Create matrix INTENT shared file

**Files:**
- Create: `commands/vg/_shared/review/matrix-intent.md`

**Step 1: Write matrix intent body**

```markdown
# Matrix INTENT (review discovery-only)

Compute 3-verdict intent per goal in `GOAL-COVERAGE-MATRIX.json`:

- `READY` — goal has L1/L2 selector bindings + endpoint observed in RUNTIME-MAP
- `BLOCKED` — goal endpoint missing OR selectors unresolved
- `NOT_SCANNED` — goal not exercised during browser discovery

**No TEST_PENDING here.** That verdict is computed by `/vg:test` Step 5 (after actual playwright execute).

## Algorithm

```python
for goal in goals:
    if goal.endpoint_observed and goal.selectors_resolved:
        verdict = "READY"
    elif not goal.endpoint_observed:
        verdict = "BLOCKED"
    else:
        verdict = "NOT_SCANNED"
```

## Output

Write `MATRIX-INTENT.json` to phase dir:

```json
{
  "phase": "${PHASE_NUMBER}",
  "computed_at": "<ISO timestamp>",
  "goals": [
    {"goal_id": "G-01", "verdict": "READY", "reason": "endpoint + selectors OK"},
    {"goal_id": "G-02", "verdict": "BLOCKED", "reason": "endpoint /api/refund missing in RUNTIME-MAP"}
  ]
}
```

## Mark step

```bash
"${PYTHON_BIN:-python3}" "$ORCH" mark-step review phase2.5_matrix_intent 2>/dev/null || true
```
```

**Step 2: Commit**

```bash
git add commands/vg/_shared/review/matrix-intent.md
git commit -m "feat(review): add matrix-intent.md — 3-verdict discovery-only computation"
```

---

### Task 8: Strip `/vg:test` STEP 5 codegen

**Files:**
- Modify: `commands/vg/test.md` (lines 52-62, 161, 177, 216, 228, 231-232, 240-298, 305)

**Step 1: Update test description**

Line 3:
```yaml
description: Execute Playwright tests + fix-loop + matrix verdict + security audit (codegen moved to /vg:test-spec)
```

**Step 2: Remove codegen markers from frontmatter**

Lines 52-62 — remove:
```yaml
- name: "5d_codegen"
- name: "5d_mobile_codegen"
```

Keep `4_goal_verification` and below.

**Step 3: Renumber STEP 5 → STEP 5 (verdict), strip codegen body**

Find line 279 (`### STEP 5 — codegen`). Delete entire STEP 5 codegen section (lines 279-302 approx — ends before `### STEP 6 — fix loop`).

Renumber:
- Old STEP 5 (codegen) → DELETED
- Old STEP 6 (fix loop) → NEW STEP 3 (fix-loop, moved)
- Old STEP 7 (regression + security) → STEP 4 (security regression)
- Old STEP 8 (close) → STEP 6 (close)

**Step 4: Replace STEP 3 (was STEP 6) fix-loop body**

Old:
```markdown
### STEP 6 — fix loop + auto escalate
```

New:
```markdown
### STEP 3 — fix loop + user-confirm gate

Read `_shared/test/fix-loop-and-verdict.md` and follow it exactly.

**User-confirm gate (v4.0 NEW):**

Before spawning fix subagent, compute `failing_goals` from playwright JSON output. If `failing_goals > 0`:

```
AskUserQuestion:
  A) Auto-fix (spawn vg-test-fixer subagent)
  B) Manual fix (block, wait for user)
  C) Skip fix-loop, emit debt
```

On A: spawn `vg-test-fixer`. On B: write `${PHASE_DIR}/FIX-LOOP-BLOCKED.md` + exit. On C: append to `KNOWN-ISSUES.md` + emit `--skip-fix-loop` debt.

Mark step:
```bash
"${PYTHON_BIN:-python3}" "$ORCH" mark-step test step3_fix_loop 2>/dev/null || true
```
```

**Step 5: Add new STEP 5 matrix verdict**

After STEP 4 (security regression), before STEP 6 (close), insert:

```markdown
### STEP 5 — matrix verdict

Compute final per-goal verdict (4-state): `READY` / `BLOCKED` / `TEST_PENDING` / `NOT_SCANNED`.

Read `_shared/test/fix-loop-and-verdict.md` Step 5 section.

Output: `${PHASE_DIR}/MATRIX-VERDICT.json` + flip `PIPELINE-STATE.json.next_command` → `/vg:accept`.

Mark step:
```bash
"${PYTHON_BIN:-python3}" "$ORCH" mark-step test step5_matrix_verdict 2>/dev/null || true
```
```

**Step 6: Verify no codegen refs remain**

```bash
grep -n "vg-test-codegen\|STEP 5 — codegen\|5d_codegen" commands/vg/test.md
```

Expected: 0 matches.

**Step 7: Commit**

```bash
git add commands/vg/test.md
git commit -m "feat(test): strip STEP 5 codegen, add STEP 3 fix-loop (user-confirm) + STEP 5 matrix verdict"
```

---

### Task 9: Create `vg-test-fixer` subagent definition

**Files:**
- Create: `agents/vg-test-fixer/SKILL.md`
- Create: `.claude/agents/vg-test-fixer/SKILL.md` (mirror)

**Step 1: Write agent definition**

```markdown
---
name: vg-test-fixer
description: Fix failing Playwright tests based on test output + RUNTIME-MAP. Spawned by /vg:test STEP 3 fix-loop on user-confirm. Returns JSON envelope.
tools: [Read, Write, Edit, Bash, Glob, Grep]
model: sonnet
---

# vg-test-fixer

## Input contract

- `phase_dir` — phase directory
- `failing_goals` — list of goal IDs that failed playwright execute
- `test_output_path` — TEST-RESULTS.json from STEP 2
- `runtime_map_path` — RUNTIME-MAP.json from /vg:review
- `lifecycle_dir` — tests/e2e/lifecycle/

## Output contract

JSON envelope:
```json
{
  "fixed_goals": ["G-01", "G-03"],
  "unfixed_goals": ["G-05"],
  "files_modified": ["src/api/refund.ts", "tests/e2e/lifecycle/G-05.idor.spec.ts"],
  "retry_count": 2,
  "escalate": false
}
```

## HARD-GATE

- Max 3 retry per goal (enforced internally)
- Cannot spawn nested subagents
- Cannot edit files outside `tests/e2e/lifecycle/` + `src/`
- Must commit fixes per goal (1 commit per goal fix)
```

**Step 2: Mirror to .claude/agents/**

```bash
mkdir -p .claude/agents/vg-test-fixer/
cp agents/vg-test-fixer/SKILL.md .claude/agents/vg-test-fixer/SKILL.md
```

**Step 3: Commit**

```bash
git add agents/vg-test-fixer/SKILL.md .claude/agents/vg-test-fixer/SKILL.md
git commit -m "feat(agents): add vg-test-fixer subagent — fix failing tests with max 3 retry"
```

---

### Task 10: Update `/vg:phase` chain order

**Files:**
- Modify: `commands/vg/phase.md` (lines 30, 205-211, 218)

**Step 1: Update phase execution doc line**

Line 30:
```markdown
Phase execution:  /vg:blueprint → /vg:build → /vg:review → /vg:test-spec → /vg:test → /vg:accept
```

(Swap order: review BEFORE test-spec.)

**Step 2: Update phase progression table**

Lines 205-211 — reorder:

```markdown
| 1 | scope | `/vg:scope {phase}` | TASK_SCOPE | CONTEXT.md |
| 2 | blueprint | `/vg:blueprint {phase}` | TASK_BLUEPRINT | PLAN*.md + API-CONTRACTS.md |
| 3 | build | `/vg:build {phase}` | TASK_BUILD | SUMMARY*.md |
| 4 | review | `/vg:review {phase}` | TASK_REVIEW | RUNTIME-MAP.json + MATRIX-INTENT.json |
| 5 | test-spec | `/vg:test-spec {phase}` | TASK_TEST_SPEC | DEEP-TEST-SPECS.md + tests/e2e/lifecycle/*.spec.ts |
| 6 | test | `/vg:test {phase}` | TASK_TEST | MATRIX-VERDICT.json with verdict != FAILED |
| 7 | accept | `/vg:accept {phase}` | TASK_ACCEPT | *-UAT.md with status "complete" |
```

**Step 3: Update skip-review user prompt**

Line 218:
```markdown
- question: "Phase scope nhỏ (1-2 files). Recommend bỏ qua /vg:review → chạy: specs → scope → blueprint → build → test-spec → test → accept. Bỏ qua review nghĩa test-spec không có RUNTIME-MAP, codegen sẽ dựa trên contracts tĩnh. Approve skip?"
```

**Step 4: Add `--skip-test` + `--skip-codegen` flag handling**

After the skip-review block, insert similar `--skip-test` block:

```markdown
- flag: "--skip-test"
- question: "Skip /vg:test? Pipeline dừng sau test-spec, UAT thủ công. Approve?"
- effect: "Bỏ stage 6, đi thẳng từ test-spec → accept"

- flag: "--skip-codegen"
- question: "Skip codegen ở test-spec? Chỉ gen 8 docs, không gen .spec.ts. Approve?"
- effect: "test-spec Step 4_codegen + 4.5 self-review SKIPPED"
```

**Step 5: Verify chain doc parse**

```bash
grep -n "/vg:review\|/vg:test-spec\|/vg:test " commands/vg/phase.md | head
```

Expected: order matches new sequence.

**Step 6: Commit**

```bash
git add commands/vg/phase.md
git commit -m "feat(phase): v4.0 chain order — review BEFORE test-spec, add --skip-test + --skip-codegen flags"
```

---

### Task 11: Regenerate codex skill mirrors

**Files:**
- Modify (auto-gen): `codex-skills/vg-review/SKILL.md`, `codex-skills/vg-test-spec/SKILL.md`, `codex-skills/vg-test/SKILL.md`, `codex-skills/vg-phase/SKILL.md`

**Step 1: Run generator**

```bash
bash scripts/generate-codex-skills.sh --force --skill=vg-review --skill=vg-test-spec --skill=vg-test --skill=vg-phase
```

**Step 2: Verify all 4 mirrors regenerated**

```bash
git status codex-skills/vg-{review,test-spec,test,phase}/SKILL.md
```

Expected: 4 files modified.

**Step 3: Commit**

```bash
git add codex-skills/vg-{review,test-spec,test,phase}/SKILL.md
git commit -m "chore(codex): regen 4 skill mirrors for v4.0 pipeline order"
```

---

### Task 12: Run verify-mirror-equivalence gate

**Files:**
- (Read-only) `scripts/verify-codex-mirror-equivalence.py`

**Step 1: Run gate**

```bash
python3 scripts/verify-codex-mirror-equivalence.py 2>&1 | tee /tmp/v4-mirror-verify.log
```

Expected: PASS with all 4 affected skills green.

**Step 2: If FAIL — fix drift**

Read failure section in log. Common causes:
- New flag not in codex SKILL.md → manually add to codex skill OR re-run generator with `--force`
- Section name mismatch → check `commands/vg/*.md` heading vs generator extraction logic

**Step 3: Re-run until PASS**

Loop Step 1-2 until green.

**Step 4: Commit (if any fix-up needed)**

```bash
git add codex-skills/
git commit -m "fix(codex): resolve mirror equivalence drift for v4.0"
```

---

### Task 13: Smoke test — review discovery-only

**Files:**
- (Test fixture) `tests/fixtures/recursive-probe-smoke/`

**Step 1: Run review on fixture**

```bash
cd tests/fixtures/recursive-probe-smoke/
bash ../../../.claude/scripts/vg-runner.sh review --phase=1 --dry-run 2>&1 | tee /tmp/v4-review-smoke.log
cd -
```

**Step 2: Verify no fix-loop ran**

```bash
grep -E "phase3_fix_loop|fix loop|matrix verdict" /tmp/v4-review-smoke.log
```

Expected: 0 matches (review v4.0 doesn't do fix-loop).

**Step 3: Verify matrix INTENT produced**

```bash
grep -E "matrix INTENT|MATRIX-INTENT\.json|phase2.5_matrix_intent" /tmp/v4-review-smoke.log
```

Expected: ≥1 match.

**Step 4: Verify auto-chain target = test-spec**

```bash
grep -E "next_command.*test-spec" /tmp/v4-review-smoke.log
```

Expected: ≥1 match.

**Step 5: Commit (no code change — log only for posterity)**

(No commit — smoke test only.)

---

### Task 14: Smoke test — test-spec codegen + self-review

**Step 1: Run test-spec on fixture**

```bash
cd tests/fixtures/recursive-probe-smoke/
bash ../../../.claude/scripts/vg-runner.sh test-spec --phase=1 --dry-run 2>&1 | tee /tmp/v4-test-spec-smoke.log
cd -
```

**Step 2: Verify Step 4_codegen ran**

```bash
grep -E "4_codegen|vg-test-codegen|smart-routing" /tmp/v4-test-spec-smoke.log
```

Expected: ≥1 match.

**Step 3: Verify Step 4.5 self-review ran**

```bash
grep -E "4_self_review|playwright --list" /tmp/v4-test-spec-smoke.log
```

Expected: ≥1 match.

**Step 4: Verify .spec.ts files generated (if dry-run produces actual files)**

```bash
ls tests/fixtures/recursive-probe-smoke/tests/e2e/lifecycle/ 2>/dev/null
```

Expected: ≥1 `.spec.ts` file (or "dry-run skipped" log entry).

---

### Task 15: Smoke test — test fix-loop user-confirm gate

**Step 1: Inject failing test fixture**

```bash
# Temporarily break a goal's selector to force failure
echo "// MOCK_FAIL_INJECT" >> tests/fixtures/recursive-probe-smoke/tests/e2e/lifecycle/G-01.base.spec.ts
```

**Step 2: Run test on fixture**

```bash
cd tests/fixtures/recursive-probe-smoke/
bash ../../../.claude/scripts/vg-runner.sh test --phase=1 --dry-run --auto-fix=skip 2>&1 | tee /tmp/v4-test-smoke.log
cd -
```

**Step 3: Verify fix-loop user prompt fired**

```bash
grep -E "AskUserQuestion|Auto-fix|Manual fix|Skip fix-loop" /tmp/v4-test-smoke.log
```

Expected: ≥1 match.

**Step 4: Verify matrix VERDICT produced**

```bash
grep -E "MATRIX-VERDICT\.json|step5_matrix_verdict" /tmp/v4-test-smoke.log
```

Expected: ≥1 match.

**Step 5: Revert injection**

```bash
git checkout tests/fixtures/recursive-probe-smoke/tests/e2e/lifecycle/G-01.base.spec.ts
```

---

### Task 16: Regression test — existing fixtures

**Step 1: Run full CI**

```bash
bash tests/run-ci.sh 2>&1 | tee /tmp/v4-ci.log
```

**Step 2: Diff against baseline**

```bash
diff docs/plans/v4-baseline-snapshot.md /tmp/v4-ci.log | head -50
```

Expected: only differences related to v4.0 changes (no regression in unrelated tests).

**Step 3: If regressions — pause + investigate**

Stop here, investigate, fix, re-run.

**Step 4: If green — record pass log**

```bash
cp /tmp/v4-ci.log docs/plans/v4-ci-passed.log
# (Not committed — local only.)
```

---

### Task 17: Bump VERSION + package.json to 4.0.0

**Files:**
- Modify: `VERSION` (single line)
- Modify: `package.json` (line 3 — `"version": "3.7.2"` → `"version": "4.0.0"`)

**Step 1: Bump VERSION file**

```bash
echo "4.0.0" > VERSION
```

**Step 2: Bump package.json**

Edit `package.json` line 3:
```json
"version": "4.0.0",
```

**Step 3: Verify**

```bash
cat VERSION
grep '"version"' package.json
```

Expected:
```
4.0.0
  "version": "4.0.0",
```

**Step 4: Commit**

```bash
git add VERSION package.json
git commit -m "chore: bump version to 4.0.0 (breaking — pipeline v4 refactor)"
```

---

### Task 18: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md` (prepend new section)

**Step 1: Read current top of CHANGELOG**

```bash
head -20 CHANGELOG.md
```

**Step 2: Insert v4.0.0 section after header**

Insert after the title block (around line 7):

```markdown
## v4.0.0 — Pipeline refactor (BREAKING)

**Pipeline order change:**
- Old: `specs → scope → blueprint → build → test-spec → review → test → accept`
- New: `specs → scope → blueprint → build → review → test-spec → test → accept`

**Ownership moves:**
- `/vg:review` → discovery-only (browser nav + RUNTIME-MAP + matrix INTENT). Phase 3 fix-loop + Phase 4 matrix verdict REMOVED.
- `/vg:test-spec` → owns codegen. Spawns `vg-test-codegen` subagent (was in `/vg:test` STEP 5). Adds lens smart-routing per `goal_type` + Step 4.5 `npx playwright --list` self-review.
- `/vg:test` → owns fix-loop + matrix verdict (4-state final). Adds user-confirm gate before auto-fix (A: auto, B: manual, C: skip+debt).

**New flags:**
- `/vg:phase --skip-test` — stop after test-spec
- `/vg:phase --skip-codegen` — test-spec docs only, no .spec.ts

**New subagent:** `vg-test-fixer` — fix failing tests, max 3 retry per goal.

**File relocations:**
- `commands/vg/_shared/review/fix-loop-and-goals.md` → `commands/vg/_shared/test/fix-loop-and-verdict.md`
- `phase3_fix_loop` marker → `step3_fix_loop`
- `phase4_goal_comparison` marker → `step5_matrix_verdict`

**Codex parity:** 4 mirrors regenerated (vg-review, vg-test-spec, vg-test, vg-phase). Strict structural equivalence enforced.

**Rollback:** `git revert <v4.0.0-commit>` + run `scripts/generate-codex-skills.sh --force`.

**Migration impact:**
- In-flight phases pre-`build` → no impact
- In-flight phases at `review` (v3.7.2 logic) → finish with v3.7.2 logic 1 last time
- In-flight phases at `test` (v3.7.2 codegen) → finish with v3.7.2 logic 1 last time
- Next phase → uses v4.0 chain
```

**Step 3: Verify markdown valid**

```bash
head -50 CHANGELOG.md
```

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG entry for v4.0.0 pipeline refactor"
```

---

### Task 19: Final integration test — full chain on fixture

**Step 1: Run full `/vg:phase` dry chain**

```bash
cd tests/fixtures/recursive-probe-smoke/
bash ../../../.claude/scripts/vg-runner.sh phase --phase=1 --dry-run --no-chain 2>&1 | tee /tmp/v4-full-chain.log
cd -
```

**Step 2: Verify chain order**

```bash
grep -E "^▶ /vg:(scope|blueprint|build|review|test-spec|test|accept)" /tmp/v4-full-chain.log
```

Expected sequence:
```
▶ /vg:scope
▶ /vg:blueprint
▶ /vg:build
▶ /vg:review
▶ /vg:test-spec
▶ /vg:test
▶ /vg:accept
```

(Review BEFORE test-spec.)

**Step 3: Verify no v3.7.2 artifacts produced**

```bash
grep -E "phase3_fix_loop|phase4_goal_comparison" /tmp/v4-full-chain.log
```

Expected: 0 matches.

**Step 4: If FAIL — investigate, fix, repeat**

---

### Task 20: Tag release + push

**Step 1: Create release tag**

```bash
git tag -a v4.0.0 -m "VGFlow v4.0.0 — pipeline refactor (review-discovery + test-spec codegen + test fix-loop)"
```

**Step 2: Push commits**

```bash
git push origin main
```

**Step 3: Push tag**

```bash
git push origin v4.0.0
```

**Step 4: Verify on GitHub**

```bash
gh release view v4.0.0 2>&1 | head -10
```

If release auto-created from tag — done. Else:

```bash
gh release create v4.0.0 --title "VGFlow v4.0.0 — Pipeline Refactor" --notes-file <(awk '/^## v4.0.0/,/^## v3/{print}' CHANGELOG.md | head -n -1)
```

---

## Post-release verification

- [ ] Tag visible on github.com/vietdev99/vgflow/releases
- [ ] `npm view vgflow version` returns 4.0.0 (after npm publish if applicable)
- [ ] No open issues filed within 24h on the 4 affected commands
- [ ] Test on 1 real project (not fixture) — confirm chain order works end-to-end

---

## Rollback procedure (emergency only)

```bash
git revert v4.0.0..main
bash scripts/generate-codex-skills.sh --force
git push origin main
git tag -d v4.0.0
git push origin :refs/tags/v4.0.0
```

Then bump version back to 3.7.3 (post-revert patch).

---

## Notes for executor

- Each task = single commit. Don't batch.
- If any verify step fails, STOP. Don't proceed to next task.
- All paths absolute relative to repo root (`D:\Workspace\Messi\Code\vgflow-repo`).
- Codex mirror regeneration is auto via `generate-codex-skills.sh` — don't hand-edit `codex-skills/*/SKILL.md`.
- User-confirm gate in `/vg:test` Step 3 fix-loop is INTERACTIVE — tests must use `--auto-fix=skip` flag to bypass during smoke.
- The plan assumes existing `tests/fixtures/recursive-probe-smoke/` works as fixture. If broken, fix first OR use `tests/fixtures/eligibility-fail-rule-1/`.
