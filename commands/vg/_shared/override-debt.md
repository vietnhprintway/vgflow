---
name: vg:_shared:override-debt
description: Override Debt Register (Shared Reference) — track every --allow/--skip/--override-reason usage, auto-expire, block accept on unresolved critical debt
---

# Override Debt Register — Shared Helper

Every VG override flag (`--allow-*`, `--skip-*`, `--override-*`) MUST log to `.planning/OVERRIDE-DEBT.md`. Debt register makes invisible technical debt visible, forces review, blocks `accept` when critical debt is unresolved.

## Config (add to `.claude/vg.config.md`)

```yaml
debt:
  register_path: ".planning/OVERRIDE-DEBT.md"
  auto_expire_days: 14              # entries older than N days without resolution → ESCALATE status
  blocking_severity: ["critical"]   # /vg:accept blocks if open entries at these severities
  severities:
    critical:                       # safety-critical overrides
      - "--allow-missing-commits"
      - "--override-reason"         # build wave accept with issue ID — still tracked
      - "--override-regressions"
    high:
      - "--allow-no-tests"
      - "--skip-design-check"
      - "--allow-intermediate"
      - "--skip-context-rebuild"
    medium:
      - "--skip-crossai"
      - "--skip-research"
      - "--allow-deferred"
```

## API

```bash
# Helper — call AFTER an override is accepted
log_override_debt() {
  local flag="$1"        # e.g. "--allow-missing-commits"
  local phase="$2"       # e.g. "7.12"
  local step="$3"        # e.g. "build.wave-3"
  local reason="$4"      # user-provided justification or auto-derived context
  local register="${CONFIG_DEBT_REGISTER_PATH:-.planning/OVERRIDE-DEBT.md}"

  # Bootstrap file if missing
  if [ ! -f "$register" ]; then
    cat > "$register" <<'HEADER'
# Override Debt Register

Auto-maintained by VG workflow. Every override flag logged here. Entries auto-ESCALATE after `config.debt.auto_expire_days` without resolution. `/vg:accept` blocks while critical entries remain OPEN.

## Entries

| ID | Severity | Phase | Step | Flag | Reason | Logged (UTC) | Status | Resolved |
|----|----------|-------|------|------|--------|--------------|--------|----------|
HEADER
  fi

  # Derive severity from config
  local severity="medium"
  for sev in critical high medium; do
    local flags_var="CONFIG_DEBT_SEVERITIES_${sev^^}"
    if grep -qF "$flag" <<<"${!flags_var:-}"; then severity="$sev"; break; fi
  done

  local id="DEBT-$(date -u +%Y%m%d%H%M%S)-$$"
  local ts="$(date -u +%FT%TZ)"
  printf '| %s | %s | %s | %s | `%s` | %s | %s | OPEN |  |\n' \
    "$id" "$severity" "$phase" "$step" "$flag" "${reason//|/\\|}" "$ts" >> "$register"

  # Emit telemetry event (if F7 enabled)
  if type -t emit_telemetry >/dev/null 2>&1; then
    emit_telemetry "override_used" "$phase" "$step" \
      "{\"flag\":\"$flag\",\"severity\":\"$severity\",\"debt_id\":\"$id\"}"
  fi

  echo "⚠ Override debt logged: ${id} (${severity}). Review: ${register}"
}

# Helper — /vg:accept calls this before UAT
check_blocking_debt() {
  local phase="$1"
  local register="${CONFIG_DEBT_REGISTER_PATH:-.planning/OVERRIDE-DEBT.md}"
  [ -f "$register" ] || return 0

  local blocking_sev="${CONFIG_DEBT_BLOCKING_SEVERITY:-critical}"
  # Count OPEN entries at blocking severity
  local open_count
  open_count=$(awk -F'|' -v sev="$blocking_sev" '
    /^\|[[:space:]]*DEBT-/ {
      gsub(/^ +| +$/, "", $3); gsub(/^ +| +$/, "", $9);
      if (index(sev, $3) > 0 && $9 == "OPEN") c++
    } END { print c+0 }' "$register")

  if [ "$open_count" -gt 0 ]; then
    echo "⛔ ${open_count} OPEN debt entries at blocking severity (${blocking_sev})."
    echo "   Review: ${register}"
    echo "   Resolve: edit Status→RESOLVED + add Resolved date + commit-link/PR-link"
    echo "   Accept cannot proceed with critical debt open."
    return 1
  fi
  return 0
}

# Helper — auto-expire (run at top of every VG command, cheap)
expire_stale_debt() {
  local register="${CONFIG_DEBT_REGISTER_PATH:-.planning/OVERRIDE-DEBT.md}"
  [ -f "$register" ] || return 0
  local days="${CONFIG_DEBT_AUTO_EXPIRE_DAYS:-14}"

  ${PYTHON_BIN:-python3} - <<PY
import re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

register = Path("$register")
cutoff = datetime.now(timezone.utc) - timedelta(days=$days)
text = register.read_text(encoding='utf-8')
lines = text.splitlines()
changed = 0

row_re = re.compile(r'^\|\s*(DEBT-\d+-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*(\S+?)\s*\|\s*(OPEN|RESOLVED|ESCALATED)\s*\|')
out = []
for line in lines:
  m = row_re.match(line)
  if not m or m.group(8) != 'OPEN':
    out.append(line); continue
  try:
    ts = datetime.fromisoformat(m.group(7).replace('Z','+00:00'))
  except Exception:
    out.append(line); continue
  if ts < cutoff:
    out.append(line.replace('| OPEN |', '| ESCALATED |'))
    changed += 1
  else:
    out.append(line)

if changed:
  register.write_text('\n'.join(out) + '\n', encoding='utf-8')
  print(f"Auto-escalated {changed} stale debt entries (> $days days)", file=sys.stderr)
PY
}
```

## Integration points

| Command | Step | Flag | Call |
|---------|------|------|------|
| `build` | resume | `--skip-context-rebuild` | `log_override_debt "--skip-context-rebuild" "$PHASE" "build.resume" "artifacts fresh"` |
| `build` | design | `--skip-design-check` | `log_override_debt "--skip-design-check" "$PHASE" "build.design-manifest" "user override"` |
| `build` | wave | `--allow-missing-commits` | `log_override_debt "--allow-missing-commits" "$PHASE" "build.wave-$N" "missing=$MISSING_TASKS"` |
| `build` | test-infra | `--allow-no-tests` | `log_override_debt "--allow-no-tests" "$PHASE" "build.wave-$N" "test infra not configured"` |
| `build` | hard-gate | `--override-reason=X` | `log_override_debt "--override-reason" "$PHASE" "build.hard-gate" "$REASON_VALUE"` |
| `review` | 4c-pre | `--allow-intermediate` | `log_override_debt "--allow-intermediate" "$PHASE" "review.4c-pre" "NOT_SCANNED=$N, FAILED=$M"` |
| `blueprint` | hard-gate | `--override` | `log_override_debt "--override" "$PHASE" "blueprint.gate" "user proceed with gaps"` |
| `accept` | regression | `--override-regressions=X` | `log_override_debt "--override-regressions" "$PHASE" "accept.regression" "$REASON"` |
| `next` | advance | `--allow-deferred` | `log_override_debt "--allow-deferred" "$PHASE" "next.advance" "DEFERRED pending"` |
| `test` | crossai | `--skip-crossai` | `log_override_debt "--skip-crossai" "$PHASE" "test.crossai" "per-run opt-out"` |

## Accept gate integration

In `.claude/commands/vg/accept.md` step 0 (before UAT):

```bash
source .claude/commands/vg/_shared/override-debt.md  # or inline helpers
expire_stale_debt
if ! check_blocking_debt "$PHASE_NUMBER"; then
  echo ""
  echo "Override (NOT RECOMMENDED): /vg:accept $PHASE_NUMBER --force-accept-with-debt"
  if [[ ! "$ARGUMENTS" =~ --force-accept-with-debt ]]; then exit 1; fi
  log_override_debt "--force-accept-with-debt" "$PHASE_NUMBER" "accept.debt-gate" "user bypass"
fi
```

## Progress surfacing

In `.claude/commands/vg/progress.md` (detect + report):
```bash
if [ -f "${CONFIG_DEBT_REGISTER_PATH}" ]; then
  OPEN=$(awk -F'|' '/\|[[:space:]]*DEBT-/ && $9~/OPEN/ {c++} END{print c+0}' "$register")
  ESC=$(awk -F'|' '/\|[[:space:]]*DEBT-/ && $9~/ESCALATED/ {c++} END{print c+0}' "$register")
  [ "$OPEN$ESC" != "00" ] && echo "⚠ Debt: ${OPEN} OPEN · ${ESC} ESCALATED — see ${register}"
fi
```

## Success criteria

- Every override flag logged to register automatically
- Stale OPEN entries auto-ESCALATE after 14 days
- `/vg:accept` blocks if critical-severity OPEN debt exists
- `/vg:progress` surfaces debt count
- Register is human-editable markdown table (no tool lock-in)
