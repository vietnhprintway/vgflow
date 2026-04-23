---
name: "vg-security-audit-milestone"
description: "Cross-phase security audit for current milestone — correlate threats, apply decay, surface composite risks, generate audit report"
metadata:
  short-description: "Cross-phase security audit for current milestone — correlate threats, apply decay, surface composite risks, generate audit report"
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

This skill is invoked by mentioning `$vg-security-audit-milestone`. Treat all user text after `$vg-security-audit-milestone` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<objective>
Cross-phase security correlation that per-phase `/vg:secure-phase` cannot catch.

Three operations:
1. **Decay**: auto-escalate unresolved OPEN threats, auto-archive old MITIGATED
2. **Correlate**: apply `config.security.composite_rules` to detect threats spanning multiple phases (e.g., broken-auth + broken-access = critical composite)
3. **Report**: generate `${PLANNING_DIR}/security-audit-{date}.md` with trends, open counts, composite risks

Run before milestone completion OR on-demand for periodic security posture review.
</objective>

<process>

<step name="0_config">
Source `_shared/config-loader.md` + `_shared/security-register.md` + `_shared/telemetry.md`.

Read:
- `CONFIG_SECURITY_REGISTER_PATH`
- `CONFIG_SECURITY_COMPOSITE_RULES` (yaml list)
- `CONFIG_SECURITY_DECAY_POLICY_*`
- `CONFIG_PATHS_PLANNING_DIR`

Parse args:
- `--dry-run` — don't modify register, just report what would change
- `--since=<ISO>` — limit analysis window
- `--threshold=<severity>` — only report threats at this severity or higher

If register missing:
```
echo "No SECURITY-REGISTER.md yet. Run /vg:secure-phase on at least one phase first."
exit 0
```
</step>

<step name="1_apply_decay">

```bash
if [ "$ARG_DRY_RUN" = "true" ]; then
  echo "━━━ Decay preview (dry-run) ━━━"
  # Parse register, show what WOULD change without writing
  # (helper returns list of pending transitions)
else
  echo "━━━ Applying decay policy ━━━"
  apply_decay_policy
fi
```

Decay rules (from helper):
- `MITIGATED + age ≥ archive_days` → ARCHIVED
- `OPEN/IN_PROGRESS + severity ≥ high + age ≥ escalate_days` → severity +1 tier

Emit telemetry event per transition:
```bash
emit_telemetry "debt_escalated" "$phase" "security-audit-milestone" \
  "{\"threat_id\":\"$tid\",\"severity\":\"$new_sev\",\"age_days\":$age}"
```
</step>

<step name="2_correlate_composite">

Composite correlation: threats spanning ≥ N phases matching specific taxonomy patterns combine into single higher-severity composite.

```bash
${PYTHON_BIN:-python3} - <<'PY'
import re, yaml, json, sys
from pathlib import Path

register = Path("${CONFIG_SECURITY_REGISTER_PATH}")
config_rules = yaml.safe_load("""
${CONFIG_SECURITY_COMPOSITE_RULES_YAML}
""") or []

text = register.read_text(encoding='utf-8')
# Parse Threats table → list of dicts
rows = []
row_re = re.compile(r'^\| (SEC-\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|', re.M)
for m in row_re.finditer(text):
  rows.append({
    "id": m.group(1),
    "severity": m.group(2).strip(),
    "phases": [p.strip() for p in m.group(3).split(",")],
    "taxonomy": [t.strip() for t in m.group(4).split(",")],
    "title": m.group(5).strip(),
    "status": m.group(6).strip(),
  })

# Parse existing Composite table
comp_existing = set()
comp_re = re.compile(r'^\| (COMP-\d+) \|', re.M)
for m in comp_re.finditer(text):
  comp_existing.add(m.group(1))

# Apply rules
new_composites = []
for rule in config_rules:
  patterns = set(rule.get("patterns", []))
  phases_min = rule.get("phases_min", 2)
  # Find OPEN threats matching ALL rule patterns across DIFFERENT phases
  matching = [r for r in rows if r["status"] in ("OPEN","IN_PROGRESS") and any(p in tax for p in patterns for tax in r["taxonomy"])]
  if not matching: continue
  phases_set = set()
  for r in matching: phases_set.update(r["phases"])
  if len(phases_set) >= phases_min:
    comp_id = f"COMP-{len(comp_existing)+len(new_composites)+1:03d}"
    new_composites.append({
      "id": comp_id,
      "components": [r["id"] for r in matching],
      "phases": sorted(phases_set),
      "severity": rule["resulting_severity"],
      "rule": rule["name"],
    })

# Write to register (append to Composite section)
if new_composites and "${ARG_DRY_RUN}" != "true":
  lines = text.splitlines()
  for i, line in enumerate(lines):
    if line.strip().startswith("| Composite ID"):
      # Skip header row + separator
      insert_at = i + 2
      for comp in new_composites:
        row = f"| {comp['id']} | {', '.join(comp['components'])} | {', '.join(comp['phases'])} | {comp['severity']} | {comp['rule']} |"
        lines.insert(insert_at, row)
        insert_at += 1
      break
  register.write_text("\n".join(lines) + "\n", encoding='utf-8')

print(json.dumps({"new_composites": new_composites, "existing_count": len(comp_existing)}))
PY
```

For each new composite, emit telemetry `security_cross_phase_threat`.
</step>

<step name="3_generate_audit_report">

Write `${PLANNING_DIR}/security-audit-${today}.md`:

```markdown
# Security Milestone Audit — ${milestone_id}
Date: {today}
Dry-run: {true|false}

## Executive Summary

- Total threats tracked: {total}
- OPEN: {open_count} ({critical_open}⚡ critical, {high_open} high)
- MITIGATED: {mitigated}
- ARCHIVED: {archived}
- Composite threats: {composite_count} (new this run: {new_comp})

## Decay Transitions This Run

| Threat ID | Transition | Reason |
|-----------|------------|--------|
| SEC-012 | high → critical | unresolved 35d |
| SEC-005 | MITIGATED → ARCHIVED | mitigated 92d ago |

## New Composite Threats

| Composite | Components | Phases | Combined Severity | Rule |
|-----------|-----------|--------|-------------------|------|
| COMP-003 | SEC-002, SEC-014 | 5, 7.8, 7.12 | critical | info-disclosure-chain |

## Open Critical (action required)

{per-threat block: ID, title, phases, evidence needed, suggested mitigation}

## Taxonomy Distribution

{count per STRIDE category} / {count per OWASP Top 10 category}

## Trend (last 4 audits)

| Date | Total | Open | Critical | Composites |
|------|-------|------|----------|------------|
| ... |

## Recommendations

- {if composite emerged}: "Prioritize fixing {composite_id} — touches phases {phases}. Fix components {components}."
- {if escalated}: "{N} threats auto-escalated. Review SECURITY-REGISTER.md decay log."
- {if open critical ≥ 3}: "Milestone cannot complete per config. Run /vg:secure-phase on affected phases."
```

Attach to `${PLANNING_DIR}/milestones/${milestone}/` if milestone dir exists, else to `${PLANNING_DIR}/` root.
</step>

<step name="4_milestone_complete_gate">

If called from `/vg:complete-milestone` flow (via `--milestone-gate`):
- Count open critical threats
- If `config.security.milestone_audit.required_before_milestone_complete == true`:
  - `open_critical > 0` → BLOCK milestone complete
  - Else → PASS

```bash
if [[ "$ARGUMENTS" =~ --milestone-gate ]]; then
  open_crit=$(count threats where status IN (OPEN, IN_PROGRESS) AND severity == "critical")
  if [ "$open_crit" -gt 0 ]; then
    echo "⛔ Milestone gate: ${open_crit} critical threats OPEN. Cannot archive milestone."
    echo "   See: ${PLANNING_DIR}/SECURITY-REGISTER.md"
    exit 1
  fi
fi
```
</step>

<step name="5_pentest_checklist">
## Step 5 — Generate Pen-Test Checklist (v2.5 Phase I)

If `.vg/SECURITY-TEST-PLAN.md` present (Phase D v2.5 artifact), generate a HUMAN-curated pen-test checklist aggregating:
- All HTTP endpoints from phase API-CONTRACTS grouped by auth model
- OPEN threats carry-over from phase SECURITY-REGISTER files
- Risk-profile-aware priority test vectors (critical → chain attacks; low → hygiene only)
- Compliance control mapping based on framework declared in SECURITY-TEST-PLAN §6

Output: `.vg/milestones/{milestone}/SECURITY-PENTEST-CHECKLIST.md` — artifact for external/internal pentesters.

VG does NOT run pentests. It curates + formats info so humans can pentest effectively.

```bash
# Optional via flag --pentest-checklist, or auto when SECURITY-TEST-PLAN.md exists
STP_FILE="${PLANNING_DIR:-.vg}/SECURITY-TEST-PLAN.md"
MILESTONE_ID="${MILESTONE_ID:-}"

# Resolve milestone from arg or STATE.md
if [ -z "$MILESTONE_ID" ] && [[ "$ARGUMENTS" =~ --milestone=([A-Za-z0-9.-]+) ]]; then
  MILESTONE_ID="${BASH_REMATCH[1]}"
fi
if [ -z "$MILESTONE_ID" ] && [ -f "${PLANNING_DIR:-.vg}/STATE.md" ]; then
  MILESTONE_ID=$(grep -oE "current_milestone:\s*\S+" "${PLANNING_DIR:-.vg}/STATE.md" 2>/dev/null | awk '{print $2}')
fi
MILESTONE_ID="${MILESTONE_ID:-M1}"

SHOULD_GEN=false
[[ "$ARGUMENTS" =~ --pentest-checklist ]] && SHOULD_GEN=true
[ -f "$STP_FILE" ] && SHOULD_GEN=true

if [ "$SHOULD_GEN" = "true" ]; then
  if [ ! -f "$STP_FILE" ]; then
    echo "⚠ Pentest checklist requested via --pentest-checklist but SECURITY-TEST-PLAN.md missing."
    echo "  Run /vg:project --update to populate Round 8 (Phase D), then retry."
  else
    echo ""
    echo "━━━ Step 5 — Pen-Test Checklist Generation (Phase I v2.5) ━━━"
    ${PYTHON_BIN:-python3} .claude/scripts/generate-pentest-checklist.py \
      --milestone "$MILESTONE_ID"
    GEN_RC=$?
    if [ "$GEN_RC" -eq 0 ]; then
      echo "  ✓ Checklist ready for pentester hand-off"
      echo "    Location: ${PLANNING_DIR:-.vg}/milestones/${MILESTONE_ID}/SECURITY-PENTEST-CHECKLIST.md"
    elif [ "$GEN_RC" -eq 2 ]; then
      echo "  (milestone ${MILESTONE_ID} has no phases yet — skipped)"
    else
      echo "  ⚠ Checklist generation failed (rc=${GEN_RC}) — see stderr above"
    fi
  fi
fi
```
</step>

</process>

<success_criteria>
- Decay policy applied (escalate stale OPEN, archive old MITIGATED)
- Composite threats computed per config.security.composite_rules
- `${PLANNING_DIR}/security-audit-{date}.md` written with exec summary + trends
- Telemetry events emitted for escalations + composites
- Milestone complete gate: blocks if critical OPEN threats exist
- Zero register corruption on failure (atomic writes via temp file + rename)
</success_criteria>
