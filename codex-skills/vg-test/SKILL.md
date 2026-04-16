---
name: "vg-test"
description: "Clean goal verification + independent smoke + codegen regression + security audit"
metadata:
  short-description: "Test a phase — verify goals against RUNTIME-MAP, gen regression tests"
---

<codex_skill_adapter>
## A. Skill Invocation
- This skill is invoked by mentioning `$vg-test`.
- Treat all user text after `$vg-test` as arguments: `{{PHASE}} [--skip-deploy] [--regression-only] [--smoke-only] [--fix-only] [--full-scan]`
- If no phase given, ask: "Which phase? (e.g., 7.6)"

## B. AskUserQuestion → request_user_input Mapping
GSD workflows use `AskUserQuestion` (Claude Code syntax). Translate to Codex `request_user_input`:
- AskUserQuestion(question="X") → request_user_input(prompt="X")

## C. Browser Tools
**Codex has MCP Playwright connected.** Use Playwright MCP tools for all browser interaction:
- `browser_navigate` → go to URL (only for initial login/domain switch)
- `browser_snapshot` → read current page state (accessibility tree)
- `browser_click` → click element by ref or text
- `browser_fill_form` → fill input fields
- `browser_take_screenshot` → capture evidence
- `browser_console_messages` → check for errors after EVERY action
- `browser_network_requests` → monitor API calls (method, url, status)
- `browser_wait_for` → wait for element/condition

**Every action must be followed by:** snapshot + console check + network check (3-layer).

### D. Playwright Lock (multi-session safety)
**BEFORE any browser interaction**, claim a lock so other sessions (Claude tabs, Gemini) know this server is in use:
```bash
bash "${HOME}/.claude/playwright-locks/playwright-lock.sh" claim "codex-{phase}-test-$$"
```
**AFTER test completes (or on error)**, release:
```bash
bash "${HOME}/.claude/playwright-locks/playwright-lock.sh" release "codex-{phase}-test-$$"
```
If claim fails (all 5 locked) → BLOCK, do NOT cleanup other sessions' locks.

### Element Interaction Protocol (for smoke check + goal verification)

When interacting with elements during smoke or goal verification, follow these rules:

**SNAPSHOT PRUNE RULE (DEFAULT — disabled if --full-scan):**
IF --full-scan: skip this rule entirely. Use full snapshot for all interactions.
Run browser_evaluate ONCE at session start:
  "const s=['main','[role=\"main\"]','#main-content','.main-content','#content','.content-area','[data-main]'];
   return s.find(sel=>document.querySelector(sel))||null;"
→ MAIN_SELECTOR = result
For every browser_snapshot: build working element list ONLY from inside MAIN_SELECTOR.
SKIP: sidebar nav, header, footer, breadcrumbs, [aria-label="sidebar"].
If no MAIN_SELECTOR: use full snapshot.
EXCEPTIONS — suspend MAIN_SELECTOR, use FULL snapshot:
  modal/dialog/drawer opened | toast/notification after action. Resume after modal closes.

**AFTER EVERY CLICK:**
- Re-snapshot → check for NEW elements not previously listed
- If new elements appeared (accordion expand, inline content, lazy load) → note in report

**Element-specific awareness:**

| Element Type | What to check |
|---|---|
| tab/segmented-control/pill-nav | Click EACH tab → verify content loads in panel → check elements inside |
| dropdown/menu/popover (NOT select) | Click to open → verify all items present → click relevant items for goal |
| table/list with rows | Scroll container → verify row count matches expected → check actions on sample row |
| disabled/hidden element | Try to enable (select checkbox/row) → verify enables correctly |
| form (inputs + submit) | Fill ALL fields → submit → verify: toast TEXT + console errors + API response (3-layer) |
| modal/dialog (after open) | List ALL elements inside → verify form fields + actions work |

**HARD RULES (same as review):**
- Re-snapshot after EVERY click
- Record console errors + network requests after EVERY action
- If confirm dialog appears: test Cancel first, re-trigger, then OK
- Report any element you cannot interact with — do NOT silently skip

## D. Spawning Agents
Use `codex exec "..."` to spawn parallel verification agents in shell.
</codex_skill_adapter>

<rules>
1. **RUNTIME-MAP.json + GOAL-COVERAGE-MATRIX.md required** — review must have completed. Missing = BLOCK.
2. **TEST-GOALS.md required** — goals must exist (from blueprint or review).
3. **No discovery in test** — review already explored. Test VERIFIES known paths.
4. **MINOR-only fix** — test fixes MINOR issues only. MODERATE/MAJOR → REVIEW-FEEDBACK.md, kick back to review.
5. **Independent smoke first** — spot-check RUNTIME-MAP accuracy before trusting it.
6. **Navigate via UI clicks** — direct URL navigation BANNED except for initial login/domain switch.
7. **Console monitoring** — check console after EVERY action.
8. **Goal-based codegen** — assertions from TEST-GOALS success criteria, paths from RUNTIME-MAP observation.
9. **Zero hardcode** — no endpoint, role, page name, or project-specific value in this workflow. All values from config or runtime observation.
10. **Profile enforcement (UNIVERSAL)** — every `<step>` MUST, as FINAL action:
    `touch "${PHASE_DIR}/.step-markers/{STEP_NAME}.done"`.
    Preflight via `filter-steps.py` returns applicable steps for `$PROFILE`. Task count MUST match.
    Browser steps (5c-smoke, 5c-flow, 5d) skipped for backend-only/cli/library.
    Contract-curl (5b) skipped for frontend-only/cli/library.
11. **Unit test gate mandatory** (if config.build_gates.test_unit_required=true) —
    Post-wave: affected subset. Post-execution: full suite. BLOCK on fail unless `--allow-no-tests`.
12. **Flow test integration** — if FLOW-SPEC.md exists, note to user: "Run via Claude /vg:test to use flow-runner MCP skill (Codex does not have flow-runner)."
    **Documented limitation:** Codex cannot invoke the flow-runner MCP skill. Multi-page
    flow tests (login → create → edit → delete chains) require Claude's /vg:test.
    Codex detects when flows SHOULD exist (chain detection) and warns the user.
</rules>

## Profile preflight (run BEFORE step 5a)

```bash
PROFILE=$(${PYTHON_BIN} -c "
import re
for line in open('.claude/vg.config.md', encoding='utf-8'):
    m = re.match(r'^profile:\s*[\"\']?([^\"\'#\s]+)', line)
    if m: print(m.group(1)); break
")
[ -z "$PROFILE" ] && { echo "⛔ config.profile missing"; exit 1; }

EXPECTED_STEPS=$(${PYTHON_BIN} .claude/scripts/filter-steps.py \
  --command .claude/commands/vg/test.md \
  --profile "$PROFILE" \
  --output-ids)
echo "Profile: $PROFILE"
echo "Applicable steps: $EXPECTED_STEPS"

MARKER_DIR="${PHASE_DIR}/.step-markers"
mkdir -p "$MARKER_DIR"

# If FLOW-SPEC.md exists and profile has browser → warn user
if [ -f "${PHASE_DIR}/FLOW-SPEC.md" ] && echo "$EXPECTED_STEPS" | grep -q "5c_flow"; then
  echo "ℹ Flow tests defined. Codex can't invoke flow-runner — run via Claude /vg:test for full flow coverage."
elif [ ! -f "${PHASE_DIR}/FLOW-SPEC.md" ] && [ -f "${PHASE_DIR}/TEST-GOALS.md" ]; then
  CHAIN_COUNT=$(${PYTHON_BIN} -c "
import re
from pathlib import Path
from collections import deque
text = Path('${PHASE_DIR}/TEST-GOALS.md').read_text(encoding='utf-8')
goals, cur = {}, None
for line in text.splitlines():
    m = re.match(r'^## Goal (G-\d+)', line)
    if m: cur = m.group(1); goals[cur] = []
    elif cur:
        dm = re.match(r'\*\*Dependencies:\*\*\s*(.+)', line)
        if dm and dm.group(1).strip().lower() not in ('none',''):
            goals[cur] = re.findall(r'G-\d+', dm.group(1))
roots = [g for g,d in goals.items() if not d]
chains = 0
for r in roots:
    q = deque([(r, 1)])
    while q:
        node, depth = q.popleft()
        for g,d in goals.items():
            if node in d:
                if depth + 1 >= 3: chains += 1
                q.append((g, depth + 1))
print(chains)
" 2>/dev/null)
  if [ "${CHAIN_COUNT:-0}" -gt 0 ]; then
    echo "⚠ FLOW-SPEC.md absent but ${CHAIN_COUNT} goal chains >= 3 detected."
    echo "  Run /vg:blueprint {phase} --from=2b7 in Claude to auto-generate FLOW-SPEC.md"
  fi
fi
```

**CRITICAL — marker filename mapping (matches Claude test.md step names, cross-CLI handoff):**

| Codex section (this skill) | Marker filename |
|---|---|
| 5a: DEPLOY | `5a_deploy.done` |
| 5b: RUNTIME CONTRACT VERIFY | `5b_runtime_contract_verify.done` |
| 5c-smoke: INDEPENDENT SPOT CHECK | `5c_smoke.done` |
| 5c-goal: GOAL VERIFICATION | `5c_goal_verification.done` |
| 5c-fix: MINOR FIX | `5c_fix.done` |
| 5c-auto-escalate | `5c_auto_escalate.done` |
| 5c-flow (if FLOW-SPEC.md) | `5c_flow.done` |
| 5d: CODEGEN | `5d_codegen.done` |
| 5e: REGRESSION | `5e_regression.done` |
| 5f: SECURITY AUDIT | `5f_security_audit.done` |
| Write report | `write_report.done` |
| Complete | `complete.done` |

Write marker at end of each section:
```bash
touch "${MARKER_DIR}/5a_deploy.done"
```

Skip markers for skipped sections (per profile): e.g., if profile=web-backend-only, skip 5c_smoke, 5c_flow, 5d_codegen — no marker written.

<objective>
Clean goal verification — review already discovered + fixed. Test only verifies goals and generates regression tests.

Pipeline: specs → scope → blueprint → build → review → **test** → accept

Sub-steps:
- 5a: DEPLOY — push + build + restart on target
- 5b: RUNTIME CONTRACT VERIFY — curl + jq per endpoint
- 5c-smoke: INDEPENDENT SPOT CHECK — cross-check RUNTIME-MAP accuracy
- 5c-goal: GOAL VERIFICATION — verify each goal via known paths (topological sort)
- 5c-fix: MINOR FIX ONLY — minor fix in test, moderate/major escalate to review
- 5d: CODEGEN — generate .spec.ts from verified goals + RUNTIME-MAP paths
- 5e: REGRESSION RUN — npx playwright test
- 5f: SECURITY AUDIT — grep + optional deep scan
</objective>

<process>

## Config Loading

Read `.claude/vg.config.md` — parse YAML frontmatter.

**Resolve ENV (never hardcode "sandbox"):**
1. If `--local` in arguments → `ENV=local`
2. If `--sandbox` in arguments → `ENV=sandbox`
3. Else → `ENV = config.step_env.sandbox_test`

From resolved `ENV`, extract:
- `credentials[ENV]` — login URLs, emails, passwords per role
- `services[ENV]` — health checks
- `environments[ENV]` — deploy commands, project path
- `paths` — planning dir, phases dir, screenshots dir, generated_tests dir

**VERIFY before any browser action:**
Print: `ENV resolved to: {ENV} | Domain: {credentials[ENV][0].domain}`
If ENV=sandbox but user ran without --sandbox flag → WARN: "Using sandbox env from config. Add --local to override."
If ENV=local but app not reachable at domain → BLOCK: "Local app not running. Start with: {environments.local.dev_command}"

<step name="0_parse_and_validate">
Parse arguments: phase_number, flags (--skip-deploy, --regression-only, --smoke-only, --fix-only).

Find phase directory in `.planning/phases/` (try both "7.6" and "07.6" formats).

Validate:
- `${PHASE_DIR}/RUNTIME-MAP.json` exists
- `${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md` exists
- `${PHASE_DIR}/TEST-GOALS.md` exists
- `${PHASE_DIR}/API-CONTRACTS.md` exists

Missing → BLOCK: "Run review first (Claude: /vg:review, Codex: $vg-review, Gemini: /vg-review)."

**⛔ NOT_SCANNED rejection gate (tightened 2026-04-17 — GLOBAL rule):**

Test replay `goal_sequences[]` mà review ghi trong RUNTIME-MAP. Goals có status `NOT_SCANNED` hoặc `FAILED` (intermediate) KHÔNG có sequence → test không có input replay → KHÔNG được defer sang test.

```
Parse GOAL-COVERAGE-MATRIX.md:
  INTERMEDIATE = goals where status IN ("NOT_SCANNED", "FAILED")

IF INTERMEDIATE > 0:
  STOP. Print:
    "⛔ {COUNT} goals có status intermediate trong GOAL-COVERAGE-MATRIX."
    "GLOBAL RULE: test chỉ replay goals có status=READY + goal_sequence.steps[] ≥ 1."
    "Intermediate = review chưa resolve. KHÔNG được dùng /vg:test để 'cover' NOT_SCANNED."
    ""
    "Fix tại review:"
    "  $vg-review {phase} --retry-failed    (deeper probe)"
    "  HOẶC update TEST-GOALS 'Infra deps: [<no-ui tag>]' → re-classify INFRA_PENDING"
    "    (tag value per project config.infra_deps — workflow không hardcode)"
    "  HOẶC manually mark UNREACHABLE nếu feature genuinely không tồn tại"
    ""
    "Re-run: $vg-review {phase} — mọi goals phải ở 1 trong 4 status kết luận"
    "  (READY | BLOCKED | UNREACHABLE | INFRA_PENDING)"
  EXIT 1.
```

**Per-goal runtime rule (enforced in 5c_goal_verification):**
- `status == READY` + `goal_sequence.steps[] ≥ 1` → replay normally
- `status == BLOCKED` → expected fail, log + count in `blocked_replayed`, không trigger fix loop
- `status == UNREACHABLE|INFRA_PENDING` → skip with log "expected skip" (không fail, không count)
- `status IN (NOT_SCANNED, FAILED)` → UNREACHABLE (shouldn't happen, gate above blocks)

If `--regression-only`: skip to 5e.
If `--smoke-only`: run only 5c-smoke.
If `--fix-only`: skip to 5c-fix.

**Optional GSD state update (if GSD installed):**
```bash
if [ -x "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" ]; then
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" state update-phase \
    --phase "${PHASE_NUMBER}" --status "in_progress" --pipeline-step "testing" 2>/dev/null || true
fi
```
</step>

<step name="5a_deploy">
## 5a: DEPLOY

**If --skip-deploy, skip this step.**

```
run_prefix = environments[ENV].run_prefix     # "ssh vollx" or ""
project_path = environments[ENV].project_path # "/home/vollx/vollxssp" or ""
deploy = environments[ENV].deploy

1. Record SHAs (local + target)
2. If deploy.pre exists: run deploy.pre (e.g. git push)
3. Run: {run_prefix} "cd {project_path} && {deploy.build}"
4. Run: {run_prefix} "{deploy.restart}"
5. Health check each service from config.services[ENV]
6. If health fail → rollback using deploy.rollback → BLOCK
```

### Re-seed DB (if configured)
If `seed_command` is configured in `config.environments[ENV]`:
  Run seed to ensure test data is fresh (review may have left dirty DB state).
  ```
  SEED_CMD=$(awk -v env="$ENV" '/^environments:/{f=1} f && $0 ~ env":"{g=1} g && /seed_command:/{print $2; exit}' .claude/vg.config.md 2>/dev/null)
  if [ -n "$SEED_CMD" ]; then
    echo "Re-seeding DB for clean test state..."
    ${run_prefix} "cd ${project_path} && ${SEED_CMD}"
  fi
  ```
  Skip silently if no seed_command.

### Typecheck (if configured)
If config.build_gates.typecheck_cmd is non-empty:
  Run: ${run_prefix} "cd ${project_path} && ${config.build_gates.typecheck_cmd}"
  Exit != 0 → BLOCK: "Typecheck failed. Fix before testing."

Display: SHA, build status, health status, services status.
</step>

<step name="5b_runtime_contract_verify">
<!-- profile="web-fullstack,web-backend-only" — skipped for frontend-only/cli/library -->
## 5b: RUNTIME CONTRACT VERIFY (curl + jq)

For each endpoint in API-CONTRACTS.md:
```
curl endpoint on target → extract response keys via jq
Compare actual keys vs expected keys from contract
Record: endpoint, match status, mismatched fields
```

All match → PASS. Any mismatch → BLOCK with specifics.

### 5b-2: Idempotency Check (auto-ON for critical_domains)

**Skip if:** `config.critical_domains` empty/absent OR no endpoints match OR server not running.

Billing, auth, payout endpoints MUST be idempotent for mutations. Double-submit same
request should NOT create duplicate records or charge twice.

```bash
CRITICAL_DOMAINS=$(awk '/^critical_domains:/{print $2}' .claude/vg.config.md 2>/dev/null | tr -d '"')
if [ -n "$CRITICAL_DOMAINS" ] && [ -n "$BASE_URL" ]; then
  # Parse mutation endpoints matching critical domains from API-CONTRACTS.md
  ${PYTHON_BIN} -c "
import re
text = open('${PHASE_DIR}/API-CONTRACTS.md', encoding='utf-8').read()
domains = '${CRITICAL_DOMAINS}'.split(',')
for m in re.finditer(r'###\s+(POST|PUT|DELETE)\s+(/\S+)', text):
    method, path = m.groups()
    if any(d.strip() in path.lower() for d in domains):
        print(f'{method}\t{path}')
" > "${VG_TMP}/critical-endpoints.txt"

  # Extract Block 4 sample payloads from API-CONTRACTS.md for each critical endpoint.
  # Block 4 in API-CONTRACTS.md contains valid sample payload per endpoint.
  # Extract via regex: Sample\s*=\s*(\{[^}]+\})
  ${PYTHON_BIN} -c "
import re
text = open('${PHASE_DIR}/API-CONTRACTS.md', encoding='utf-8').read()
domains = '${CRITICAL_DOMAINS}'.split(',')
# Split by endpoint headers
parts = re.split(r'(###\s+(?:GET|POST|PUT|DELETE|PATCH)\s+/\S+)', text)
for i in range(1, len(parts), 2):
    header = parts[i]
    body = parts[i+1] if i+1 < len(parts) else ''
    m = re.match(r'###\s+(POST|PUT|DELETE|PATCH)\s+(/\S+)', header)
    if not m: continue
    method, path = m.groups()
    if not any(d.strip() in path.lower() for d in domains): continue
    sample_m = re.search(r'Sample\s*=\s*(\{[^}]+\})', body)
    payload = sample_m.group(1) if sample_m else '{}'
    print(f'{method}\t{path}\t{payload}')
" 2>/dev/null > "${VG_TMP}/critical-endpoints-with-payload.txt"

  CRITICAL_COUNT=$(wc -l < "${VG_TMP}/critical-endpoints-with-payload.txt" | tr -d ' ')
  IDEMPOTENCY_FAILS=0
  if [ "$CRITICAL_COUNT" -gt 0 ]; then
    echo "Idempotency check: ${CRITICAL_COUNT} critical-domain mutation endpoints"
    while IFS=$'\t' read -r METHOD ENDPOINT PAYLOAD; do
      [ -z "$ENDPOINT" ] && continue
      # Use Block 4 sample payload; fall back to empty object if not extracted
      [ -z "$PAYLOAD" ] && PAYLOAD='{}'
      RESP1=$(curl -sf -X "$METHOD" "${BASE_URL}${ENDPOINT}" \
        -H "Authorization: Bearer ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" -d "$PAYLOAD" \
        -w "\n%{http_code}" 2>/dev/null)
      STATUS1=$(echo "$RESP1" | tail -1)
      RESP2=$(curl -sf -X "$METHOD" "${BASE_URL}${ENDPOINT}" \
        -H "Authorization: Bearer ${AUTH_TOKEN}" \
        -H "Content-Type: application/json" -d "$PAYLOAD" \
        -w "\n%{http_code}" 2>/dev/null)
      STATUS2=$(echo "$RESP2" | tail -1)
      if [ "$STATUS1" = "201" ] && [ "$STATUS2" = "201" ]; then
        ID1=$(echo "$RESP1" | sed '$d' | ${PYTHON_BIN} -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
        ID2=$(echo "$RESP2" | sed '$d' | ${PYTHON_BIN} -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
        if [ -n "$ID1" ] && [ -n "$ID2" ] && [ "$ID1" != "$ID2" ]; then
          echo "  CRITICAL: ${METHOD} ${ENDPOINT} — double-submit created 2 records"
          IDEMPOTENCY_FAILS=$((IDEMPOTENCY_FAILS + 1))
        fi
      fi
    done < "${VG_TMP}/critical-endpoints-with-payload.txt"
  fi
  echo "Idempotency: ${CRITICAL_COUNT} checked, ${IDEMPOTENCY_FAILS} failures"
fi
```
</step>

<step name="5c_smoke">
## 5c-smoke: INDEPENDENT SPOT CHECK (~2 min)

Cross-check that RUNTIME-MAP matches current app state. Review may have run hours ago.

**Browser mode: HEADED (visible, not headless).** User should see the browser actions.

Login using credentials from config.credentials[ENV].

**Stratified sampling:**
```
1. Select 5 views from RUNTIME-MAP.json:
   - At least 1 view from each role
   - Prefer views with most elements[]
   - Include views referenced by goal_sequences

2. For each selected view:
   a. Navigate via UI clicks (not URL)
   b. Snapshot → read current state
   c. Compare vs RUNTIME-MAP snapshot_summary
   d. Check fingerprint: element count, key elements still exist
   e. Replay 1-2 steps from a goal_sequence if referenced
   f. Console → new errors?

3. Results:
   - 0 mismatches → PROCEED
   - 1 mismatch → WARNING, proceed
   - ≥2 mismatches → FLAG, ask user: proceed or re-review?
```
</step>

<step name="5c_goal_verification">
## 5c-goal: GOAL VERIFICATION (follow known paths)

**Execute goals in dependency order (topological sort):**

For each goal:
```
1. Read goal from TEST-GOALS.md:
   - Success criteria, mutation evidence, priority

2. Read goal_sequence from RUNTIME-MAP.json:
   - start_view, steps[], result

3. REPLAY the goal_sequence step by step:
   a. Narrate goal start (tightened 2026-04-17): print user-readable line
      → `━━━ [${idx}/${total}] ${gid} • ${priority} ━━━`
      → `🎯 ${goal.title}`
   b. Navigate to start_view via UI clicks
   c. For each step (MUST narrate BEFORE action):
      Verb map: navigate=📍Mở, click=👆Bấm, fill=⌨️ Điền, select=🔽Chọn, wait=⏳Đợi, observe=👁 Kiểm tra, assert=✓Xác nhận
      → `  [${n}/${total}] ${icon} ${action} ${target}${value?' = "'+value+'"':''}`
      IF step.do: Execute action (click, fill, select, wait) + check console
         → narrate result: `       ✓ ${detail}` or `       ❌ ${error}`
      IF step.observe: Snapshot → compare vs step description
      IF step.assert: Check criterion → PASS or FAIL
   d. Take screenshot as evidence
   e. Narrate goal end:
      → `✅ ${gid} PASSED (${duration}s)` OR `❌ ${gid} FAILED — ${reason}`

4. Record result:
   - ALL asserts PASS → Goal PASSED
   - ANY assert FAIL → Goal FAILED (with specific failure)
   - Can't complete replay → Goal UNREACHABLE

5. Update GOAL-COVERAGE-MATRIX:
   READY → ✅ TEST-PASSED or ❌ TEST-FAILED
```

**Narration example user sees:**
```
━━━ [3/12] G-03 • critical ━━━
🎯 Tạo chiến dịch mới với budget và targeting
  [1/6] 📍 Mở trang Campaigns (sidebar > Campaigns)
  [2/6] 👆 Bấm "New Campaign"
       ✓ Modal mở
  [3/6] ⌨️  Điền name = "Test Campaign"
  [4/6] ⌨️  Điền budget = "500"
  [5/6] 👆 Bấm "Create"
       ✓ Toast "Campaign created"
       ✓ API POST /api/campaigns → 201
  [6/6] ✓ Xác nhận row mới xuất hiện
✅ G-03 PASSED (4.2s)
```

**After ALL goals:** print tree summary — passed goals 1 dòng, failed expand:
```
═══════════════════════════════════════════════
  GOAL VERIFICATION SUMMARY
═══════════════════════════════════════════════
  ✅ G-01: Create campaign
  ❌ G-02: Delete campaign
      └─ failed at step 4: confirm modal not shown
  ⚠️  G-03: Bulk edit (unreachable)

  Tổng: 1 PASS · 1 FAIL · 1 UNREACHABLE
═══════════════════════════════════════════════
```

For BLOCKED goals: attempt anyway — fix may have resolved blocker.
For UNREACHABLE: try alternative paths.
</step>

<step name="5c_fix">
## 5c-fix: MINOR FIX ONLY (max 2 iterations)

**If all goals PASSED → skip to 5d.**

Classify each FAILED goal:

```
MINOR (fix directly):
  - Wrong text/label, CSS/layout issue, off-by-one, missing null check
  → Fix, commit: "fix({phase}): {description}"
  → Re-verify THIS goal only

MODERATE (escalate):
  - API wrong status, form validation missing, data not refreshing
  → Write to REVIEW-FEEDBACK.md, DO NOT fix

MAJOR (escalate):
  - Feature missing, navigation broken, auth/permissions wrong
  → Write to REVIEW-FEEDBACK.md, DO NOT fix
```

Max 2 fix iterations for MINOR. After 2 still failing → reclassify as MODERATE → escalate.

**REVIEW-FEEDBACK.md format:**
```markdown
# Review Feedback — Phase {phase}

## Issues (require re-review)
| Goal | Severity | Issue | Why test can't fix |
|------|----------|-------|-------------------|

## Suggested Action
Run review again with --fix-only, then re-test with --skip-deploy.
```
</step>

<step name="5c_auto_escalate">
## 5c-auto-escalate: REMEDIATION ROUTING (max 3 total iterations)

Track iteration count across test→fix→re-test loops in ${PHASE_DIR}/test-loop-state.json:
```json
{ "total_iterations": N, "last_action": "...", "timestamp": "..." }
```

**Classification and routing:**

After 5c-fix completes, classify remaining failures:

| Category | Condition | Action |
|----------|-----------|--------|
| A: MODERATE goals still failing | fix loop exhausted (2 iterations) | Redirect: "$vg-review {phase} --retry-failed" |
| B: UNREACHABLE goals | path never found | Redirect: "$vg-build {phase} --gaps-only" (missing implementation) |
| C: NOT_SCANNED goals | scan missed views | Re-run discovery for affected views, then retry goal verification |
| D: SKIPPED goals | user skipped or deferred | Mark in GOAL-COVERAGE-MATRIX as DEFERRED, no action |

**Termination conditions (any → STOP):**
1. All goals READY → proceed to 5d
2. TOTAL_ITER >= 3 → STOP with FINAL GUIDANCE
3. Only DEFERRED goals remain → proceed to 5d
4. No improvement between iterations (same failures) → STOP

**FINAL GUIDANCE (when iterations exhausted):**
```
Test loop exhausted after {N} iterations.

Remaining failures:
  MODERATE (need review fix): {list with $vg-review redirect}
  UNREACHABLE (need implementation): {list with $vg-build redirect}  
  NOT_SCANNED (need discovery): {list with $vg-review --retry-failed}
  DEFERRED: {list, no action needed}

Recommended next step based on majority failure type:
  - Mostly MODERATE → $vg-review {phase} --retry-failed
  - Mostly UNREACHABLE → $vg-build {phase} --gaps-only
  - Mixed → Manual triage needed
```

**DON'T do:**
- Don't fix MODERATE issues directly (that's review's job)
- Don't generate plans (that's build's job)
- Don't re-discover views (that's review --retry-failed)
- Don't exceed 3 total iterations
</step>

<step name="5d_codegen">
<!-- profile="web-fullstack,web-frontend-only" — skipped for backend-only/cli/library -->
## 5d: CODEGEN — Goal-based Test Generation

Generate Playwright test files from VERIFIED goals.

**Pre-codegen Gate — Dynamic ID scan (HARD BLOCK, tightened 2026-04-17):**

```bash
DYN_ID_PATTERNS='#[a-zA-Z_-]+_[0-9]{3,}|#row-[a-z0-9]{6,}|data-id="[0-9]+|\[id\^=|\[data-id\^='
DYN_FOUND=$(${PYTHON_BIN} -c "
import json, re
rt = json.load(open('${PHASE_DIR}/RUNTIME-MAP.json', encoding='utf-8'))
patterns = re.compile(r'${DYN_ID_PATTERNS}')
for goal_id, seq in rt.get('goal_sequences', {}).items():
    for i, step in enumerate(seq.get('steps', [])):
        sel = step.get('selector', '')
        if sel and patterns.search(sel):
            print(f'{goal_id}|step={i}|{sel}')
" 2>/dev/null)

if [ -n "$DYN_FOUND" ]; then
  echo "⛔ Dynamic ID selectors in RUNTIME-MAP.json goal_sequences:"
  echo "$DYN_FOUND" | sed 's/^/  /'
  echo "  Fix: \$vg-review ${PHASE_NUMBER} --retry-failed"
  if [[ ! "$ARGUMENTS" =~ --allow-dynamic-ids ]]; then
    exit 1
  fi
fi
```

For each goal group, write `{generated_tests_dir}/{phase}-goal-{group}.spec.ts`:

```
Codegen rules:
1. Credentials from env vars (ROLE_UPPER_EMAIL, ROLE_UPPER_PASSWORD, ROLE_UPPER_DOMAIN)
2. Selectors from goal_sequences (prefer getByRole > getByText > locator)
3. Assertions from TEST-GOALS success criteria only
4. Steps from goal_sequences — nearly 1:1 mapping
5. Web-first assertions (expect(locator).toHaveText with auto-retry)
6. **Mutation 3-layer verify (tightened 2026-04-17)** — every POST/PUT/PATCH/DELETE step:
   - Layer 1: `await expect(page.getByRole('status')).toContainText(step.expected_toast);`
   - Layer 2: `const res = await page.waitForResponse(r => r.url().includes(step.endpoint)); expect(res.status()).toBeLessThan(400);`
   - Layer 3: `expect((await page.evaluate(() => window.__consoleErrors || [])).length).toBe(0);`

Structure per goal:
  describe("{goal_id}: {description}"):
    beforeEach: login + navigate to start_view
    
    test("primary"):
      Replay goal_sequence steps as Playwright actions
      Console error check at end
      Screenshot capture
    
    test("probe:edit"):     (if probe exists)
    test("probe:boundary"): (if probe exists)
    test("probe:repeat"):   (if probe exists)
```
</step>

<step name="5e_regression">
## 5e: REGRESSION RUN

Run generated tests:
```bash
# Auto-create minimal playwright config for generated tests if missing
if [ ! -f "{generated_tests_dir}/playwright.config.generated.ts" ]; then
  cat > "{generated_tests_dir}/playwright.config.generated.ts" << 'PWEOF'
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.',
  use: { baseURL: process.env.BASE_URL || 'http://localhost:3000' },
  timeout: 30000,
});
PWEOF
fi

cd {project_path} && npx playwright test {generated_tests_dir}/{phase}-goal-*.spec.ts
```

All pass → PASS. Failures → record in report.
</step>

<step name="5f_security_audit">
## 5f: SECURITY AUDIT

### Tier 1: Built-in Security Grep (always, <10 sec)

Get changed files for this phase. Scan for:
1. Secrets — hardcoded credentials, API keys, tokens
2. Injection — unsanitized user input in queries/templates
3. XSS — raw HTML insertion patterns
4. Auth — route handlers without auth middleware

### Tier 2: Deep Scan (optional)
Use first available: semgrep → npm audit → expanded grep.

### Tier 3: Contract-code verbatim verification (3 blocks)

The contract has 3 code blocks per endpoint (auth, schema, error). Verify the executor
actually copied them:

```bash
COPY_MISMATCHES=0

# Extract auth middleware lines from contract Block 1
${PYTHON_BIN} -c "
import re
text = open('${PHASE_DIR}/API-CONTRACTS.md', encoding='utf-8').read()
for m in re.finditer(r'###\s+(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)', text):
    method, path = m.groups()
    rest = text[m.end():m.end()+2000]
    auth_match = re.search(r'\`\`\`\w+\n(.*?requireRole.*?)\n', rest, re.DOTALL)
    if auth_match:
        for line in auth_match.group(1).splitlines():
            if 'requireRole' in line or 'requireAuth' in line:
                print(f'{path}\t{line.strip()}'); break
" 2>/dev/null > "${VG_TMP}/contract-auth-lines.txt"

# Verify each auth line exists in actual route file
while IFS=$'\t' read -r ENDPOINT AUTH_LINE; do
  [ -z "$ENDPOINT" ] && continue
  ROUTE_FILE=$(grep -rl "${ENDPOINT}" ${config_code_patterns_api_routes} 2>/dev/null | head -1)
  [ -z "$ROUTE_FILE" ] && continue
  KEY_PART=$(echo "$AUTH_LINE" | grep -oE "requireRole\(['\"][^'\"]+['\"]\)" || true)
  if [ -n "$KEY_PART" ] && ! grep -q "$KEY_PART" "$ROUTE_FILE" 2>/dev/null; then
    echo "  CRITICAL: ${ENDPOINT} — contract says '${KEY_PART}' but route file doesn't contain it"
    COPY_MISMATCHES=$((COPY_MISMATCHES + 1))
  fi
done < "${VG_TMP}/contract-auth-lines.txt"

# FE anti-pattern: toast.error(error.message) without .response.data path
CHANGED_FE=$(git diff --name-only HEAD~${COMMIT_COUNT:-5} HEAD -- "${config_code_patterns_web_pages}" 2>/dev/null)
if [ -n "$CHANGED_FE" ]; then
  BAD_TOAST=$(echo "$CHANGED_FE" | xargs grep -l "toast.*error\.message\b" 2>/dev/null | \
    xargs grep -L "error\.response.*data.*error.*message" 2>/dev/null | head -5)
  if [ -n "$BAD_TOAST" ]; then
    echo "  HIGH: FE reads error.message (AxiosError) instead of error.response.data.error.message"
    COPY_MISMATCHES=$((COPY_MISMATCHES + 1))
  fi
  # FE nested path: response.data.data double-nesting
  DOUBLE_DATA=$(echo "$CHANGED_FE" | xargs grep -n "response\.data\.data\." 2>/dev/null | head -5)
  if [ -n "$DOUBLE_DATA" ]; then
    echo "  WARN: FE accesses response.data.data (double nesting) — check API envelope"
  fi
fi
```

### Tier 4: Runtime auth smoke (if server running)

```bash
if [ -n "$BASE_URL" ]; then
  NEG_FAILURES=0
  while IFS=$'\t' read -r ENDPOINT AUTH_LINE; do
    [ -z "$ENDPOINT" ] && continue
    STATUS=$(curl -sf -o /dev/null -w '%{http_code}' "${BASE_URL}${ENDPOINT}" 2>/dev/null)
    if [ "$STATUS" != "401" ] && [ "$STATUS" != "403" ] && [ "$STATUS" != "404" ]; then
      echo "  CRITICAL: ${ENDPOINT} no-token → ${STATUS} (expected 401/403)"
      NEG_FAILURES=$((NEG_FAILURES + 1))
    fi
  done < "${VG_TMP}/contract-auth-lines.txt"
fi
```

CRITICAL/HIGH → FAIL. MEDIUM → GAPS_FOUND. LOW → logged.
</step>

<step name="5g_performance_check">
## 5g: PERFORMANCE CHECK (config.perf_budgets)

**Skip if:** `perf_budgets` section absent in config.

```bash
# Bundle size check
MAX_BUNDLE_KB=$(awk '/^perf_budgets:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /max_bundle_kb:/{print $2; exit}' .claude/vg.config.md 2>/dev/null)
if [ -n "$MAX_BUNDLE_KB" ]; then
  BUILD_DIR=$(find . -maxdepth 3 \( -name "dist" -o -name "build" -o -name ".next" \) -type d 2>/dev/null | head -1)
  if [ -d "$BUILD_DIR" ]; then
    BUNDLE_KB=$(du -sk "$BUILD_DIR" 2>/dev/null | awk '{print $1}')
    if [ "$BUNDLE_KB" -gt "$MAX_BUNDLE_KB" ]; then
      echo "  WARN: Bundle ${BUNDLE_KB}KB > budget ${MAX_BUNDLE_KB}KB"
    fi
  fi
fi

# Page load time check (if api_response_p95_ms or page_load_s configured)
PAGE_LOAD_S=$(awk '/^perf_budgets:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /page_load_s:/{print $2; exit}' .claude/vg.config.md 2>/dev/null)
if [ -n "$PAGE_LOAD_S" ] && [ -n "$BASE_URL" ]; then
  # Pick 3 critical routes from RUNTIME-MAP (most-elements views)
  CRITICAL_ROUTES=$(${PYTHON_BIN} -c "
import json
from pathlib import Path
rm = json.loads(Path('${PHASE_DIR}/RUNTIME-MAP.json').read_text(encoding='utf-8'))
views = sorted(rm.get('views',{}).items(), key=lambda x: len(x[1].get('elements',[])), reverse=True)[:3]
for url, _ in views: print(url)
" 2>/dev/null)
  for ROUTE in $CRITICAL_ROUTES; do
    LOAD_TIME=$(curl -sf -o /dev/null -w '%{time_total}' "${BASE_URL}${ROUTE}" 2>/dev/null)
    LOAD_INT=$(echo "$LOAD_TIME" | awk '{printf "%d", $1}')
    if [ "$LOAD_INT" -gt "$PAGE_LOAD_S" ]; then
      echo "  WARN: ${ROUTE} load time ${LOAD_TIME}s > budget ${PAGE_LOAD_S}s"
    fi
  done
fi

# N+1 query pattern check
CHANGED_SRC=$(git diff --name-only HEAD~${COMMIT_COUNT:-5} HEAD -- "apps/" "packages/" 2>/dev/null)
if [ -n "$CHANGED_SRC" ]; then
  N_PLUS_1=$(echo "$CHANGED_SRC" | xargs grep -n "await.*\(for\|forEach\|\.map\)" 2>/dev/null | \
    xargs -I{} sh -c 'grep -A5 "{}" 2>/dev/null | grep -l "await\|\.find\|\.findOne\|\.query"' 2>/dev/null | head -5)
  if [ -n "$N_PLUS_1" ]; then
    echo "  WARN: Potential N+1 query pattern (await inside loop)"
  fi

  # MongoDB query efficiency check
  MISSING_LEAN=$(echo "$CHANGED_SRC" | xargs grep -n "\.find\(\\|\.findOne\(" 2>/dev/null | \
    grep -v "\.lean()\|\.toArray()\|\.count()\|\.countDocuments(" | head -5)
  if [ -n "$MISSING_LEAN" ]; then
    echo "  WARN: MongoDB queries without .lean()/.toArray() (memory overhead):"
    echo "$MISSING_LEAN" | sed 's/^/    /'
  fi

  # Large source file check (>50KB)
  LARGE_FILES=$(echo "$CHANGED_SRC" | xargs wc -c 2>/dev/null | awk '$1 > 51200 && !/total$/ {print $2 " (" int($1/1024) "KB)"}' | head -5)
  if [ -n "$LARGE_FILES" ]; then
    echo "  WARN: Large source files (>50KB) — consider splitting:"
    echo "$LARGE_FILES" | sed 's/^/    /'
  fi
fi
```
</step>

<step name="write_report">
## Write SANDBOX-TEST.md

Write `${PHASE_DIR}/{num}-SANDBOX-TEST.md`:

```markdown
---
phase: "{PHASE_NUMBER}"
tested: "{ISO timestamp}"
status: "{PASSED|GAPS_FOUND|FAILED}"
deploy_sha: "{sha}"
environment: "{ENV}"
---

# Sandbox Test Report — Phase {phase}

## 5a Deploy
- SHA: {sha}, Health: {OK|FAIL}

## 5b Contract Verify
- Endpoints: {N}/{total}, Result: {PASS|BLOCK}
- Idempotency (critical domains): {N} checked, {F} failures

## 5c Smoke Check
- Views: {N}/5 match

## 5c Goal Verification
| Goal | Priority | Criteria | Passed | Failed | Status |
|------|----------|----------|--------|--------|--------|

### Fix Loop
- Minor fixes: {N}, Escalated: {N}

## 5d Codegen
- Files: {N}, Tests: {N}

## 5e Regression
- Tests: {passed}/{total}

## 5f Security
- Tier 1 grep: {findings}
- Tier 2 deep: {tool|skipped}
- Tier 3 contract-code verify: {COPY_MISMATCHES} mismatches
- Tier 4 runtime no-token: {NEG_FAILURES} open endpoints

## 5g Performance
- Bundle size: {KB}/{max_bundle_kb}KB
- N+1 patterns: {count}

## Verdict: {PASSED | GAPS_FOUND | FAILED}

Gate (weighted):
- Critical: {N}/{N} (100%), Important: {N}/{N} (80%), Nice-to-have: {N}/{N} (50%)
```

**Verdict COMPUTATION (HARD RULE — tightened 2026-04-17, no AI-written verdicts):**

Before writing SANDBOX-TEST.md, verdict MUST be computed from actual goal JSON results, NOT inferred by the model from context.

```bash
VERDICT_JSON=$(${PYTHON_BIN} - <<'PYEOF'
import json, re, glob, os
from pathlib import Path

phase_dir = os.environ.get('PHASE_DIR')
vg_tmp = os.environ.get('VG_TMP')

tg_path = next(Path(phase_dir).glob('*TEST-GOALS*.md'), None)
if not tg_path:
    print(json.dumps({"error":"TEST-GOALS.md missing","verdict":"FAILED"})); exit(1)

tg = tg_path.read_text(encoding='utf-8')
goal_priority = {}
current = None
for line in tg.splitlines():
    m = re.match(r'^##\s*Goal\s+(G-\d+)', line)
    if m: current = m.group(1)
    mp = re.match(r'^\s*\*\*Priority:\*\*\s*(\w+)', line, re.I)
    if mp and current: goal_priority[current] = mp.group(1).lower()

results = {}
for rf in glob.glob(f"{vg_tmp}/goal-*-result.json"):
    try:
        r = json.load(open(rf, encoding='utf-8'))
        results[r['goal_id']] = r['status']
    except: pass

buckets = {'critical':{'pass':0,'total':0},'important':{'pass':0,'total':0},'nice-to-have':{'pass':0,'total':0}}
for gid, prio in goal_priority.items():
    p = prio if prio in buckets else 'important'
    buckets[p]['total'] += 1
    if results.get(gid) == 'PASSED': buckets[p]['pass'] += 1

def pct(b): return 100.0 * b['pass'] / b['total'] if b['total'] else 100.0

cp, ip, np_ = pct(buckets['critical']), pct(buckets['important']), pct(buckets['nice-to-have'])
verdict = 'PASSED'; reasons = []
if cp < 100.0: verdict='FAILED'; reasons.append(f"critical {cp:.0f}%<100%")
elif ip < 80.0: verdict='GAPS_FOUND'; reasons.append(f"important {ip:.0f}%<80%")
elif np_ < 50.0: verdict='GAPS_FOUND'; reasons.append(f"nice {np_:.0f}%<50%")

print(json.dumps({"verdict":verdict,"reasons":reasons,"buckets":buckets}))
PYEOF
)
VERDICT=$(echo "$VERDICT_JSON" | ${PYTHON_BIN} -c "import json,sys;print(json.load(sys.stdin)['verdict'])")
echo "$VERDICT_JSON" > "${PHASE_DIR}/.verdict-computed.json"
echo "Computed verdict: $VERDICT"
```

**Writer MUST copy $VERDICT into SANDBOX-TEST.md header/body verbatim. Do NOT re-evaluate.**

Commit all artifacts.
</step>

<step name="complete">
**⛔ Test artifact cleanup (tightened 2026-04-17 — dọn rác test run):**

Test sinh ra nhiều screenshot/html/json tạm — dọn sau khi verdict đã commit.

| Loại | Path | Action |
|------|------|--------|
| Goal PASS/FAIL evidence | `${SCREENSHOTS_DIR}/{phase}-goal-*.png` | GIỮ |
| Generated .spec.ts | `${GENERATED_TESTS_DIR}/{phase}-goal-*.spec.ts` | GIỮ |
| Playwright test-results | `**/test-results/`, `**/playwright-report/` | XOÁ |
| Root-leaked screenshots | `./*.png`, `./screenshot-*.png` | XOÁ |
| Probe retries (>1) | `${SCREENSHOTS_DIR}/*-probe-*-retry[2-9]*.png` | XOÁ |
| Goal result JSONs | `${VG_TMP}/goal-*-result.json`, baseline | XOÁ |
| MCP snapshots | `**/.playwright-mcp/`, `./snapshot-*.yaml` | XOÁ |
| Videos/traces | `**/*.webm`, `**/trace.zip` | XOÁ nếu PASSED, GIỮ nếu FAILED |

```bash
echo "=== Test cleanup ==="

find . -type d \( -name "test-results" -o -name "playwright-report" -o -name ".playwright-mcp" \) \
  -not -path "./node_modules/*" -not -path "./.git/*" \
  -exec rm -rf {} + 2>/dev/null

rm -f ./*.png ./screenshot-*.png ./snapshot-*.yaml 2>/dev/null

if [ -d "${SCREENSHOTS_DIR}" ]; then
  find "${SCREENSHOTS_DIR}" -name "*-probe-*-retry[2-9]*.png" -delete 2>/dev/null
  find "${SCREENSHOTS_DIR}" -name "*-probe-*-retry[1-9][0-9]*.png" -delete 2>/dev/null
fi

rm -f "${VG_TMP}"/goal-*-result.json "${VG_TMP}"/goal-*-baseline.json 2>/dev/null
rm -f "${VG_TMP}"/vg-crossai-${PHASE_NUMBER}-*.md 2>/dev/null

if [ "$VERDICT" = "PASSED" ] || [ "$VERDICT" = "GAPS_FOUND" ]; then
  find . -type f \( -name "*.webm" -o -name "trace.zip" \) \
    -not -path "./node_modules/*" -not -path "./.git/*" -delete 2>/dev/null
else
  echo "Verdict=$VERDICT — keeping videos/traces for debug"
fi

echo "Cleanup complete. Evidence preserved: SANDBOX-TEST.md, goal-*.png, *.spec.ts"
```

**Optional GSD state + roadmap update (if GSD installed):**
```bash
if [ -x "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" ]; then
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" state update-phase \
    --phase "${PHASE_NUMBER}" --status "in_progress" --pipeline-step "test-complete" \
    --test-verdict "$VERDICT" 2>/dev/null || true
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" roadmap update-phase \
    --phase "${PHASE_NUMBER}" --status "tested" 2>/dev/null || true
fi
```

Display:
```
Test complete for Phase {N}.
  Deploy: {OK}
  Contract: {PASS}
  Smoke: {N}/5 match
  Goals: {passed}/{total} (critical: {N}/{N}, important: {N}/{N})
  Fix loop: {minor_fixed} fixed, {escalated} escalated
  Regression: {passed}/{total}
  Security: {verdict}
  Verdict: {PASSED | GAPS_FOUND | FAILED}
  Next: accept (human UAT)
```
</step>

</process>

<success_criteria>
- Deploy successful, services healthy
- Runtime contract verify passed (curl + jq)
- Smoke check confirms RUNTIME-MAP accuracy
- Goals verified against known paths from RUNTIME-MAP.json
- MINOR fixes applied, MODERATE/MAJOR escalated to REVIEW-FEEDBACK.md
- Codegen produced .spec.ts per goal group
- Regression tests pass
- Security audit completed
- SANDBOX-TEST.md with weighted goal-based verdict
</success_criteria>
