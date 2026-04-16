---
name: vg:migrate
description: Convert legacy GSD phase artifacts to VG format
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

<rules>
1. **Non-destructive** — never delete GSD originals. Move to `.gsd-backup/` within phase dir.
2. **Idempotent** — running migrate twice on same phase produces same result. Skip already-converted artifacts.
3. **Config-driven** — all format decisions from vg.config.md (contract_format, scan_patterns, etc.)
4. **No hardcoded project values** — endpoint paths, file locations, domain names all from config or code scan.
5. **Profile enforcement** — `touch "${PHASE_DIR}/.step-markers/migrate.done"` at end.
</rules>

<objective>
Convert a phase that was planned/built using GSD workflows into VG-native format.
Ensures all VG pipeline steps (review, test, accept) can run on the migrated phase.

When to use:
- Project previously used GSD, now switching to VG
- Phase has CONTEXT.md (GSD format) but no API-CONTRACTS.md or TEST-GOALS.md
- Phase has old-style PLAN.md without VG task attributes
- `/vg:next` shows phase as `legacy_gsd` type
</objective>

<process>

**Config:** Read .claude/commands/vg/_shared/config-loader.md first.

<step name="1_parse_args">
Parse `$ARGUMENTS`: phase number (required), optional flags:
- `--dry-run` — show what would be converted, don't write files
- `--force` — re-convert even if VG artifacts already exist (backup existing first)
- `--skip-contracts` — skip API-CONTRACTS.md generation (manual later)
- `--skip-goals` — skip TEST-GOALS.md generation (manual later)
</step>

<step name="2_detect_artifacts">
## Artifact Inventory

Scan `${PHASE_DIR}/` and classify every file:

```bash
echo "=== Phase ${PHASE_NUMBER} Artifact Inventory ==="

# GSD-era artifacts (may need conversion)
GSD_ARTIFACTS=()
VG_ARTIFACTS=()
MISSING_VG=()

# Check each expected file
for f in RESEARCH.md CONTEXT.md PLAN.md SUMMARY*.md DISCUSSION-LOG.md; do
  if ls "${PHASE_DIR}"/$f 2>/dev/null; then
    GSD_ARTIFACTS+=("$f")
  fi
done

# Check VG-native artifacts
for f in API-CONTRACTS.md TEST-GOALS.md FLOW-SPEC.md PIPELINE-STATE.json; do
  if [ -f "${PHASE_DIR}/$f" ]; then
    VG_ARTIFACTS+=("$f")
  else
    MISSING_VG+=("$f")
  fi
done

# Check CONTEXT.md format (enriched vs flat)
if [ -f "${PHASE_DIR}/CONTEXT.md" ]; then
  # VG enriched format has sub-sections per decision: Endpoints:, UI Components:, Test Scenarios:
  ENRICHED=$(grep -c "Endpoints:\|UI Components:\|Test Scenarios:" "${PHASE_DIR}/CONTEXT.md" 2>/dev/null || echo 0)
  if [ "$ENRICHED" -gt 0 ]; then
    CONTEXT_FORMAT="vg-enriched"
  else
    CONTEXT_FORMAT="gsd-flat"
  fi
fi

# Check PLAN.md format (VG attributes vs GSD plain)
if ls "${PHASE_DIR}"/PLAN*.md 2>/dev/null; then
  VG_ATTRS=$(grep -c "<file-path>\|<contract-ref>\|<goals-covered>" "${PHASE_DIR}"/PLAN*.md 2>/dev/null || echo 0)
  if [ "$VG_ATTRS" -gt 0 ]; then
    PLAN_FORMAT="vg-attributed"
  else
    PLAN_FORMAT="gsd-plain"
  fi
fi
```

**Display inventory:**

```
Phase {N} — Artifact Inventory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GSD artifacts found:     {list}
VG artifacts found:      {list}
VG artifacts missing:    {list}

CONTEXT.md format:       {gsd-flat | vg-enriched | missing}
PLAN.md format:          {gsd-plain | vg-attributed | missing}

Migration needed:
  [ ] CONTEXT.md enrichment    {yes/no — yes if gsd-flat}
  [ ] PLAN.md attribution      {yes/no — yes if gsd-plain}
  [ ] API-CONTRACTS.md         {generate/exists/skip}
  [ ] TEST-GOALS.md            {generate/exists/skip}
```

If ALL artifacts already VG-native → print "Phase already VG-native. Nothing to migrate." → STOP.
If `--dry-run` → print migration plan → STOP.
</step>

<step name="3_backup_originals">
## Backup GSD Originals

```bash
BACKUP_DIR="${PHASE_DIR}/.gsd-backup"
mkdir -p "$BACKUP_DIR"

# Backup files that will be converted (not all files)
if [ "$CONTEXT_FORMAT" = "gsd-flat" ]; then
  cp "${PHASE_DIR}/CONTEXT.md" "$BACKUP_DIR/CONTEXT.md.gsd"
  echo "Backed up: CONTEXT.md → .gsd-backup/CONTEXT.md.gsd"
fi

if [ "$PLAN_FORMAT" = "gsd-plain" ]; then
  for plan in "${PHASE_DIR}"/PLAN*.md; do
    PLAN_NAME=$(basename "$plan")
    cp "$plan" "$BACKUP_DIR/${PLAN_NAME}.gsd"
    echo "Backed up: ${PLAN_NAME} → .gsd-backup/${PLAN_NAME}.gsd"
  done
fi

# If --force and VG artifacts exist, backup those too
if [[ "$FLAGS" =~ --force ]]; then
  for f in API-CONTRACTS.md TEST-GOALS.md; do
    if [ -f "${PHASE_DIR}/$f" ]; then
      cp "${PHASE_DIR}/$f" "$BACKUP_DIR/${f}.prev"
      echo "Backed up: ${f} → .gsd-backup/${f}.prev"
    fi
  done
fi
```
</step>

<step name="4_enrich_context">
## Convert CONTEXT.md: GSD flat → VG enriched

**Skip if:** CONTEXT_FORMAT already "vg-enriched" AND not --force.

**GSD flat format** (decisions only):
```
## D-01: Use MongoDB for storage
MongoDB chosen for flexibility...

## D-02: REST API with Fastify
Standard REST endpoints...
```

**VG enriched format** (decisions + structured sub-sections):
```
## D-01: Use MongoDB for storage
MongoDB chosen for flexibility...

**Endpoints:** none (infrastructure decision)
**UI Components:** none
**Test Scenarios:**
- Database connection established on startup
- Collections created with correct indexes
```

**Conversion process — spawn agent (model=sonnet for quality):**

```
Agent(model="sonnet", description="Enrich CONTEXT.md for phase ${PHASE_NUMBER}"):
  prompt: |
    Convert this GSD-format CONTEXT.md to VG enriched format.
    
    RULES:
    1. Keep ALL existing decision text EXACTLY as-is (do not rewrite prose)
    2. ADD 3 sub-sections after each decision: Endpoints, UI Components, Test Scenarios
    3. Derive sub-sections from decision text + code scan:
       - Endpoints: grep code for routes/handlers matching this decision's domain
       - UI Components: grep code for pages/components matching this decision
       - Test Scenarios: infer 2-3 testable scenarios from decision text
    4. If decision is pure infra/config (no API/UI): write "none" for Endpoints/UI
    5. Do NOT invent endpoints that don't exist in code — only document what's built
    
    Code patterns to scan:
      API routes: ${config.code_patterns.api_routes}
      Web pages: ${config.code_patterns.web_pages}
    
    <context_md>
    @${PHASE_DIR}/CONTEXT.md
    </context_md>
    
    <code_scan_hints>
    Grep existing endpoints in codebase related to this phase's domain.
    </code_scan_hints>
    
    Output: write enriched CONTEXT.md to ${PHASE_DIR}/CONTEXT.md
```

**Post-conversion validation:**
```bash
DECISIONS=$(grep -c "^## D-" "${PHASE_DIR}/CONTEXT.md")
ENDPOINTS=$(grep -c "^\*\*Endpoints:\*\*" "${PHASE_DIR}/CONTEXT.md")
if [ "$DECISIONS" != "$ENDPOINTS" ]; then
  echo "WARNING: ${DECISIONS} decisions but only ${ENDPOINTS} Endpoint sections. Some decisions may be missing sub-sections."
fi

# ⛔ Hallucination check (tightened 2026-04-17): enriched CONTEXT may hallucinate endpoints.
# For every endpoint mentioned in Endpoints sections, grep actual API route files
# to confirm it exists. Missing endpoints → fail (rewrite required).
API_ROUTES_GLOB="${config.code_patterns.api_routes:-apps/api/src/modules/**/*.routes.ts}"

HALLUCINATED=0
while IFS= read -r ep; do
  # Extract VERB + path, e.g., "POST /api/sites"
  METHOD=$(echo "$ep" | grep -oE "^(GET|POST|PUT|PATCH|DELETE)")
  PATH_PART=$(echo "$ep" | grep -oE '/[a-zA-Z0-9/_:{}.-]+')
  [ -z "$METHOD" ] || [ -z "$PATH_PART" ] && continue

  # Search for route registration — various frameworks
  if ! grep -rEq "(\.|@)(${METHOD,,}|route|Route).*['\"\`]${PATH_PART}['\"\`]" $API_ROUTES_GLOB 2>/dev/null \
     && ! grep -rEq "method.*['\"\`]${METHOD}['\"\`].*path.*['\"\`]${PATH_PART}['\"\`]" $API_ROUTES_GLOB 2>/dev/null; then
    echo "⚠ HALLUCINATED endpoint: ${METHOD} ${PATH_PART} — not found in ${API_ROUTES_GLOB}"
    HALLUCINATED=$((HALLUCINATED + 1))
  fi
done < <(grep -oE "(GET|POST|PUT|PATCH|DELETE)\s+/[a-zA-Z0-9/_:{}.-]+" "${PHASE_DIR}/CONTEXT.md" | sort -u)

if [ "$HALLUCINATED" -gt 0 ]; then
  TOTAL_EPS=$(grep -oE "(GET|POST|PUT|PATCH|DELETE)\s+/" "${PHASE_DIR}/CONTEXT.md" | wc -l | tr -d ' ')
  RATIO=$((HALLUCINATED * 100 / (TOTAL_EPS + 1)))
  echo "Hallucination ratio: ${HALLUCINATED}/${TOTAL_EPS} (${RATIO}%)"
  if [ "$RATIO" -gt 10 ]; then
    echo "⛔ Hallucination ratio > 10% — enrichment agent likely invented endpoints."
    echo "   Fix: rewrite CONTEXT.md manually OR ensure code has the referenced routes first."
    if [[ ! "$ARGUMENTS" =~ --allow-hallucinated-eps ]]; then
      exit 1
    fi
  fi
fi
```
</step>

<step name="5_generate_contracts">
## Generate API-CONTRACTS.md (if missing)

**Skip if:** API-CONTRACTS.md exists AND not --force. Also skip if --skip-contracts.

This reuses the existing blueprint contract generation logic, but targeted at an already-built phase.

**Key difference from blueprint:** blueprint generates contracts BEFORE code. Migrate generates contracts FROM existing code (reverse-engineering).

```
Agent(model="sonnet", description="Generate API-CONTRACTS.md from built code"):
  prompt: |
    Read skill: .claude/skills/api-contract/SKILL.md — Mode: Generate.
    
    Generate API-CONTRACTS.md for phase ${PHASE_NUMBER}.
    This phase was ALREADY BUILT — extract contracts from existing code, don't invent.
    
    Inputs:
    1. CONTEXT.md enriched decisions (Endpoints sub-sections)
    2. Actual route handler code at: ${config.code_patterns.api_routes}
    3. Contract format: ${config.contract_format.type}
    
    Process:
    1. Read CONTEXT.md → list endpoints mentioned in Endpoints sub-sections
    2. For each endpoint, grep actual route handler in codebase
    3. Extract: method, path, request schema (from validation), response shape, auth middleware, error codes
    4. Generate 4-block contract per endpoint (auth, schema, errors, sample)
    5. If code uses Zod: extract schema directly from code (don't reinvent)
    6. If code uses bare validation: create Zod schema matching the validation logic
    
    CRITICAL: This is REVERSE-ENGINEERING from code, not forward-design.
    Every field, every status code, every auth guard MUST match what's actually in the code.
    
    Output: write ${PHASE_DIR}/API-CONTRACTS.md
```
</step>

<step name="6_generate_goals">
## Generate TEST-GOALS.md (if missing)

**Skip if:** TEST-GOALS.md exists AND not --force. Also skip if --skip-goals.

Reuses blueprint step 2b5 logic but from enriched CONTEXT.md.

```
Agent(model="sonnet", description="Generate TEST-GOALS.md from enriched CONTEXT"):
  prompt: |
    Generate TEST-GOALS.md for phase ${PHASE_NUMBER}.
    
    Inputs:
    1. CONTEXT.md enriched decisions (Test Scenarios sub-sections)
    2. API-CONTRACTS.md (if generated in step 5)
    3. Built code (verify goals are testable against actual implementation)
    
    Rules:
    1. Every decision with Test Scenarios → at least 1 goal
    2. Every endpoint in API-CONTRACTS.md → at least 1 goal
    3. Goals describe WHAT to verify, not HOW
    4. Priority assignment:
       - Auth/payment/security → critical
       - Data mutation (POST/PUT/DELETE) → important (min)
       - Read-only (GET) → important
       - Cosmetic/display → nice-to-have
    5. Each goal MUST have: success criteria, mutation evidence, dependencies
    6. Add `infra_deps` field if goal requires services not in this phase:
       ```
       **Infra deps:** [clickhouse, kafka, pixel-server, redis]
       ```
       Goals with unmet infra_deps auto-classify as INFRA_PENDING in review Phase 4.
    
    Output format: follow TEST-GOALS.md template from blueprint step 2b5.
    Write to: ${PHASE_DIR}/TEST-GOALS.md
```
</step>

<step name="7_attribute_plans">
## Attribute PLAN.md tasks (if GSD-plain format)

**Skip if:** PLAN_FORMAT already "vg-attributed" AND not --force.

Add VG task attributes to existing GSD plan tasks WITHOUT rewriting task content.

```
Agent(model="sonnet", description="Add VG attributes to PLAN.md tasks"):
  prompt: |
    Add VG task attributes to existing PLAN.md tasks for phase ${PHASE_NUMBER}.
    
    DO NOT rewrite task descriptions. ONLY ADD attributes.
    
    For each task (## Task N or ### Task N):
    1. Add <file-path> — grep codebase for the file this task actually created/modified
       (check git log for phase commits if available)
    2. Add <contract-ref> — if task touches API endpoint, reference API-CONTRACTS.md section
    3. Add <goals-covered> — map task to G-XX from TEST-GOALS.md
    4. Add <design-ref> — if task builds UI page and design assets exist
    
    Read:
    - ${PHASE_DIR}/PLAN*.md (tasks to attribute)
    - ${PHASE_DIR}/API-CONTRACTS.md (for contract-ref mapping)
    - ${PHASE_DIR}/TEST-GOALS.md (for goals-covered mapping)
    
    Output: overwrite ${PHASE_DIR}/PLAN*.md with attributed versions
```
</step>

<step name="8_write_pipeline_state">
## Initialize VG Pipeline State

```bash
# Write PIPELINE-STATE.json if not exists
PIPELINE_STATE="${PHASE_DIR}/PIPELINE-STATE.json"
if [ ! -f "$PIPELINE_STATE" ]; then
  ${PYTHON_BIN} -c "
import json
from datetime import datetime
state = {
  'status': 'migrated',
  'pipeline_step': 'review',
  'migrated_from': 'gsd',
  'migrated_at': datetime.now().isoformat(),
  'updated_at': datetime.now().isoformat(),
  'artifacts': {
    'context': 'enriched',
    'contracts': 'generated' if not skip_contracts else 'skipped',
    'goals': 'generated' if not skip_goals else 'skipped',
    'plans': 'attributed' if plan_format == 'gsd-plain' else 'already_vg',
  }
}
with open('${PIPELINE_STATE}', 'w') as f:
  json.dump(state, f, indent=2)
print('PIPELINE-STATE.json written')
"
fi

# Update .recon-state.json for /vg:next routing
${PYTHON_BIN} .claude/scripts/phase-recon.py \
  --phase-dir "${PHASE_DIR}" --profile "${PROFILE}" --quiet 2>/dev/null || true
```
</step>

<step name="8b_backfill_infra">
## Backfill Project-Level Infra Registers (2026-04-17)

Runs ONCE per project (idempotent). If project has multiple phases being migrated, this step auto-skips after first run. Use `--force-infra` to re-run.

VG infra features (debt/telemetry/security/visual/graphify) depend on registers that don't exist in legacy projects. Scan historical artifacts to backfill.

**Skip if already done:**
```bash
INFRA_MARKER=".planning/.infra-backfill.done"
if [ -f "$INFRA_MARKER" ] && [[ ! "$FLAGS" =~ --force-infra ]]; then
  echo "Infra already backfilled (${INFRA_MARKER}). Use --force-infra to re-run."
else
```

**8b.1 — Debt register backfill** (if `CONFIG_DEBT_REGISTER_PATH` config present):
```bash
if [ -n "${CONFIG_DEBT_REGISTER_PATH}" ] && [ ! -f "${CONFIG_DEBT_REGISTER_PATH}" ]; then
  ${PYTHON_BIN} - "${CONFIG_DEBT_REGISTER_PATH}" <<'PY'
import os, re, sys, glob
from datetime import datetime, timezone
from pathlib import Path
register = Path(sys.argv[1])
register.parent.mkdir(parents=True, exist_ok=True)

patterns = {
  "--allow-missing-commits": "critical", "--override-reason": "critical",
  "--override-regressions": "critical", "--force-accept-with-debt": "critical",
  "--allow-no-tests": "high", "--skip-design-check": "high",
  "--allow-intermediate": "high", "--skip-context-rebuild": "high",
  "--skip-crossai": "medium", "--skip-research": "medium", "--allow-deferred": "medium",
}

rows, count = [], 0
for phase_dir in sorted(glob.glob(".planning/phases/*/")):
  phase = Path(phase_dir).name.split("-")[0] if "-" in Path(phase_dir).name else Path(phase_dir).name
  for fname in ("build-state.log", "SANDBOX-TEST.md", "UAT.md"):
    fpath = Path(phase_dir) / fname
    if not fpath.exists(): continue
    try: text = fpath.read_text(encoding='utf-8', errors='ignore')
    except Exception: continue
    mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    for pat, sev in patterns.items():
      for line in text.splitlines():
        if pat in line:
          count += 1
          reason = (line.strip()[:100]).replace("|","\\|")
          rows.append(f"| DEBT-HIST-{count:03d} | {sev} | {phase} | historical-{fname} | `{pat}` | {reason} | {mtime} | RESOLVED | (backfill) |")
          break  # one match per file per pattern

with open(register, 'w', encoding='utf-8') as f:
  f.write("# Override Debt Register\n\nAuto-maintained by VG workflow. Backfilled from historical artifacts.\n\n## Entries\n\n")
  f.write("| ID | Severity | Phase | Step | Flag | Reason | Logged (UTC) | Status | Resolved |\n")
  f.write("|----|----------|-------|------|------|--------|--------------|--------|----------|\n")
  f.write("\n".join(rows) + "\n")
print(f"  Debt backfill: {count} historical entries")
PY
else
  echo "  Debt register exists or not configured — skip"
fi
```

**8b.2 — Security register consolidation** (if `CONFIG_SECURITY_REGISTER_PATH` config present):
```bash
if [ -n "${CONFIG_SECURITY_REGISTER_PATH}" ] && [ ! -f "${CONFIG_SECURITY_REGISTER_PATH}" ]; then
  ${PYTHON_BIN} - "${CONFIG_SECURITY_REGISTER_PATH}" <<'PY'
import os, re, sys, glob
from datetime import datetime, timezone
from pathlib import Path
register = Path(sys.argv[1])
register.parent.mkdir(parents=True, exist_ok=True)

sev_map = {"critical":"critical","high":"high","medium":"medium","low":"low","info":"info"}
status_map = {"open":"OPEN","mitigated":"MITIGATED","resolved":"MITIGATED","fixed":"MITIGATED","in_progress":"IN_PROGRESS"}
threats, count = [], 0

for sec_file in sorted(glob.glob(".planning/phases/*/SECURITY*.md")) + sorted(glob.glob(".planning/phases/*/security.md")):
  phase = Path(sec_file).parent.name.split("-")[0] if "-" in Path(sec_file).parent.name else Path(sec_file).parent.name
  text = open(sec_file, encoding='utf-8', errors='ignore').read()
  blocks = re.split(r'^##\s+(?:Finding|Issue|Threat)[\s:]', text, flags=re.M|re.I)[1:]
  for blk in blocks:
    lines = blk.splitlines()
    title = (lines[0].strip().lstrip(':').strip() if lines else "untitled")[:100]
    sev, status, evidence, tax = "medium", "OPEN", "-", "custom"
    for line in lines:
      l = line.lower().strip()
      m = re.search(r'severity:\s*(\w+)', l);   sev = sev_map.get(m.group(1), sev) if m else sev
      m = re.search(r'status:\s*(\w+)', l);     status = status_map.get(m.group(1), status.upper()) if m else status
      m = re.search(r'evidence:\s*(.+)', line, re.I); evidence = m.group(1).strip()[:80] if m else evidence
      if l.startswith("taxonomy:") or l.startswith("stride:") or l.startswith("owasp:"):
        tax = line.split(":",1)[1].strip()[:40] if ":" in line else tax
    count += 1
    ts = datetime.fromtimestamp(Path(sec_file).stat().st_mtime, tz=timezone.utc).date().isoformat()
    threats.append((f"SEC-{count:03d}", sev, phase, tax, title, status, evidence, ts))

milestone = os.environ.get("MILESTONE_ID", "legacy")
with open(register, 'w', encoding='utf-8') as f:
  f.write(f"# Security Register (Milestone: {milestone})\n\nCumulative threat ledger. Backfilled from per-phase SECURITY.md files.\n\n## Threats\n\n")
  f.write("| ID | Severity | Phase(s) | Taxonomy | Title | Mitigation Status | Evidence | Created | Last Updated |\n")
  f.write("|----|----------|----------|----------|-------|-------------------|----------|---------|--------------|\n")
  for t in threats: f.write("| " + " | ".join(t[:7]) + f" | {t[7]} | {t[7]} |\n")
  f.write("\n## Composite Threats (auto-correlated)\n\n| Composite ID | Component SEC-IDs | Phases | Combined Severity | Rule |\n|-------------|-------------------|--------|-------------------|------|\n")
  f.write(f"\n## Decay Log\n- {datetime.now(timezone.utc).date().isoformat()} Backfilled {count} threats via /vg:migrate\n")
  f.write(f"\n## Audit Trail\n- {datetime.now(timezone.utc).date().isoformat()} /vg:migrate infra backfill: +{count} threats\n")
print(f"  Security backfill: {count} threats from legacy SECURITY.md files")
PY
else
  echo "  Security register exists or not configured — skip"
fi
```

**8b.3 — Telemetry init + git-log phase reconstruction**:
```bash
if [ -n "${CONFIG_TELEMETRY_PATH}" ] && [ ! -f "${CONFIG_TELEMETRY_PATH}" ]; then
  mkdir -p "$(dirname "${CONFIG_TELEMETRY_PATH}")"
  TS=$(date -u +%FT%TZ); SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
  echo "{\"ts\":\"${TS}\",\"event\":\"bootstrap\",\"phase\":\"\",\"step\":\"migrate\",\"session_id\":\"migrate\",\"git_sha\":\"${SHA}\",\"meta\":{\"reason\":\"vg:migrate infra backfill\"}}" > "${CONFIG_TELEMETRY_PATH}"

  # Reconstruct phase timings from git log commits (feat(X.Y-NN): pattern)
  ${PYTHON_BIN} - "${CONFIG_TELEMETRY_PATH}" <<'PY'
import subprocess, json, re, sys
from datetime import datetime
from pathlib import Path
path = Path(sys.argv[1])
r = subprocess.run(["git","log","--pretty=format:%H|%cI|%s","--reverse"], capture_output=True, text=True)
first, last = {}, {}
for line in r.stdout.splitlines():
  parts = line.split("|",2)
  if len(parts) != 3: continue
  sha, ts, msg = parts
  m = re.match(r'^(feat|fix|chore|docs|test|refactor)\((\d+(?:\.\d+)*)-\d+\):', msg)
  if not m: continue
  phase = m.group(2)
  first.setdefault(phase, (sha, ts))
  last[phase] = (sha, ts)
with open(path, 'a', encoding='utf-8') as f:
  for phase in sorted(first):
    s_sha, s_ts = first[phase]; e_sha, e_ts = last[phase]
    dur = int((datetime.fromisoformat(e_ts) - datetime.fromisoformat(s_ts)).total_seconds())
    f.write(json.dumps({"ts":e_ts,"event":"phase_complete_backfill","phase":phase,"step":"bootstrap-from-git","session_id":"migrate","git_sha":e_sha[:8],"meta":{"duration_s":dur,"source":"git-log"}}) + "\n")
print(f"  Telemetry init + {len(first)} phase timing events reconstructed from git log")
PY
else
  echo "  Telemetry already initialized or not configured — skip"
fi
```

**8b.4 — Graphify rebuild marker** (assume current graph is fresh, so first `/vg:map` after migrate doesn't force full rebuild):
```bash
GRAPH_MARKER="${CONFIG_PATHS_PLANNING_DIR:-.planning}/.graphify-last-rebuild"
if [ ! -f "$GRAPH_MARKER" ] && [ -f .claude/scripts/graphify-incremental.py ]; then
  ${PYTHON_BIN} .claude/scripts/graphify-incremental.py mark --marker "$GRAPH_MARKER" 2>/dev/null && \
    echo "  Graphify marker initialized"
fi
```

**8b.5 — Visual baseline auto-promote** (only if `visual_regression.enabled`):
```bash
if [ "${CONFIG_VISUAL_REGRESSION_ENABLED:-false}" = "true" ] && [ -d "${CONFIG_VISUAL_REGRESSION_CURRENT_DIR}" ] && [ ! -d "${CONFIG_VISUAL_REGRESSION_BASELINE_DIR}" ]; then
  for sd in "${CONFIG_VISUAL_REGRESSION_CURRENT_DIR}"/*/; do
    [ -d "$sd" ] || continue
    phase=$(basename "$sd")
    ${PYTHON_BIN} .claude/scripts/visual-diff.py promote --from "$sd" --to "${CONFIG_VISUAL_REGRESSION_BASELINE_DIR}/${phase}" 2>/dev/null
  done
  echo "  Visual baseline promoted from existing screenshots"
fi
```

**Mark infra backfill done:**
```bash
mkdir -p .planning
touch "$INFRA_MARKER"
fi  # end "already done" skip guard
```
</step>

<step name="9_validate_and_report">
## Validation + Report

**Completeness checks:**

```bash
echo "=== Migration Validation ==="

PASS=0
WARN=0
FAIL=0

# Check CONTEXT.md enriched
if grep -q "^\*\*Endpoints:\*\*" "${PHASE_DIR}/CONTEXT.md" 2>/dev/null; then
  echo "  [PASS] CONTEXT.md enriched"
  ((PASS++))
else
  echo "  [FAIL] CONTEXT.md not enriched"
  ((FAIL++))
fi

# Check API-CONTRACTS.md
if [ -f "${PHASE_DIR}/API-CONTRACTS.md" ]; then
  BLOCKS=$(grep -c '```typescript\|```yaml\|```python' "${PHASE_DIR}/API-CONTRACTS.md" 2>/dev/null || echo 0)
  if [ "$BLOCKS" -gt 0 ]; then
    echo "  [PASS] API-CONTRACTS.md with ${BLOCKS} code blocks"
    ((PASS++))
  else
    echo "  [WARN] API-CONTRACTS.md exists but no code blocks"
    ((WARN++))
  fi
else
  if [[ "$FLAGS" =~ --skip-contracts ]]; then
    echo "  [SKIP] API-CONTRACTS.md (--skip-contracts)"
  else
    echo "  [FAIL] API-CONTRACTS.md missing"
    ((FAIL++))
  fi
fi

# Check TEST-GOALS.md
if [ -f "${PHASE_DIR}/TEST-GOALS.md" ]; then
  GOALS=$(grep -c "^## Goal G-" "${PHASE_DIR}/TEST-GOALS.md" 2>/dev/null || echo 0)
  echo "  [PASS] TEST-GOALS.md with ${GOALS} goals"
  ((PASS++))
else
  if [[ "$FLAGS" =~ --skip-goals ]]; then
    echo "  [SKIP] TEST-GOALS.md (--skip-goals)"
  else
    echo "  [FAIL] TEST-GOALS.md missing"
    ((FAIL++))
  fi
fi

# Check PLAN.md attributed
if ls "${PHASE_DIR}"/PLAN*.md 2>/dev/null; then
  ATTRS=$(grep -c "<file-path>" "${PHASE_DIR}"/PLAN*.md 2>/dev/null || echo 0)
  TASKS=$(grep -c "^##\{1,2\} Task" "${PHASE_DIR}"/PLAN*.md 2>/dev/null || echo 0)
  if [ "$ATTRS" -gt 0 ]; then
    echo "  [PASS] PLAN.md attributed (${ATTRS}/${TASKS} tasks have file-path)"
    ((PASS++))
  else
    echo "  [WARN] PLAN.md exists but no VG attributes"
    ((WARN++))
  fi
fi

# Check backups exist
BACKUPS=$(ls "${PHASE_DIR}/.gsd-backup/" 2>/dev/null | wc -l)
echo "  [INFO] ${BACKUPS} backup file(s) in .gsd-backup/"

echo ""
echo "Result: ${PASS} pass, ${WARN} warn, ${FAIL} fail"
```

**Display migration report:**

```
━━━ Migration Complete — Phase {N} ━━━

Converted:
  CONTEXT.md:        gsd-flat → vg-enriched ({N} decisions enriched)
  PLAN.md:           gsd-plain → vg-attributed ({N}/{M} tasks attributed)
  API-CONTRACTS.md:  generated ({N} endpoints, {M} code blocks)
  TEST-GOALS.md:     generated ({N} goals: {c} critical, {i} important, {n} nice-to-have)

Backups:             .gsd-backup/ ({N} files)
Pipeline state:      migrated → ready for /vg:review

Next steps:
  1. Review generated artifacts: API-CONTRACTS.md and TEST-GOALS.md
  2. Run: /vg:review {phase}
  3. Or: /vg:next (auto-detects review as next step)
```

Final action: `touch "${PHASE_DIR}/.step-markers/migrate.done"`
</step>

</process>

<success_criteria>
- GSD originals backed up to .gsd-backup/
- CONTEXT.md enriched with Endpoints/UI/Test sub-sections per decision
- API-CONTRACTS.md generated from existing code (if not --skip-contracts)
- TEST-GOALS.md generated with goals + infra_deps field (if not --skip-goals)
- PLAN.md tasks attributed with VG task attributes
- PIPELINE-STATE.json written with migrated status
- Validation passes with 0 FAIL items
- Phase routable by /vg:next (shows as review-ready)
</success_criteria>
