---
name: "vg-accept"
description: "Human UAT acceptance — data-driven checklist generated from VG artifacts (SPECS, CONTEXT, TEST-GOALS, RIPPLE-ANALYSIS, PLAN design-refs)"
metadata:
  short-description: "Final acceptance — structured UAT over VG artifacts + phase sign-off"
---

<codex_skill_adapter>
## A. Skill Invocation
- This skill is invoked by mentioning `$vg-accept`.
- Treat all user text after `$vg-accept` as arguments: `{{PHASE}}`
- If no phase given, ask: "Which phase? (e.g., 7.6)"

## B. AskUserQuestion → request_user_input Mapping
The Claude version uses `AskUserQuestion`. In Codex, translate to `request_user_input`:
- AskUserQuestion(question="X", options=[...]) → request_user_input(prompt="X\n\n[options]")

## C. No browser needed
This skill only reads files + asks user questions — no Playwright required.

## D. No SlashCommand available
The Claude version runs entirely inline — no nested command delegation. Port 1:1.

## E. Python interpreter
Prefer `python3` → `python` → `py` in that order. Store resolved path in `$PYTHON_BIN`.
</codex_skill_adapter>

<rules>
1. **All pipeline artifacts required** — SPECS → CONTEXT → PLAN → API-CONTRACTS → TEST-GOALS → SUMMARY → RUNTIME-MAP (web profiles only) → GOAL-COVERAGE-MATRIX → SANDBOX-TEST. Missing = BLOCK.
2. **Step markers mandatory** — every profile-applicable step from build/review/test MUST have its `.step-markers/{step}.done` marker. Missing = BLOCK (silent skip detection).
3. **SANDBOX-TEST verdict gate** — must be `PASSED` or `GAPS_FOUND`. `FAILED` → BLOCK with redirect.
4. **UAT is data-driven** — every checklist item is GENERATED from VG artifacts (D-XX from CONTEXT, G-XX from TEST-GOALS, HIGH callers from RIPPLE-ANALYSIS, design-refs from PLAN). No hardcoded checks.
5. **No auto-accept** — every non-N/A item requires explicit user Pass/Fail/Skip.
6. **Ripple gate** — if RIPPLE-ANALYSIS / .ripple.json has HIGH-severity callers, user MUST acknowledge before proceeding.
7. **Write UAT.md atomic** — all responses persisted at the end. Rejected/deferred phases still write UAT.md (audit trail).
8. **Zero hardcode** — all paths from config via `.claude/vg.config.md`.
9. **VG-native, not GSD** — no dependency on `/gsd:verify-work` or any GSD skill. All logic lives here.
</rules>

<objective>
Step 6 of V6 pipeline (final). Data-driven Human UAT generated from VG artifacts — replaces the prior GSD-delegating flow. User reviews each decision, goal, ripple, design-ref explicitly.

Pipeline: specs → scope → blueprint → build → review → test → **accept**
</objective>

<process>

## Step 0: Config Loading

Read `.claude/vg.config.md` — parse YAML frontmatter.
Uses same config resolution as `.claude/commands/vg/_shared/config-loader.md` (BOM strip, required field check, env resolution). Codex inlines the logic below for portability.

**Resolve ENV:**
1. If `--local` in arguments → `ENV=local`
2. If `--sandbox` in arguments → `ENV=sandbox`
3. Else → `ENV = config.step_env.verify` (default)

**Resolve paths + profile:**
```
PHASE_NUMBER  = {first positional argument}
PHASES_DIR    = config.paths.phases               (e.g., .planning/phases)
PLANNING_DIR  = config.paths.planning             (e.g., .planning)
PROFILE       = config.profile                    (web-fullstack|web-frontend-only|web-backend-only|cli-tool|library)
REPO_ROOT     = $(git rev-parse --show-toplevel 2>/dev/null || pwd)
VG_TMP        = ${REPO_ROOT}/.vg-tmp
PYTHON_BIN    = first of: python3, python, py (that passes `-V` major>=3 minor>=10)
```

Locate phase dir (handle both `7.6` and `07.6` naming):
```bash
PHASE_DIR=$(find "$PHASES_DIR" -maxdepth 1 -type d \( -name "${PHASE_NUMBER}*" -o -name "0${PHASE_NUMBER}*" \) 2>/dev/null | head -1)
[ -z "$PHASE_DIR" ] && { echo "⛔ Phase dir not found for: $PHASE_NUMBER"; exit 1; }
PHASE_NUMBER=$(basename "$PHASE_DIR" | grep -oE '^[0-9]+(\.[0-9]+)*')
mkdir -p "$VG_TMP"
```

## Step 1: Gate 1 — Artifact Precheck

```bash
MISSING=""
for f in SPECS.md CONTEXT.md API-CONTRACTS.md TEST-GOALS.md GOAL-COVERAGE-MATRIX.md; do
  [ -f "${PHASE_DIR}/${f}" ] || MISSING="$MISSING $f"
done
ls "${PHASE_DIR}"/*PLAN*.md       >/dev/null 2>&1 || MISSING="$MISSING PLAN*.md"
ls "${PHASE_DIR}"/*SUMMARY*.md    >/dev/null 2>&1 || MISSING="$MISSING SUMMARY*.md"
ls "${PHASE_DIR}"/*SANDBOX-TEST.md >/dev/null 2>&1 || MISSING="$MISSING SANDBOX-TEST.md"

# RUNTIME-MAP only required for web profiles
case "$PROFILE" in
  web-fullstack|web-frontend-only)
    [ -f "${PHASE_DIR}/RUNTIME-MAP.json" ] || MISSING="$MISSING RUNTIME-MAP.json"
    ;;
esac

if [ -n "$MISSING" ]; then
  echo "⛔ Missing required artifacts:$MISSING"
  echo "   Run prior pipeline steps first (\$vg-build / \$vg-review / \$vg-test)"
  exit 1
fi
echo "✓ All required artifacts present"
```

## Step 2: Gate 2 — Step Marker Verification

Every step in build/review/test that applies to `$PROFILE` must have a `.step-markers/{step}.done` marker. Uses `filter-steps.py` (already in `.claude/scripts/`) to compute the expected set per profile.

```bash
MARKER_DIR="${PHASE_DIR}/.step-markers"
mkdir -p "$MARKER_DIR"

MISSED=""
for cmd in build review test; do
  CMD_FILE=".claude/commands/vg/${cmd}.md"
  [ -f "$CMD_FILE" ] || continue
  EXPECTED=$(${PYTHON_BIN} .claude/scripts/filter-steps.py \
    --command "$CMD_FILE" --profile "$PROFILE" --output-ids 2>/dev/null)
  [ -z "$EXPECTED" ] && continue
  for step in $(echo "$EXPECTED" | tr ',' ' '); do
    if [ ! -f "${MARKER_DIR}/${step}.done" ]; then
      MISSED="$MISSED ${cmd}:${step}"
    fi
  done
done

if [ -n "$(echo "$MISSED" | xargs)" ]; then
  echo "⛔ Missing step markers for profile '$PROFILE':"
  for m in $MISSED; do echo "   - $m"; done
  echo "   Resume: \$vg-next  (auto-detects which step to rerun)"
  exit 1
fi
echo "✓ All expected step markers present for profile: $PROFILE"
```

## Step 3: Gate 3 — SANDBOX-TEST Verdict

```bash
SANDBOX=$(ls "${PHASE_DIR}"/*SANDBOX-TEST.md 2>/dev/null | head -1)
VERDICT=$(grep -iE "^\s*\*\*Verdict:?\*\*|^\s*Verdict:" "$SANDBOX" | head -1 \
          | grep -oiE "PASSED|GAPS_FOUND|FAILED" | tr '[:lower:]' '[:upper:]')

case "$VERDICT" in
  PASSED|GAPS_FOUND)
    echo "✓ Test verdict: $VERDICT"
    ;;
  FAILED)
    # ⛔ HARD GATE (tightened 2026-04-17): no override path.
    echo "⛔ Test verdict: FAILED. Cannot accept."
    echo "   Fix failures: \$vg-build ${PHASE_NUMBER} --gaps-only → \$vg-test ${PHASE_NUMBER}"
    exit 1
    ;;
  *)
    # ⛔ HARD GATE (tightened 2026-04-17): unparseable verdict = exit, not warn.
    echo "⛔ Test verdict not parseable from $SANDBOX — regenerate via \$vg-test."
    exit 1
    ;;
esac

# ⛔ HARD GATE (tightened 2026-04-17): surface build-phase overrides.
BUILD_STATE="${PHASE_DIR}/build-state.log"
if [ -f "$BUILD_STATE" ]; then
  OVERRIDES=$(grep -E "^(override|regression-guard.*OVERRIDE|regression-guard.*WARN|skip-design-check|missing-summaries)" "$BUILD_STATE" 2>/dev/null)
  if [ -n "$OVERRIDES" ]; then
    echo "⚠ Build-phase overrides detected (must be acknowledged in UAT.md):"
    echo "$OVERRIDES" | sed 's/^/   /'
    echo "$OVERRIDES" > "${VG_TMP}/uat-build-overrides.txt"
  fi
fi

# ⛔ HARD GATE (tightened 2026-04-17): regression surface check.
REG_REPORT=$(ls "${PHASE_DIR}"/REGRESSION-REPORT*.md 2>/dev/null | head -1)
if [ -n "$REG_REPORT" ]; then
  REG_COUNT=$(grep -oE 'REGRESSION_COUNT:\s*[0-9]+' "$REG_REPORT" | grep -oE '[0-9]+' | head -1)
  REG_FIXED=$(grep -q "fix-loop: applied" "$REG_REPORT" && echo "yes" || echo "no")
  if [ -n "$REG_COUNT" ] && [ "$REG_COUNT" -gt 0 ] && [ "$REG_FIXED" != "yes" ]; then
    echo "⛔ Regressions detected: ${REG_COUNT} goals regressed, fix-loop not run."
    echo "   Fix: \$vg-regression --fix  (auto-fix then re-accept)"
    if [[ ! "$ARGUMENTS" =~ --override-regressions= ]]; then
      exit 1
    else
      echo "⚠ --override-regressions set — recording in UAT.md"
    fi
  fi
fi

DIRTY=$(git status --porcelain 2>/dev/null | head -5)
if [ -n "$DIRTY" ]; then
  echo "⚠ Working tree has uncommitted changes (may be intentional):"
  echo "$DIRTY" | sed 's/^/   /'
fi

# ⛔ HARD GATE (added v1.5.1 — codex parity): UNREACHABLE triage gate
# Block accept if /vg:review (Claude or Codex) produced bug-this-phase / cross-phase-pending / scope-amend verdicts.
TRIAGE_JSON="${PHASE_DIR}/.unreachable-triage.json"
if [ -f "$TRIAGE_JSON" ]; then
  BLOCKING_LIST=$(${PYTHON_BIN} - "$TRIAGE_JSON" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
blocking = []
for gid, v in data.get("verdicts", {}).items():
    if v.get("blocks_accept"):
        blocking.append(f"{gid}|{v['verdict']}|{v['title'][:80]}")
print("\n".join(blocking))
PY
)
  if [ -n "$BLOCKING_LIST" ]; then
    BLOCKING_COUNT=$(echo "$BLOCKING_LIST" | wc -l)
    echo ""
    echo "⛔ \$vg-accept BLOCKED — ${BLOCKING_COUNT} UNREACHABLE goals need resolution before phase ${PHASE_NUMBER} can ship:"
    echo ""
    echo "$BLOCKING_LIST" | while IFS='|' read -r gid verdict title; do
      echo "  • ${gid} [${verdict}] — ${title}"
    done
    echo ""
    echo "See ${PHASE_DIR}/UNREACHABLE-TRIAGE.md for evidence + required actions."
    echo ""
    echo "Fix paths by verdict:"
    echo "  bug-this-phase       → \$vg-build ${PHASE_NUMBER} --gaps-only"
    echo "  cross-phase-pending  → wait for owning phase to reach 'accepted', OR \$vg-amend"
    echo "  scope-amend          → \$vg-amend ${PHASE_NUMBER}"
    echo ""
    if [[ "$ARGUMENTS" =~ --allow-unreachable ]]; then
      REASON=$(echo "$ARGUMENTS" | grep -oE -- "--reason='[^']+'" | sed "s/--reason='//; s/'$//")
      [ -z "$REASON" ] && { echo "⛔ --allow-unreachable requires --reason='<why shipping with known gaps>'"; exit 1; }
      echo "⚠ --allow-unreachable set — reason: ${REASON}"
      echo "unreachable-accept: phase=${PHASE_NUMBER} reason=\"${REASON}\" ts=$(date -u +%FT%TZ)" >> "${PHASE_DIR}/build-state.log"
      echo "$BLOCKING_LIST" > "${VG_TMP}/uat-unreachable-debt.txt"
      echo "$REASON" > "${VG_TMP}/uat-unreachable-reason.txt"
    else
      exit 1
    fi
  fi
fi
```

## Step 4: Build UAT Checklist (5 sections — from VG artifacts)

### Section A — Decisions (from CONTEXT.md D-XX)

```bash
${PYTHON_BIN} - <<PY > "${VG_TMP}/uat-decisions.txt"
import re
from pathlib import Path
text = Path("${PHASE_DIR}/CONTEXT.md").read_text(encoding="utf-8")
for m in re.finditer(r'^##?\s*(D-\d+)[:\s-]+([^\n]+)', text, re.MULTILINE):
    did = m.group(1)
    title = m.group(2).strip().rstrip('*').strip()[:100]
    print(f"{did}\t{title}")
PY
```

### Section B — Goals (TEST-GOALS.md G-XX × GOAL-COVERAGE-MATRIX.md status)

```bash
${PYTHON_BIN} - <<PY > "${VG_TMP}/uat-goals.txt"
import re
from pathlib import Path
goals_text = Path("${PHASE_DIR}/TEST-GOALS.md").read_text(encoding="utf-8")
cov_path = Path("${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md")
coverage = cov_path.read_text(encoding="utf-8") if cov_path.exists() else ""

for m in re.finditer(r'^##?\s*(G-\d+)[:\s-]+([^\n]+)', goals_text, re.MULTILINE):
    gid = m.group(1)
    title = m.group(2).strip().rstrip('*').strip()[:100]
    status = "UNKNOWN"
    for line in coverage.splitlines():
        if gid in line:
            up = line.upper()
            for tag in ("READY", "BLOCKED", "UNREACHABLE", "PARTIAL"):
                if tag in up:
                    status = tag
                    break
            break
    print(f"{gid}\t{status}\t{title}")
PY
```

### Section C — Ripple acknowledgment (from `.ripple.json`)

```bash
RIPPLE_JSON="${PHASE_DIR}/.ripple.json"
if [ -f "$RIPPLE_JSON" ]; then
  ${PYTHON_BIN} - <<PY > "${VG_TMP}/uat-ripples.txt"
import json
from pathlib import Path
d = json.loads(Path("$RIPPLE_JSON").read_text(encoding="utf-8"))
count = 0
for r in d.get("ripples", []):
    for c in r.get("callers", []):
        print(f"{c['file']}:{c.get('line','?')}\t{c.get('symbol','?')}\t{r['changed_file']}")
        count += 1
print(f"# TOTAL_CALLERS={count}")
PY
else
  : > "${VG_TMP}/uat-ripples.txt"
fi
```

### Section D — Design fidelity (from PLAN `<design-ref>`)

```bash
${PYTHON_BIN} - <<PY > "${VG_TMP}/uat-designs.txt"
import re
from pathlib import Path
for plan in Path("${PHASE_DIR}").glob("*PLAN*.md"):
    text = plan.read_text(encoding="utf-8")
    for m in re.finditer(r'<design-ref>([^<]+)</design-ref>', text):
        print(m.group(1).strip())
PY
sort -u "${VG_TMP}/uat-designs.txt" -o "${VG_TMP}/uat-designs.txt"
```

### Section E — Deliverables (informational, from SUMMARY*.md)

```bash
${PYTHON_BIN} - <<PY > "${VG_TMP}/uat-summary.txt"
import re
from pathlib import Path
for s in sorted(Path("${PHASE_DIR}").glob("*SUMMARY*.md")):
    text = s.read_text(encoding="utf-8")
    for m in re.finditer(r'^##?\s*(Task\s+\d+|Deliverable\s*\d+)[:\s-]+([^\n]+)', text, re.MULTILINE):
        title = m.group(2).strip().rstrip('*').strip()[:100]
        print(f"{s.name}\t{m.group(1)}\t{title}")
PY
```

### Present counts + kickoff prompt

```
UAT Checklist for Phase ${PHASE_NUMBER}:
  A — Decisions (D-XX):      {count}
  B — Goals (G-XX):          {count}
  C — Ripple HIGH callers:   {count}
  D — Design refs:           {count}
  E — Deliverables summary:  {count}
  Test verdict (pre-UAT):    $VERDICT
```

```
request_user_input(prompt="
Proceed with UAT for Phase ${PHASE_NUMBER}?

  [y] Start UAT (run sections A→D interactively)
  [n] Abort (write UAT.md status=ABORTED)
")
```

## Step 5: Interactive UAT (one item at a time)

Record every response in memory as `{section, id, status, note, timestamp}` for Step 6.

### A. Decisions — ask for each line in `uat-decisions.txt`

```
request_user_input(prompt="
Decision {D-XX}: {title}

Was this decision implemented as specified in CONTEXT.md?

  [p] Pass — verified in code/runtime
  [f] Fail — not implemented correctly (describe issue)
  [s] Skip — cannot verify right now (deferred)
")
```

### B. Goals — ask only for READY goals; flag BLOCKED/UNREACHABLE as known gaps (no question)

For READY:
```
request_user_input(prompt="
Goal {G-XX}: {title}   [STATUS: READY per coverage matrix]

Verified working in runtime per TEST-GOALS.md success criteria?

  [p] Pass — meets success criteria
  [f] Fail — wrong behavior / doesn't work (describe)
  [s] Skip — not testable here (deferred)
")
```

For BLOCKED/UNREACHABLE — just print:
```
⚠ Goal {G-XX}: {title}   [STATUS: {BLOCKED|UNREACHABLE}] — known gap, not gated.
    Address later via \$vg-build --gaps-only or next phase.
```

### C. Ripple acknowledgment (MANDATORY if HIGH callers exist)

Present first 10 (plus "... and N more" if > 10), then:
```
request_user_input(prompt="
Ripple callers (HIGH severity) not updated in this phase:

  {caller 1}
  {caller 2}
  ...
  (+ N more — see RIPPLE-ANALYSIS.md)

Each should have been manually reviewed or explicitly cited in commits.
Have you verified these callers still work with the changed symbols?

  [y] Yes — verified (code review + RIPPLE-ANALYSIS read)
  [n] No — need review first (ABORT UAT)
  [s] Skip — accept risk (recorded in UAT.md)
")
```

If response = `n` → write UAT.md with status `DEFERRED_PENDING_RIPPLE_REVIEW`, exit.

### D. Design fidelity — for each unique design-ref

```
request_user_input(prompt="
Design ref: {ref}
Screenshot: .planning/design-normalized/screenshots/{ref}.png

Built output matches screenshot (layout, spacing, components)?

  [p] Pass — visual match
  [f] Fail — significant drift (describe)
  [s] Skip — no design asset / cannot verify
")
```

### E. Deliverables — print `uat-summary.txt` as context, no per-item question.

### Final verdict question

Present running totals:
```
UAT Progress:
  A Decisions:  {P}P / {F}F / {S}S
  B Goals:      {P}P / {F}F / {S}S  (+ {N} known gaps)
  C Ripples:    {acknowledged | risk-accepted | skipped}
  D Designs:    {P}P / {F}F / {S}S
```

```
request_user_input(prompt="
Overall phase verdict?

  [a] ACCEPT  — phase complete (all critical items pass)
  [r] REJECT  — issues found, need \$vg-build --gaps-only
  [d] DEFER   — partial accept, revisit later
")
```

## Step 6: Write UAT.md

Write `${PHASE_DIR}/${PHASE_NUMBER}-UAT.md`:

```markdown
# Phase ${PHASE_NUMBER} — UAT Results

**Date:** {ISO timestamp}
**Tester:** {git user.name} (Codex-assisted UAT)
**Profile:** {PROFILE}
**Verdict:** {ACCEPTED | REJECTED | DEFERRED | ABORTED | DEFERRED_PENDING_RIPPLE_REVIEW}
**Test verdict (pre-UAT):** {VERDICT from SANDBOX-TEST.md}

## A. Decisions (CONTEXT.md D-XX)
| D-XX | Title | Result | Note |
|------|-------|--------|------|
| ... | ... | PASS/FAIL/SKIP | ... |

Totals: {P}P / {F}F / {S}S

## B. Goals (TEST-GOALS.md G-XX)
| G-XX | Title | Coverage | UAT Result | Note |
|------|-------|----------|------------|------|
| ... | ... | READY | PASS | ... |
| ... | ... | BLOCKED | — | Known gap |

Totals (READY only): {P}P / {F}F / {S}S  (+ {N} pre-known gaps)

## C. Ripple Acknowledgment (RIPPLE-ANALYSIS / .ripple.json)
- Total HIGH callers: {N}
- Response: {acknowledged | risk-accepted | review-deferred}
- Sample callers (first 20): ...

## D. Design Fidelity (PLAN <design-ref>)
| Ref | Result | Note |
|-----|--------|------|
| ... | PASS/FAIL/SKIP | ... |

Totals: {P}P / {F}F / {S}S

## E. Deliverables (informational, SUMMARY*.md)
- {N} tasks built — see SUMMARY*.md

## Issues Found
{bulleted FAIL list across sections, or "None"}

## Overall Summary
- Total items: {N_total}
- Passed: {N_passed}
- Failed: {N_failed}
- Skipped/deferred: {N_skipped}
- Known pre-existing gaps (not gated): {N_gaps}

## Next Step
{
  ACCEPTED: "Phase complete. Run \$vg-next.",
  REJECTED: "Address failures via \$vg-build ${PHASE_NUMBER} --gaps-only, then \$vg-test → \$vg-accept.",
  DEFERRED: "Partial accept — open items listed. Resume: \$vg-accept ${PHASE_NUMBER} --resume."
}

---
_Generated by \$vg-accept — data-driven UAT over VG artifacts (Codex port)._
```

Touch marker:
```bash
touch "${PHASE_DIR}/.step-markers/accept.done"
```

## Step 7: Post-Verdict Actions

### If ACCEPTED

```bash
# Cleanup scan intermediates
rm -f "${PHASE_DIR}"/scan-*.json
rm -f "${PHASE_DIR}"/probe-*.json
rm -f "${PHASE_DIR}"/nav-discovery.json
rm -f "${PHASE_DIR}"/discovery-state.json
rm -f "${PHASE_DIR}"/view-assignments.json
rm -f "${PHASE_DIR}"/element-counts.json
rm -f "${PHASE_DIR}"/.ripple-input.txt
rm -f "${PHASE_DIR}"/.ripple.json       # aggregated into UAT.md
rm -f "${PHASE_DIR}"/.callers.json
rm -f "${PHASE_DIR}"/.god-nodes.json
rm -rf "${PHASE_DIR}"/.wave-context
rm -rf "${PHASE_DIR}"/.wave-tasks

# Root-leaked screenshots (banned location per project convention)
rm -f ./${PHASE_NUMBER}-*.png 2>/dev/null || true

# Prune git worktrees + playwright locks (best-effort)
git worktree prune 2>/dev/null || true
[ -x "${HOME}/.claude/playwright-locks/playwright-lock.sh" ] && \
  bash "${HOME}/.claude/playwright-locks/playwright-lock.sh" cleanup 0 all 2>/dev/null || true

# Update GSD state (optional — skip silently if not installed)
if [ -x "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" ]; then
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" state update-phase \
    --phase "${PHASE_NUMBER}" --status "complete" --pipeline-step "accepted" 2>/dev/null || true
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" roadmap update-phase \
    --phase "${PHASE_NUMBER}" --status "complete" 2>/dev/null || true
fi

# Commit UAT.md + marker
git add "${PHASE_DIR}/${PHASE_NUMBER}-UAT.md" "${PHASE_DIR}/.step-markers/accept.done"
git commit -m "docs(${PHASE_NUMBER}-accept): UAT accepted — {N_passed}/{N_total} items pass

Covers goal: accept phase ${PHASE_NUMBER}"
```

Output:
```
Phase ${PHASE_NUMBER} ACCEPTED ✓

Preserved: SPECS, CONTEXT, PLAN*, API-CONTRACTS, TEST-GOALS, SUMMARY*,
           RUNTIME-MAP.json, GOAL-COVERAGE-MATRIX.md, SANDBOX-TEST.md,
           RIPPLE-ANALYSIS.md, UAT.md

Cleaned:   scan/probe intermediates, .wave-* , .ripple.json, .callers.json

▶ \$vg-next   (advance to next phase)
```

### If REJECTED

```
Phase ${PHASE_NUMBER} REJECTED — {N_failed} issues.

Failed items:
  [A] Decisions: {list of failed D-XX}
  [B] Goals:     {list of failed G-XX}
  [C] Ripples:   {if deferred}
  [D] Designs:   {list of failed refs}

Next:
  1. \$vg-build ${PHASE_NUMBER} --gaps-only   (gap-closure plans from UAT.md FAIL items)
  2. \$vg-test  ${PHASE_NUMBER}               (re-verify)
  3. \$vg-accept ${PHASE_NUMBER}              (re-run UAT)
```

### If DEFERRED / ABORTED / DEFERRED_PENDING_RIPPLE_REVIEW

```bash
# ⛔ HARD GATE (tightened 2026-04-17): DEFERRED blocks \$vg-next until resolved.
PIPELINE_STATE="${PHASE_DIR}/PIPELINE-STATE.json"
${PYTHON_BIN} -c "
import json; from pathlib import Path
p = Path('${PIPELINE_STATE}')
s = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
s['status'] = 'deferred-incomplete'
s['deferred_at'] = __import__('datetime').datetime.now().isoformat()
s['deferred_items_count'] = ${N_failed:-0}
p.write_text(json.dumps(s, indent=2))
"
touch "${PHASE_DIR}/.deferred-incomplete"
```

```
Phase ${PHASE_NUMBER} {STATUS} — partial / no accept.

⛔ \$vg-next BLOCKED for this phase until deferred items resolved.
Open items recorded in UAT.md.
Resume: \$vg-accept ${PHASE_NUMBER} --resume  (reopens deferred items only)
Force advance (NOT RECOMMENDED): \$vg-next --allow-deferred
```

</process>

<success_criteria>
- All artifacts + step markers verified BEFORE UAT starts
- Checklist items generated FROM VG data (not hardcoded)
- Every D-XX, G-XX (READY), HIGH-ripple caller, design-ref addressed by user
- UAT.md written atomically with pass/fail/skip per section
- If ACCEPTED: cleanup + commit + optional GSD state update
- If REJECTED: clear gap list pointing to $vg-build --gaps-only
- No dependency on GSD verify-work or any SlashCommand (VG-native, Codex-portable)
</success_criteria>
