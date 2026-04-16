---
name: "vg-review"
description: "Post-build review — code scan + browser discovery + fix loop + goal comparison → RUNTIME-MAP"
metadata:
  short-description: "Full review for a phase — same depth as Claude /vg:review"
---

<codex_skill_adapter>
## A. Skill Invocation
- This skill is invoked by mentioning `$vg-review`.
- Treat all user text after `$vg-review` as arguments: `{{PHASE}} [--resume] [--skip-scan] [--skip-discovery] [--fix-only] [--discovery-only] [--evaluate-only] [--retry-failed] [--full-scan] [--skip-crossai] [--with-probes]`
- If no phase given, ask: "Which phase? (e.g., 7.6)"

## B. AskUserQuestion → request_user_input Mapping
GSD workflows use `AskUserQuestion` (Claude Code syntax). Translate to Codex `request_user_input`:
- AskUserQuestion(question="X") → request_user_input(prompt="X")

## C. Browser Tools
Use whatever browser tools your environment provides. This workflow describes WHAT to do, not which tool to call.
If you have a browser: navigate, click, fill forms, take screenshots, check console.
If you don't: use curl for API checks + code inspection for UI review.

## D. Playwright Lock (multi-session safety)
Codex has its own playwright1-5 MCP pool (separate user-data-dirs from Claude Code).
Use the shared lock manager with `pool=codex` to prevent parallel Codex sessions conflicting:

**BEFORE any browser interaction**, claim a lock with auto-release on exit:
```bash
SESSION_ID="codex-{phase}-review-$$"
PLAYWRIGHT_SERVER=$(bash "${HOME}/.claude/playwright-locks/playwright-lock.sh" claim "$SESSION_ID" codex)
# Auto-release on any exit (normal/error/kill) — prevents lock leak
trap "bash '${HOME}/.claude/playwright-locks/playwright-lock.sh' release \"$SESSION_ID\" codex 2>/dev/null" EXIT INT TERM
# Use $PLAYWRIGHT_SERVER for all MCP tool calls: mcp__playwright1__*, mcp__playwright2__*, etc.
```
If claim fails (all 5 locked) → BLOCK. Lock manager auto-sweeps stale locks (TTL 1800s + dead-PID check) on every claim — genuine contention if still full. Do NOT cleanup other sessions' locks manually.
Do NOT touch Claude Code's `playwright1.lock`-`playwright5.lock` (pool: claude) — separate pool.

Note: `codex exec` subprocesses do NOT have MCP playwright access — only the main Codex session does.
</codex_skill_adapter>

<rules>
1. **SUMMARY*.md required** — build must have completed. Missing = BLOCK.
2. **API-CONTRACTS.md required** — contracts must exist. Missing = BLOCK.
3. **Discovery-first** — AI explores the running app organically. No hardcoded checklists. No pre-scripted paths.
4. **Bấm → Nhìn → List → Đánh giá** — at every view: snapshot, evaluate data + actions, click each, observe result.
5. **Fix in review, verify in test** — review handles discovery + fix. Test handles clean goal verification only.
6. **RUNTIME-MAP is ground truth** — produced from actual browser interaction, not code guessing.
7. **Flexible format** — AI chooses best representation per page (tree, list, flow). No mandated table structure.
8. **State persistence** — discovery progress saved to discovery-state.json. Resumable after failure.
9. **Exploration limits** — max 50 actions/view, 200 total, 30 min wall time. Prevents runaway.
10. **Zero hardcode** — no endpoint, role, page name, or project-specific value in this workflow. All values from config or runtime observation.
11. **Profile enforcement (UNIVERSAL)** — every `<step>` MUST, as FINAL action:
    `touch "${PHASE_DIR}/.step-markers/{STEP_NAME}.done"`.
    Preflight in create_task_tracker: run `${PYTHON_BIN} .claude/scripts/filter-steps.py --command .claude/commands/vg/review.md --profile $PROFILE --output-ids` → list of applicable steps. Task count MUST match. Browser discovery (phase2) skipped for backend-only/cli/library profiles.
    Cross-CLI markers: if Claude already ran some steps, their markers exist. Codex should skip those and only run uncovered applicable steps.
</rules>

## Profile preflight (run BEFORE phase 1)

```bash
PROFILE=$(${PYTHON_BIN} -c "
import re
for line in open('.claude/vg.config.md', encoding='utf-8'):
    m = re.match(r'^profile:\s*[\"\']?([^\"\'#\s]+)', line)
    if m: print(m.group(1)); break
")
if [ -z "$PROFILE" ]; then
  echo "⛔ config.profile missing. Run /vg:init via Claude first."
  exit 1
fi

EXPECTED_STEPS=$(${PYTHON_BIN} .claude/scripts/filter-steps.py \
  --command .claude/commands/vg/review.md \
  --profile "$PROFILE" \
  --output-ids)

MARKER_DIR="${PHASE_DIR}/.step-markers"
mkdir -p "$MARKER_DIR"

echo "Profile: $PROFILE"
echo "Applicable steps: $EXPECTED_STEPS"
```

**CRITICAL — Codex section names ≠ Claude step names.** Use this explicit mapping so markers match Claude's expected names (cross-CLI handoff works):

| Codex section (this skill) | Marker filename (matches Claude review.md) |
|---|---|
| Phase 1: CODE SCAN (1a + 1b) | `phase1_code_scan.done` |
| Phase 1.5: GRAPHIFY IMPACT ANALYSIS | `phase1_5_ripple_and_god_node.done` |
| Phase 2: BROWSER DISCOVERY (2a + 2b + 2c + 2d combined) | `phase2_browser_discovery.done` |
| Phase 3: FIX LOOP (3a-3e) | `phase3_fix_loop.done` |
| Phase 4: GOAL COMPARISON (4a-4e) | `phase4_goal_comparison.done` |
| CrossAI review section | `crossai_review.done` |
| Write artifacts section | `write_artifacts.done` |
| Complete section | `complete.done` |

Write marker when a WHOLE phase completes (not per-subsection):
```bash
touch "${MARKER_DIR}/phase1_code_scan.done"   # after 1a + 1b both done
touch "${MARKER_DIR}/phase2_browser_discovery.done"   # after 2a-2d all done
# etc.
```

**Skip markers for skipped phases** (per profile or flag): don't write marker if phase not executed. Step-9 marker check in Claude expects this exact behavior.

**Sub-flag markers** also used internally, do NOT conflict with phase-level ones:
- `--discovery-only`: writes only up to `phase2_browser_discovery.done`, then stops
- `--evaluate-only`: expects `phase2_browser_discovery.done` already exists (from Codex discovery run), writes `phase3_fix_loop.done` + `phase4_goal_comparison.done`

<objective>
Post-build review. Combines static code scan + live browser discovery + iterative fix loop + goal comparison.

Pipeline: specs → scope → blueprint → build → **review** → test → accept

4 Phases:
- Phase 1: CODE SCAN — grep contracts + count elements (fast, automated, <10 sec)
- Phase 2: BROWSER DISCOVERY — organic exploration → RUNTIME-MAP
- Phase 3: FIX LOOP — errors found → fix → redeploy → re-discover (max 3 iterations)
- Phase 4: GOAL COMPARISON — map TEST-GOALS to discovered paths → weighted gate
</objective>

<process>

## Config Loading

Read `.claude/vg.config.md` — parse YAML frontmatter.

**Resolve ENV (never hardcode "sandbox"):**
1. If `--local` in arguments → `ENV=local`
2. If `--sandbox` in arguments → `ENV=sandbox`
3. Else → `ENV = config.step_env.sandbox_test` (review step default)
   - vg.config.md has `step_env.sandbox_test: "local"` → ENV=local by default
   - Only `ENV=sandbox` if that's what config explicitly sets

From resolved `ENV`, extract:
- `credentials[ENV]` — login URLs, emails, passwords per role
- `services[ENV]` — health checks
- `environments[ENV]` — deploy commands, project path, run_prefix
- `paths` — planning dir, phases dir, screenshots dir
- `scan_patterns` — grep patterns for element counting
- `code_patterns` — where API routes and web pages live

**VERIFY before any browser action:**
Print: `ENV resolved to: {ENV} | Domain: {credentials[ENV][0].domain}`
If ENV=sandbox but user ran without --sandbox flag → WARN: "Using sandbox env from config. Add --local to override."
If ENV=local but app not reachable at domain → BLOCK: "Local app not running. Start with: {environments.local.dev_command}"

<step name="0_parse_and_validate">
Parse arguments: phase_number, flags (--resume, --skip-scan, --skip-discovery, --fix-only, --discovery-only, --evaluate-only, --retry-failed, --full-scan, --skip-crossai, --with-probes).

**--evaluate-only mode:**
Requires: ${PHASE_DIR}/nav-discovery.json AND at least 1 scan-*.json already exist.
Missing → BLOCK: "Run discovery first: `$vg-review {phase} --discovery-only` to generate scan data."
Print: "Evaluate mode: requires prior discovery run. Reading existing scan data."
Skips Phase 1 (code scan) + Phase 2 (browser discovery). Starts at Phase 2b-3 (collect + merge scan results) → Phase 3 (fix loop) → Phase 4 (goal comparison).

**--discovery-only mode:**
Run Phase 1 (code scan) + Phase 2 (browser discovery: Pass 1 navigator + Pass 2a goals + Pass 2b element scan).
Write all output JSONs: nav-discovery.json, discovery-state.json, scan-*.json, probe-*.json, RUNTIME-MAP.json, GOAL-COVERAGE-MATRIX.md.
STOP after Phase 2 — do NOT enter Phase 3 (fix loop) or Phase 4 (goal comparison).
Print: "Discovery complete. Run `/vg:review {phase} --evaluate-only` in Claude to evaluate + fix."

**--retry-failed mode:**
Re-scan ONLY views mapped to failed/blocked goals.
Requires: ${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md + RUNTIME-MAP.json already exist.
Missing → BLOCK: "Run `/vg:review {phase}` or `$vg-review {phase}` first to generate initial artifacts."

Parse GOAL-COVERAGE-MATRIX.md → collect goals where status ≠ READY (BLOCKED, UNREACHABLE, FAILED, PARTIAL).
If none → print "All goals already READY. Nothing to retry." → stop.

Parse RUNTIME-MAP.json → for each failed goal_id:
  start_view = goal_sequences[goal_id].start_view
RETRY_VIEWS[] = unique(all start_views), with roles from RUNTIME-MAP views[start_view].role

Print: "Retry mode: {N} failed goals → {M} views to re-scan: {RETRY_VIEWS[]}"

Skip Phase 1 (code scan). Skip Pass 1 navigator.
In Pass 2b (element scan): use RETRY_VIEWS[] as unvisited_views (instead of reading discovery-state.json).
Continue normally to Pass 2b collection → then stop (print results, do NOT run Phase 3 fix loop).
Print: "Re-scan complete. Run `/vg:review {phase} --evaluate-only` in Claude to fix + verify."

Find phase directory in `.planning/phases/` (try both "7.6" and "07.6" formats).

Validate:
- `${PHASE_DIR}/SUMMARY*.md` exists → build completed
- `${PHASE_DIR}/API-CONTRACTS.md` exists → contracts available

Missing → BLOCK with guidance.

**Update GSD STATE.md (optional — if GSD installed):**
```bash
if [ -x "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" ]; then
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" state update-phase \
    --phase "${PHASE_NUMBER}" --status "in_progress" --pipeline-step "reviewing" 2>/dev/null || true
fi
```
</step>

<step name="phase1_code_scan">
## Phase 1: CODE SCAN (automated, <10 sec)

**If --skip-scan, skip this phase.**

### 1a: Contract Verify (grep)

Read API-CONTRACTS.md. For each endpoint:
```
For each endpoint in API-CONTRACTS.md:
  Grep backend at ${config.code_patterns.api_routes} (from vg.config.md)
  Grep frontend at ${config.code_patterns.web_pages} (from vg.config.md)
  Use scan_patterns.${config.scan_patterns.stack} for element detection
```
- Report mismatches

Result: 0 mismatches → PASS. Mismatches → WARNING.

### 1b: Element Inventory (grep — reference data, NOT gate)

Count UI elements using scan_patterns from config:
```
For each source file in code_patterns.web_pages:
  Count: modals, tabs, tables, forms, dropdowns, actions, tooltips
```

Write `${PHASE_DIR}/element-counts.json` — reference data for discovery.

### 1c: i18n Key Resolution Check (config-gated)

**Skip if:** `config.i18n.enabled` is false/absent OR `config.i18n.locale_dir` empty.

Verify every i18n key used in phase-changed FE files resolves to a translation string.
Missing keys = user sees raw key like `dashboard.title` instead of text.

```bash
I18N_ENABLED=$(awk '/^i18n:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /enabled:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '" ')
if [ "$I18N_ENABLED" = "true" ]; then
  LOCALE_DIR=$(awk '/^i18n:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /locale_dir:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '"')
  DEFAULT_LOCALE=$(awk '/^i18n:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /default_locale:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '"' || echo "en")
  KEY_FN=$(awk '/^i18n:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /key_function:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '"' || echo "t")

  CHANGED_FE=$(git diff --name-only HEAD~${COMMIT_COUNT:-5} HEAD -- "${config_code_patterns_web_pages}" 2>/dev/null)
  if [ -n "$CHANGED_FE" ] && [ -d "$LOCALE_DIR" ]; then
    I18N_KEYS=$(echo "$CHANGED_FE" | xargs grep -ohE "${KEY_FN}\(['\"]([^'\"]+)['\"]\)" 2>/dev/null | \
      grep -oE "['\"][^'\"]+['\"]" | tr -d "'" | tr -d '"' | sort -u)
    LOCALE_FILE=$(find "$LOCALE_DIR" -path "*/${DEFAULT_LOCALE}*" -name "*.json" 2>/dev/null | head -1)
    MISSING_KEYS=0
    if [ -n "$LOCALE_FILE" ] && [ -n "$I18N_KEYS" ]; then
      while IFS= read -r KEY; do
        [ -z "$KEY" ] && continue
        EXISTS=$(${PYTHON_BIN} -c "
import json, sys
from pathlib import Path
data = json.loads(Path('$LOCALE_FILE').read_text())
keys = '$KEY'.split('.')
ref = data
for k in keys:
    if isinstance(ref, dict) and k in ref: ref = ref[k]
    else: print('MISSING'); sys.exit(0)
print('OK')
" 2>/dev/null)
        [ "$EXISTS" = "MISSING" ] && MISSING_KEYS=$((MISSING_KEYS + 1))
      done <<< "$I18N_KEYS"
    fi
    echo "i18n check: $(echo "$I18N_KEYS" | wc -l) keys, ${MISSING_KEYS} missing"
  fi
fi
```

Result: `MISSING_KEYS > 0` → GAPS_FOUND (not block).
</step>

<step name="phase1_5_ripple_and_god_node">
## Phase 1.5: GRAPHIFY IMPACT ANALYSIS

**Purpose**: cross-module ripple + god node coupling. Retroactive safety net matching Claude's build-time caller graph.

### Prereq: graphify active check (bash)

```bash
GRAPHIFY_ENABLED=$(awk '/^graphify:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /enabled:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '"')
GRAPHIFY_GRAPH_PATH=$(awk '/^graphify:/{f=1; next} f && /^[a-z_]+:/{f=0} f && /graph_path:/{print $2; exit}' .claude/vg.config.md 2>/dev/null | tr -d '"' || echo "graphify-out/graph.json")

if [ "$GRAPHIFY_ENABLED" != "true" ] || [ ! -f "$GRAPHIFY_GRAPH_PATH" ]; then
  echo "ℹ Graphify not available — skipping Phase 1.5"
  touch "${PHASE_DIR}/.step-markers/phase1_5_ripple_and_god_node.done"
  # skip to Phase 2
fi
```

### A. Collect phase's changed files (bash)

```bash
PHASE_START_TAG=$(git tag --list "vg-build-${PHASE_NUMBER}-wave-*-start" | sort -V | head -1)
if [ -n "$PHASE_START_TAG" ]; then
  CHANGED_FILES=$(git diff --name-only "$PHASE_START_TAG" HEAD | sort -u)
else
  CHANGED_FILES=$(git diff --name-only $(git merge-base HEAD main) HEAD | sort -u)
fi

# Filter to source files only
CHANGED_SRC=$(echo "$CHANGED_FILES" | grep -vE '^\.(planning|claude|codex)/|/node_modules/|/dist/|/build/|/target/|^graphify-out/' || true)
echo "$CHANGED_SRC" > "${PHASE_DIR}/.ripple-input.txt"
echo "Phase changed $(echo "$CHANGED_SRC" | wc -l) source files"
```

### B. Ripple analysis (bash — hybrid script, no MCP)

Graphify MCP alone misses TS path-alias imports. Script `build-caller-graph.py --changed-files-input` combines graphify + git grep.

```bash
${PYTHON_BIN} .claude/scripts/build-caller-graph.py \
  --changed-files-input "${PHASE_DIR}/.ripple-input.txt" \
  --config .claude/vg.config.md \
  --graphify-graph "$GRAPHIFY_GRAPH_PATH" \
  --output "${PHASE_DIR}/.ripple.json"
```

Script output `.ripple.json` has schema: `{mode: "ripple", ripples: [{changed_file, exports_at_risk, callers[{file, line, symbol, source}]}], affected_callers[]}`. Each caller is a file outside phase's changed list that imports/uses a symbol exported by a changed file.

### C. God node coupling check (bash — Python API, no MCP)

```bash
${PYTHON_BIN} - <<'PY' > "${PHASE_DIR}/.god-nodes.json"
import json
from graphify.analyze import god_nodes
from graphify.build import build_from_json
from networkx.readwrite import json_graph
from pathlib import Path
data = json.loads(Path("${GRAPHIFY_GRAPH_PATH}").read_text(encoding="utf-8"))
G = json_graph.node_link_graph(data, edges="links")
gods = god_nodes(G)[:20]
print(json.dumps([{"label": g.get("label"), "source_file": g.get("source_file"), "degree": g.get("degree")} for g in gods], indent=2))
PY
```

Cross-check phase diff for new import lines pointing to any god node's source_file — flag as coupling warning.

### D. Write `${PHASE_DIR}/RIPPLE-ANALYSIS.md`

Sections: High-Severity Ripples | Low-Severity Ripples | God Node Coupling Warnings | Summary (counts + action hint).

### E. Inject into Phase 2 + Phase 4

- Phase 2: read `RIPPLE-ANALYSIS.md` HIGH rows, prioritize those caller URLs first in browser queue
- Phase 4 goal comparison: if goal touches a HIGH-ripple caller NOT browsed → mark UNVERIFIED

### Fallback (graphify unavailable)

Skip with warning + write empty RIPPLE-ANALYSIS.md stub. Final action: `touch "${PHASE_DIR}/.step-markers/phase1_5_ripple_and_god_node.done"`
</step>

<step name="phase2_browser_discovery">
## Phase 2: BROWSER DISCOVERY (organic)

**If --skip-discovery, skip to Phase 4.**
**If --resume, load discovery-state.json and continue from queue.**

### Browser Tools

**Codex has MCP Playwright connected.** Use Playwright MCP tools for all browser interaction:
- `browser_navigate` → go to URL (only for initial login/domain switch)
- `browser_snapshot` → read current page state (accessibility tree)
- `browser_click` → click element by ref or text
- `browser_fill_form` → fill input fields
- `browser_take_screenshot` → capture evidence
- `browser_console_messages` → check for errors after every action
- `browser_network_requests` → monitor API calls (method, url, status)
- `browser_wait_for` → wait for element/condition

**Every action must be followed by:** snapshot + console check + network check (3-layer).

### Element Interaction Protocol (applies to ALL passes)

When interacting with elements during any pass, follow these exhaustive rules:

**SNAPSHOT PRUNE RULE (DEFAULT — disabled if --full-scan):**
IF --full-scan: skip this rule entirely. Use full snapshot for all interactions.
Run browser_evaluate ONCE at session start:
  "const s=['main','[role=\"main\"]','#main-content','.main-content','#content','.content-area','[data-main]'];
   return s.find(sel=>document.querySelector(sel))||null;"
→ MAIN_SELECTOR = result
For every browser_snapshot: build working element list ONLY from inside MAIN_SELECTOR.
SKIP: sidebar nav, header, footer, breadcrumbs, [aria-label="sidebar"].
If no MAIN_SELECTOR: use full snapshot. Eliminates 50-70% redundant elements per snapshot.
EXCEPTIONS — suspend MAIN_SELECTOR, use FULL snapshot:
  modal/dialog/drawer opened | toast/notification after action. Resume after modal closes.

**AFTER EVERY CLICK:**
- Re-snapshot → check for NEW elements not previously listed (within MAIN_SELECTOR only)
- If new elements appeared (accordion expand, inline content, lazy load) → add to working list, continue iteration

**Element-specific rules:**

| Element Type | Action |
|---|---|
| button/link/menuitem/accordion | Click → snapshot → record outcome (modal? navigate? expand?) |
| tab/segmented-control/pill-nav | Click EACH tab → for each tab panel, list ALL elements → interact with each (recurse like modal) |
| dropdown/menu/popover (NOT select) | Click to open → list ALL items → click EACH item → record outcome → close/re-open between items |
| textbox/input/textarea | Read attributes → fill test data: email→"scan-test@example.com", number→"9.99", url→"scan-test.example.com", phone→"+1234567890", date→"2026-01-15", name→"Scan Test Item", other→"scan-test-data" |
| select/combobox | Click open → record all options (count + first 5) → select first non-placeholder |
| checkbox/radio/switch/toggle | Toggle → record state change → toggle back |
| table/list with rows | Scroll table container → count rows → click actions on FIRST row only (sample) → recurse if opens detail/modal |
| disabled/hidden element | Record state → try to enable (select checkbox/row nearby) → if enables, interact → if not, mark stuck with reason |
| form (inputs + submit) | Fill ALL fields → submit → record result + API response + toast → if confirm dialog: Cancel first, re-trigger, OK second |
| modal/dialog (after open) | List ALL elements inside → interact with each (full recurse) → close after done |

**HARD RULES:**
- Visit 100% of elements — including dynamically appended ones after clicks
- Recurse into every modal/dialog AND every tab panel (each tab = fresh element list)
- Click every item in every dropdown/action menu
- Re-snapshot after EVERY click, append new elements to working list
- Attempt to enable disabled elements before marking stuck
- Record console errors + network requests after EVERY action
- If you cannot interact with an element, add it to "stuck" with reason — do NOT silently skip

### 2a: Deploy + Environment Prep

Deploy using `environments[ENV]` from config (never hardcode):
```
run_prefix = environments[ENV].run_prefix          # "ssh vollx" or ""
project_path = environments[ENV].project_path      # "/home/vollx/vollxssp" or ""
deploy = environments[ENV].deploy

1. If deploy.pre exists: run deploy.pre (e.g. git push)
2. Run: {run_prefix} "cd {project_path} && {deploy.build}"
3. Run: {run_prefix} "{deploy.restart}"
4. Health check: {run_prefix} "{deploy.health}"
5. If health fail → rollback using deploy.rollback → PRE-FLIGHT BLOCK (see below)
```

### 2a-preflight: INFRASTRUCTURE READINESS GATE

**Review fix loop can only fix CODE bugs. Infra failures (missing config, app down, domain unreachable) must be fixed BEFORE review can work.**

Pre-flight checklist (all must pass):
```
[ ] Build succeeded (exit 0, no compile errors)
[ ] Restart succeeded, service running
[ ] Health endpoint(s) return 200 — all in config.services[ENV]
[ ] All role domains from config.credentials[ENV] resolve (no ERR_CONNECTION)
[ ] At least 1 role can login
```

If ANY fails → BLOCK review with diagnostic + fix guidance:
```
⛔ PRE-FLIGHT FAILED — review cannot proceed.
The review step fixes code bugs, not infrastructure.

Issues: {list with category: Build / Health / Domain / Login + specific error}

Fix categories:
  Build failure      → Missing files (ecosystem.config.js, .env), compile errors, bad tsconfig
  Health endpoint    → Service crashed: check logs. Missing env var, DB down, port conflict
  Domain unreachable → /etc/hosts or dev proxy (local) | DNS/HAProxy (sandbox)
  Login failure      → DB seed not run, user missing, JWT secret unset

Next actions — choose scenario that matches your error:

First: cat .planning/phases/{phase}/deploy-review.json   # identify exact error

Scenario A — Deploy config WRONG (pm2 but no ecosystem.config.js, bad dev_command, non-existent health):
  Fix:  edit .claude/vg.config.md → environments.{ENV}.deploy.* + services.{ENV}
        or: /vg:init        (interactive wizard — requires Claude)
  Then: $vg-review {phase}

Scenario B — Service crashed / code error (500s, stack trace, port conflict):
  Fix:  check logs (pm2 logs / journalctl / dev output), fix code
  Then: $vg-review {phase} --retry-failed      (5-10× faster, only failed views)

Scenario C — Feature NOT BUILT (UNREACHABLE — code confirmed missing):
  Fix:  /vg:build {phase} --gaps-only       (requires Claude — build is Claude-only)
  Then: $vg-review {phase} --retry-failed

Scenario C2 — Code EXISTS but NOT SCANNED (NOT_SCANNED — multi-step wizard / orphan route):
  Fix:  /vg:test {phase}                    (codegen walks wizard, fills steps, verifies goal)
     OR: $vg-review {phase} --retry-failed  (fresh re-scan of only failed views)
  DO NOT use --gaps-only — code already exists.

Scenario D — Auth/DB setup missing (login 500, seed user missing, JWT invalid):
  Fix:  run project seed (pnpm db:seed), verify .env secrets
  Then: $vg-review {phase} --retry-failed

Scenario E — Cross-CLI (cheaper — Codex discovers, Claude evaluates):
  Discovery:  $vg-review {phase} --retry-failed --discovery-only
  Evaluate:   /vg:review {phase} --evaluate-only    (Claude reads scan JSONs, evaluates + fixes)

Verify before any re-run:
  curl {services[ENV][0].health}                  # must return 200
  curl -I https://{credentials[ENV][0].domain}    # NOT ERR_CONNECTION
```

Only when all pre-flight checks pass → proceed to seed + login + Phase 2b.

### 2b-0: Seed Data (if configured)
If config.environments[ENV].seed_command is non-empty:
  Run: ${run_prefix} "cd ${project_path} && ${seed_command}"
  Verify exit 0. If seed fails → WARN (not block), proceed with whatever data exists.
  Purpose: diverse data for discovery (empty DB = fewer views/states found).

Login per role from config.credentials[ENV]:
```
For each role:
  1. browser_navigate → https://{role.domain}/login
  2. browser_fill_form → email + password fields
  3. browser_click → submit button
  4. browser_wait_for → dashboard loaded
```

Initialize tracking:
```
Load TEST-GOALS.md → create GOAL-COVERAGE-MATRIX.md (all ⬜ UNTESTED)
Initialize RUNTIME-MAP.json
Initialize discovery-state.json

Load .planning/KNOWN-ISSUES.json (if exists):
  Filter issues for current phase
  Display: "Known issues that may be fixable here: {list}"
```

#### PASS 1: NAVIGATOR (main model, 3-layer — includes code-registered routes)

Purpose: Build URL map. Sidebar DOM alone misses sub-routes registered in router config
but not surfaced on menu → they are marked UNREACHABLE incorrectly. Layer 0 closes this gap
via config-driven code scan. Main model does browser layers because only it has MCP access.

```
LAYER 0 — Registered routes from code (PURE CONFIG-DRIVEN, no stack defaults):

  Workflow is engine only. Project declares HOW routes live in its code via
  vg.config.md. If no config present → skip layer 0 + warn (sidebar-only risk).

  Config keys (pick either source, or both):
    code_patterns.frontend_routes   — glob to route declaration files
    code_patterns.route_path_regex  — regex with capture group yielding path
    graphify.route_predicate        — regex matching graphify node (label/type/file)
    graphify.route_path_extract     — regex with capture group extracting path

  Algorithm:
    REGISTERED_ROUTES = []
    IF graphify.route_predicate AND graphify.route_path_extract AND graph exists:
      For each node in graph where predicate matches (label|type|file):
        Apply route_path_extract regex, collect capture group 1
    ELSE IF code_patterns.frontend_routes AND code_patterns.route_path_regex:
      grep -rhoE "$route_path_regex" $frontend_routes glob
      Collect capture group 1 from each hit
    ELSE:
      echo "⚠ Route discovery not configured in vg.config.md."
      echo "  Sidebar-only scan → sub-routes không trong menu sẽ bị mark UNREACHABLE sai."
      echo "  Add one of the two source blocks above to fix."

    Deduplicate REGISTERED_ROUTES.

LAYER 1 — Sidebar extraction (per role):
  For each role in config.credentials[ENV]:
    1. Login → browser_snapshot → read sidebar/nav menu
    2. Extract ALL visible navigation URLs from sidebar
    3. Write immediately, do NOT explore further

LAYER 2 — Resolve :id params only (applied to BOTH sidebar + registered):
  For each URL containing :id / :slug / dynamic segment:
    1. Navigate to the list page
    2. browser_snapshot → find first row → extract real URL
    3. Navigate back

LAYER 3 — Visit hidden_but_registered routes:
  For each route in REGISTERED_ROUTES not in sidebar views:
    1. browser_navigate directly (access_via: direct_url)
    2. Verify not redirected to login/403 → if redirected, record reason
    3. Otherwise add to views list with source: registered_hidden

BANNED in Pass 1:
  - Opening modals
  - Clicking action buttons
  - Following pagination
  - Exploring nested routes beyond the sources above
  - Filling forms

After all layers:
  Write ${PHASE_DIR}/nav-discovery.json:
  {
    "views": [
      { "url": "/sites",         "roles": ["admin", "publisher"], "source": "sidebar" },
      { "url": "/sites/123",     "roles": ["publisher"], "resolved_from": "/sites/:id", "source": "sidebar" },
      { "url": "/audit-log",     "roles": ["admin"], "source": "registered_hidden", "access_via": "direct_url" },
      ...
    ],
    "redirected":           { "/settings/billing": "/403" },
    "missing_route_config": false,
    "generated_at":         "{ISO timestamp}"
  }

  If missing_route_config = true, scanner phase downstream must flag UNREACHABLE goals
  as "likely_hidden" rather than authoritative — config gap prevents full discovery.

Max actions: 50 for browser layers. Layer 0 (code scan) does not count.
```

**FLUSH_RULE:** After view-assignments.json (or nav-discovery.json) is written to disk, discard the view list
from working memory. Re-read from file when needed for scanner dispatch. This prevents
stale in-memory state if navigator is re-run.

#### PASS 2a: GOAL EXPLORATION (goal-driven, sequential, with mutations)

Purpose: For each goal, plan and execute a multi-step action chain. Record every step as replayable sequence.

```
FOR each goal in TEST-GOALS (sorted by dependency — no-deps first):
  
  1. Read goal: success criteria, mutation evidence, priority
  
  2. Plan: which view to start, what actions to perform
     Use Pass 1 navigation graph to find starting point
  
  3. Execute step-by-step, recording every action:
     
     steps = []
     WHILE goal not verified AND step_count < 20:
       
       // OBSERVE current state
       Snapshot → read what's on screen
       Check console messages
       Check network requests
       
       // DECIDE next action to advance toward goal
       
       // ACT
       Perform action (click, fill, select, wait, etc.)
       Record step: { do: "{action}", selector: "{from snapshot}", label: "{text}", value?: "{if fill}" }
       
       // OBSERVE result (3-layer: UI + network + console)
       Snapshot → what changed on screen?
       Network → what API calls fired? Status codes? Response shapes?
       Console → new errors since last check?
       
       Record: { observe: "{what_changed}", network: [{method, url, status}], console_errors: ["{messages}"] }
       
       // CHECK: goal criteria met?
       IF all success criteria satisfied AND no new console errors:
         Record: { assert: "{criterion}", passed: true }
         → goal VERIFIED
         Break
       
       IF stuck (same state 3 times):
         → goal FAILED, save partial sequence
         Break
     
     // SAVE primary sequence
     goal_sequences[goal_id] = {
       start_view, steps[], result: "passed|failed",
       evidence: [screenshot paths],
       probes: []
     }
     
     // PROBE VARIATIONS (only if primary sequence PASSED and goal involves mutation)
     IF goal PASSED AND goal has mutation steps (fill/select/submit):
       
       probes = []
       
       // Probe 1: EDIT — modify 1-2 fields of the just-created record, re-submit
       IF the goal created/updated a record:
         Navigate back to same form (edit mode if available)
         Change 1-2 field values (different valid data)
         Submit → observe UI + network + console
         Record probe: { type: "edit", changed_fields: [...], result, network[], console_errors[] }
       
       // Probe 2: BOUNDARY — same form, edge-case values
       Open same form again
       Fill with boundary values (empty optional fields, max-length strings, special characters)
       Submit → observe
       Record probe: { type: "boundary", values_description: "...", result, network[], console_errors[] }
       
       // Probe 3: REPEAT — same exact data, submit again
       Open same form again
       Fill with SAME data as primary sequence
       Submit → observe (expect either success or proper duplicate error — not crash)
       Record probe: { type: "repeat", result, network[], console_errors[] }
       
       goal_sequences[goal_id].probes = probes
     
     // UPDATE matrix
     GOAL-COVERAGE-MATRIX: ⬜ → 🔍 REVIEW-PASSED or ❌ FAILED
  
  SAVE STATE after each goal:
    Write to ${PHASE_DIR}/discovery-state.json:
      - goal_id, result (passed/failed), steps[], probes[]
      - completed_goals[] list (for --resume to skip already-done goals)
    Write to ${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md (overwrite with latest status)
    → If token/session dies here, --resume picks up from next unfinished goal.
```

#### PASS 2b: EXHAUSTIVE ELEMENT SCAN (spawn cheap model per view)

Purpose: After goals explored, spawn cheap model agents to exhaustively scan remaining elements per view.

**MANDATORY_GATE:** You MUST dispatch element scanners for all unvisited views.
Do NOT skip scanning because "you already know what's there" or "the views look simple."
The scan discovers interactive states (modals, drawers, tab content) that code review cannot see.
Skipping = incomplete RUNTIME-MAP = missed goals in Phase 4.

**REREAD_REQUIRED:** Before dispatching scanners, re-read view-assignments.json (or discovery-state.json)
from disk (not from memory). The file may have been updated by a prior partial run or resumed session.

**Spawn 1 agent per view with unvisited elements** using `codex exec -m o3-mini`:

```
1. IDENTIFY gaps:
   IF --retry-failed:
     unvisited_views = RETRY_VIEWS[]   ← set during --retry-failed setup (failed goals → views only)
   ELSE:
     READ ${PHASE_DIR}/discovery-state.json   ← read from file, NOT from context
     unvisited_views = views where unvisited_elements > 0
   Sort by: most unvisited elements first

2. SPAWN cheap model per view:
   For each unvisited_view:
     codex exec -m o3-mini "Exhaustively scan unvisited elements on {view_url}.
       Login: {domain}/login | {email} | {password}
       Boundary: {allowed_pattern}
       ALREADY VISITED (skip these): {visited_selectors[]}
       
       WORKFLOW:
       1. Navigate to URL, wait stable
       2. Snapshot → list ALL interactive elements
       3. Remove already-visited from list
       4. For EACH remaining element, follow Element Interaction Protocol:
          - AFTER EVERY CLICK: re-snapshot, append new elements
          - Tabs: click EACH tab, recurse panel elements
          - Dropdowns: click open, click EACH item
          - Tables: scroll container, sample 1st row actions
          - Disabled: try enable (select checkbox/row), interact or mark stuck
          - Forms: fill ALL fields, submit, record result + confirm fork
          - Modals: recurse (list + interact all elements inside)
       5. Write results to: {PHASE_DIR}/scan-{view_slug}.json
       
       HARD RULES:
       - Visit 100% of remaining elements (including dynamically appended)
       - Recurse into every modal AND every tab panel
       - Click every dropdown/menu item
       - Record console errors + network requests after EVERY action
       - Mark stuck elements with reason — never silently skip

       CLEANUP (MANDATORY — always run, even on error):
         1. browser_close   ← close your browser session
         NOTE: Do NOT run playwright-lock.sh — you are a subprocess, you hold NO locks.
         Do NOT skip browser_close even if scan failed or timed out."

3. COLLECT + MERGE (summaries first, full JSON on demand):
   For each scan-{view}.json:
     Read top-level fields only: view, elements_total, elements_visited,
     elements_stuck, errors[] count, forms[] count, sub_views_discovered[]
   → Build slim overview: { view, visited_pct, error_count, stuck_count, sub_views }

   IF error_count > 0 OR stuck_count > 3 OR visited_pct < 90%:
     Read full scan-{view}.json for detail
   ELSE: do NOT load full JSON into context

   sub_views_discovered → add to gap list for follow-up spawn
   Append findings to free_exploration[] in RUNTIME-MAP
   New errors → add to error list

### Quality Check Flags
For each scan result, check:
- **INCOMPLETE**: < 3 elements found for a view that element-counts.json predicted 10+
- **SUSPICIOUS**: All elements have identical types (e.g., 20 buttons, 0 inputs)
- **SHALLOW**: No modals/drawers/tabs found for a view with known interactive triggers

Flag count > 3 → trigger re-scan for flagged views before proceeding to RUNTIME-MAP.
```

**Exploration limits:**
- Max 50 actions per view per agent
- Max 30 min wall time total
- Stagnation: same state 3 times = stuck, move on

**Session model:**
- multi-context: each role gets own browser context (from config)
- Roles come from config.credentials[ENV]

#### PASS 2b-PROBE: MUTATION PROBES (OPT-IN — only if --with-probes flag set)

**Default OFF.** Without `--with-probes`, skip this entire section. Let /vg:test handle mutation
variations via Playwright codegen (deterministic, cheaper). Only use `--with-probes` when test
codegen can't cover the mutation (complex data setup, external service stubs) or debugging a
goal that passed scan but failed probes.

**IF NOT --with-probes: skip to section 2c.**

Purpose: For each goal marked PASSED that involves mutations (create/edit/delete), spawn probes to test edge cases.

```
For each goal in GOAL-COVERAGE-MATRIX where result=PASSED AND has mutation steps:
  
  codex exec -m o3-mini "You are a probe agent. Test mutation variations for goal: {goal_id}.
    
    URL: {view_url} | Login: {credentials}
    Primary action: {what Pass 2a already did — from goal sequence}
    
    Run 3 probes:
    
    Probe 1 — EDIT: Navigate to the record just created/modified.
      Open edit form → change 1-2 fields (different valid data) → submit
      → Record: {changed_fields, result, network[], console_errors[]}
    
    Probe 2 — BOUNDARY: Open same form again.
      Fill with edge values: empty optional fields, max-length text (255 chars),
      special chars (O'Brien <script>), zero for numbers, past dates
      → Submit → Record: {values_description, result, validation_errors[]}
    
    Probe 3 — REPEAT: Open same form again.
      Fill with EXACT same data as primary → submit
      → Expect: success OR proper duplicate error — NOT crash/500
      → Record: {result, is_duplicate_handled}
    
    Write to: {PHASE_DIR}/probe-{goal_id}.json
    
    CLEANUP: browser_close when done."

Collect all probe JSONs → merge into goal coverage
Update matrix: PASSED + probes passed → PROBE-VERIFIED
```

### 2c: Parallel Verify (spawn CLI agents — read-only, after discovery)

After Pass 2a + 2b, spawn parallel CLI agents to independently verify RUNTIME-MAP accuracy.

**Critical: spawned agents do READ-ONLY verification. No mutations.**

```
For each role in config.credentials[ENV]:
  Gather views accessible to this role from RUNTIME-MAP
  
  Spawn CLI agent (shell command):
    codex exec -m o3 "Verify RUNTIME-MAP accuracy for role '{role}' in Phase {PHASE}.
      Read .planning/phases/{phase_dir}/RUNTIME-MAP.json
      Login at https://{role.domain} with {role.email}/{role.password}
      
      For EACH view accessible to your role:
      1. Navigate via UI clicks
      2. browser_snapshot → compare vs snapshot_summary in RUNTIME-MAP
      3. Check elements[] exist and are interactive
      4. browser_console_messages → any errors?
      5. DO NOT click create/edit/delete/submit buttons
      
      Write results to: .planning/phases/{phase_dir}/verify-{role}.json
      Format: {view, summary_match, elements_found, errors, mismatches}"

Wait for all agents → merge results:
  - All agree → confirmed
  - Mismatch → re-check that view
  - New errors → add to Phase 3 error list
```

### 2d: Build RUNTIME-MAP

Write `${PHASE_DIR}/RUNTIME-MAP.json`:
```json
{
  "phase": "{phase}",
  "build_sha": "{sha}",
  "discovered_at": "{ISO timestamp}",
  
  "views": {
    "{view_path}": {
      "role": "{role}",
      "arrive_via": "{click sequence}",
      "snapshot_summary": "{free text}",
      "fingerprint": { "url": "{url}", "element_count": 0, "dom_hash": "{sha256[:16]}" },
      "elements": [
        { "selector": "{from snapshot}", "label": "{visible text}", "visited": false }
      ],
      "issues": [],
      "screenshots": ["{phase}-{view}-{state}.png"]
    }
  },
  
  "goal_sequences": {
    "{goal_id}": {
      "start_view": "{view_path}",
      "result": "passed|failed",
      "steps": [
        { "do": "click", "selector": "{from snapshot}", "label": "{text}" },
        { "do": "fill", "selector": "{from snapshot}", "value": "{test data}" },
        { "observe": "{what_changed}", "network": [{"method": "POST", "url": "{observed}", "status": 201}], "console_errors": [] },
        { "assert": "{criterion from TEST-GOALS}", "passed": true }
      ],
      "probes": [
        { "type": "edit", "changed_fields": ["{field}"], "result": "passed|failed", "network": [], "console_errors": [] },
        { "type": "boundary", "values_description": "{what AI tried}", "result": "passed|failed", "network": [], "console_errors": [] },
        { "type": "repeat", "result": "passed|failed", "network": [], "console_errors": [] }
      ],
      "evidence": ["{screenshot paths}"]
    }
  },
  
  "free_exploration": [
    { "view": "{view_path}", "element_selector": "{selector}", "element_label": "{text}", "result": "{free text}", "issue": null }
  ],
  
  "errors": [],
  "coverage": {
    "views": 0,
    "goals_attempted": 0,
    "goals_passed": 0,
    "elements_visited": 0,
    "elements_total": 0
  }
}
```

Derive `${PHASE_DIR}/RUNTIME-MAP.md` from JSON (human-readable summary).
**JSON is source of truth.** Markdown is derived.
</step>

<step name="phase3_fix_loop">
## Phase 3: FIX LOOP (max 3 iterations)

**If no errors found in Phase 2 → skip to Phase 4.**

### 3a: Error Summary
Collect errors from: RUNTIME-MAP.json errors[], per-view issues[], failed goal_sequences, free_exploration issues, REVIEW-FEEDBACK.md (if exists), KNOWN-ISSUES.json.

### 3b: Classify Errors
- **CODE BUG** → fix immediately
- **INFRA ISSUE** → escalate to user
- **SPEC GAP** → emit SPEC-GAPS.md (see 3b-spec-gaps below)
- **PRE-EXISTING** → write to KNOWN-ISSUES.json (see 3b-known below)

### PRE-EXISTING errors → KNOWN-ISSUES.json

For errors classified as PRE-EXISTING (existed before this phase):
Write ${PHASE_DIR}/KNOWN-ISSUES.json:
```json
{
  "phase": "{PHASE}",
  "generated_at": "{ISO timestamp}",
  "issues": [
    {
      "id": "KI-{N}",
      "found_in_phase": "{current phase}",
      "view": "{view URL}",
      "description": "{error description}",
      "evidence": "{screenshot/console/network}",
      "affects_views": ["{list}"],
      "suggested_phase": "{future phase to fix}",
      "severity": "LOW|MEDIUM|HIGH",
      "status": "open"
    }
  ]
}
```
Future phases consume this file to skip known issues during their fix loops.

### 3b-spec-gaps: Feedback loop to blueprint

When SPEC_GAP count ≥3 OR any critical-priority goal maps to SPEC_GAP, emit `${PHASE_DIR}/SPEC-GAPS.md`:

```markdown
# Spec Gaps — Phase {phase}

Detected during Codex review phase 3b. These issues trace to missing CONTEXT decisions or un-tasked PLAN items — NOT code bugs.

## Gaps
| # | Observed Issue | Related Goal | Likely Missing | Evidence |
|---|----------------|--------------|----------------|----------|
| 1 | ... | G-XX | D-XX decision | screenshot/log |

## Recommended action (handoff to Claude)

Review CANNOT fix scope gaps. User should:

    /vg:blueprint {phase} --from=2a

(Must run via Claude — blueprint command not available as Codex skill.)
This appends tasks for missing decisions, then rerun build + review.

Do NOT attempt to fix in review fix loop — that loop targets code bugs, not missing scope.
```

Threshold + user prompt:
```bash
SPEC_GAP_COUNT=... (count SPEC_GAP classifications)
if [ "$SPEC_GAP_COUNT" -ge 3 ] || [ "$CRITICAL_SPEC_GAPS" -ge 1 ]; then
  echo "⚠ ${SPEC_GAP_COUNT} spec gaps detected. See ${PHASE_DIR}/SPEC-GAPS.md"
  echo "   Handoff to Claude: /vg:blueprint ${PHASE} --from=2a"
fi
```

Don't block review — fix loop continues for code bugs only.

### 3c: Fix + Redeploy (severity-routed, single-process Codex-compatible)

Codex CLI là single-process — KHÔNG có Task tool để spawn sub-agents. Khác với VG harness (Claude Code) có Agent tool, ở Codex toàn bộ fix chạy inline trong cùng session. Route chỉ dùng severity để decide inline-fix vs escalate.

**Config:**

```yaml
review:
  fix_routing:
    minor:
      action: "inline"         # fix trong session này
    moderate:
      action: "inline"         # Codex single-process — same session
    major:
      action: "escalate"       # REVIEW-FEEDBACK.md, không auto-fix
    tripwire:
      minor_bloat_loc: <int>   # nếu MINOR bloat → flag re-classify
      action: "warn"           # Codex không có rollback/respawn, chỉ warn
```

**Algorithm per CODE BUG:**

```
1. Load severity từ step 3b (MINOR/MODERATE/MAJOR)

2. IF severity == MAJOR:
     Append to REVIEW-FEEDBACK.md: {bug_id, view, severity, description, why_escalated}
     narrate: "[escalated] MAJOR ${bug_title} → REVIEW-FEEDBACK.md"
     Continue to next bug (do NOT fix)

3. ELSE (MINOR or MODERATE):
     Read source file → fix inline → commit: fix({phase}): {description}
     narrate: "[inline] ${severity} ${bug_title} (${files} files, ~${loc} LOC)"
```

**Post-fix tripwire (warn-only in Codex):**
```
For each MINOR-classified commit:
  ACTUAL_LOC = git show --stat {commit}
  IF ACTUAL_LOC > config.tripwire.minor_bloat_loc:
    narrate: "⚠ Tripwire: ${commit} LOC=${ACTUAL_LOC} > threshold, likely mis-classified as MINOR"
    Log to build-state.log for post-review human audit
```

**Narration format:**
```
  ▶ Fix 1/5: [inline] MINOR edit label mismatch → ✓ 1 file, 2 LOC
  ▶ Fix 2/5: [inline] MODERATE form validation missing → ✓ 3 files, 24 LOC
  ▶ Fix 3/5: [escalated] MAJOR bulk import UI absent → REVIEW-FEEDBACK.md
  ▶ Fix 4/5: [inline] MINOR CSS overflow → ⚠ 45 LOC > 15 threshold, flag re-classify
```

**Note on parity với VG (Claude Code):** VG harness có Agent tool → VG workflow spawn cheaper model cho MODERATE. Codex single-process nên tất cả inline. Cả 2 workflow dùng CÙNG config schema (`review.fix_routing`) — chỉ khác runtime behavior ở `moderate.action`:
- VG: `"spawn"` (routes to `config.models.review_fix_spawn`)
- Codex: `"inline"` (same session, chỉ severity classification + tripwire)

Redeploy → health check → if fail → rollback.

### 3d: Re-verify (spawn parallel agents — focused on fixed zones)
After fix+redeploy, spawn CLI agents to re-verify ONLY affected views:

```
1. git diff old_sha..new_sha → list changed files
2. Map changed files to views (using code_patterns from config)
3. Group affected views into zones

4. Spawn parallel agents per zone:
   codex exec "Re-verify fixed actions in {zone}.
     Previous errors: {error list}
     Expected: errors should be resolved.
     Test each previously-failed action.
     Check: did the fix break anything else?
     Report: {action, was_broken, now_works, new_issues}"

5. Merge results:
   Fixed → update matrix: ❌ → 🔍 REVIEW-PASSED
   Still broken → keep ❌, increment iteration
   New errors → add to error list
```

### 3e: Iterate
Repeat 3a-3d until stable or max 3 iterations.
</step>

<step name="phase4_goal_comparison">
## Phase 4: GOAL COMPARISON

### 4a: Load Goals
Read TEST-GOALS.md. Parse: ID, description, success criteria, priority.

### 4b: Map Goals to RUNTIME-MAP
```
For each goal:
  IF goal_sequences[goal_id] exists AND result == "passed":
    → STATUS: READY
  IF result == "failed":
    → STATUS: BLOCKED
  IF not in goal_sequences:
    → cross-check code presence:
      code_exists = grep config.code_patterns for page file, route registration, API handler
      IF code_exists == FALSE → STATUS: UNREACHABLE  (feature not built)
      IF code_exists == TRUE  → STATUS: NOT_SCANNED  (code built, review didn't replay)
        (causes: multi-step wizard, orphan route, timeout, retry-scope miss)
```

Status semantics (tightened 2026-04-17):

**4 conclusive statuses** (only these may appear in final GOAL-COVERAGE-MATRIX):
- READY         = goal_sequences exists + result passed
- BLOCKED       = goal_sequences exists + result failed (code bug — view found, criteria not met)
- UNREACHABLE   = goal_sequences missing + code NOT in repo (feature genuinely not built)
- INFRA_PENDING = goal needs service/infra not available on ENV (config.infra_deps)

**2 intermediate statuses** (MUST resolve before review exits):
- NOT_SCANNED   = goal_sequences missing + code EXISTS (review skipped)
- FAILED        = scan timeout/exception

**⛔ GLOBAL RULE: KHÔNG được defer NOT_SCANNED sang /vg:test.** `/vg:test` codegen lấy steps từ `goal_sequences[]` review ghi. NOT_SCANNED = review không ghi sequence = codegen không có input.

### 4c-pre: ⛔ Intermediate resolution gate (tightened 2026-04-17)

Trước khi chạy weighted gate, PHẢI resolve mọi `NOT_SCANNED` + `FAILED` thành 1 trong 4 conclusive statuses:
```
NOT_SCANNED_COUNT = count goals where status == "NOT_SCANNED"
FAILED_COUNT      = count goals where status == "FAILED"
INTERMEDIATE = NOT_SCANNED_COUNT + FAILED_COUNT

IF INTERMEDIATE > 0 AND --allow-intermediate NOT in args:
  STOP review. Options:
    a) /vg:review {phase} --retry-failed    (deeper probe)
    b) Goal không có UI surface → update TEST-GOALS 'Infra deps: [<no-ui tag>]' → re-classify INFRA_PENDING (tag value per project config.infra_deps — workflow không hardcode)
    c) Verify config.code_patterns.frontend_routes cover pattern đó (orphan route)
    d) Manually mark UNREACHABLE với reason note

  EXIT 1. KHÔNG được exit Phase 4 với intermediate status.

IF --allow-intermediate passed:
  Auto-convert remaining NOT_SCANNED/FAILED → UNREACHABLE với reason="review-skip-{original}"
  Log to build-state.log
```

### 4c: Weighted Gate
```
critical:     100% must be READY
important:     80% must be READY
nice-to-have:  50% must be READY

ANY critical NOT READY → BLOCK
Important ready% < 80% → BLOCK
All thresholds met → PASS
```

### 4d: Write GOAL-COVERAGE-MATRIX.md

```markdown
# Goal Coverage Matrix — Phase {phase}

## Summary
- Goals: {total}
- Ready: {N} | Blocked: {N} | Unreachable: {N}

## By Priority
| Priority | Ready | Total | Threshold | Status |
|----------|-------|-------|-----------|--------|
| critical | {N} | {N} | 100% | {PASS|BLOCK} |
| important | {N} | {N} | 80% | {PASS|BLOCK} |
| nice-to-have | {N} | {N} | 50% | {PASS|BLOCK} |

## Goal Details
| Goal | Priority | Status | Notes |
|------|----------|--------|-------|

## Gate: {PASS|BLOCK}
```

### CrossAI Review (skip in Codex)
Codex does not invoke CrossAI CLIs. If CrossAI review is needed, run in Claude:
  /vg:review {phase} --crossai-only
CrossAI results are written to ${PHASE_DIR}/crossai/ and consumed by accept.
</step>

<step name="write_artifacts">
## Write Final Artifacts

1. `${PHASE_DIR}/RUNTIME-MAP.json` — canonical JSON (source of truth)
2. `${PHASE_DIR}/RUNTIME-MAP.md` — derived from JSON
3. `${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md` — from Phase 4
4. `${PHASE_DIR}/element-counts.json` — from Phase 1b
5. `${PHASE_DIR}/discovery-state.json` — for --resume

### Artifact Validation (MANDATORY before commit)
Verify all required outputs exist:
- [ ] ${PHASE_DIR}/RUNTIME-MAP.json (non-empty, valid JSON)
- [ ] ${PHASE_DIR}/RUNTIME-MAP.md
- [ ] ${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md
- [ ] ${PHASE_DIR}/element-counts.json
- [ ] ${PHASE_DIR}/RIPPLE-ANALYSIS.md (if graphify enabled)

If ANY missing → DO NOT commit. Re-run the missing phase.

Commit:
```bash
git add ${PHASE_DIR}/RUNTIME-MAP.json ${PHASE_DIR}/RUNTIME-MAP.md \
       ${PHASE_DIR}/GOAL-COVERAGE-MATRIX.md ${PHASE_DIR}/element-counts.json
git commit -m "review({phase}): RUNTIME-MAP — {views} views, {actions} actions, gate {PASS|BLOCK}"
```
</step>

<step name="complete">

**Update GSD STATE.md (optional — if GSD installed):**
```bash
if [ -x "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" ]; then
  node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" state update-phase \
    --phase "${PHASE_NUMBER}" --status "in_progress" --pipeline-step "reviewed" 2>/dev/null || true
fi
```

Display:
```
Review complete for Phase {N}.
  Code scan: contract {PASS|WARNING}, {N} elements inventoried
  Discovery: {views} views, {actions} actions tested
  Fix loop: {iterations} iterations, {fixes} fixes applied
  Goals: {ready}/{total} ready (critical: {N}/{N}, important: {N}/{N})
  Gate: {PASS|BLOCK}
  Artifacts: RUNTIME-MAP.json + GOAL-COVERAGE-MATRIX.md
  Next: /vg:test {phase}
```
</step>

</process>

<success_criteria>
- Code scan completed (contract verify + element inventory)
- Browser discovery explored all reachable views organically
- RUNTIME-MAP.json produced with actual runtime observations
- RUNTIME-MAP.md derived from JSON
- Fix loop resolved code bugs (if any)
- TEST-GOALS mapped to discovered paths
- GOAL-COVERAGE-MATRIX.md shows weighted goal readiness
- Gate passed (100% critical, 80% important, 50% nice-to-have)
- Discovery state saved (resumable)
</success_criteria>
