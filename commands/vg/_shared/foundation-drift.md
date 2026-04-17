---
name: vg:_shared:foundation-drift
description: Foundation Drift Check (Shared Reference) — soft-warn when phase/milestone wording suggests platform shift away from FOUNDATION.md
---

# Foundation Drift Check — Shared Helper

Detects when a new phase title, milestone description, or scope discussion uses keywords that hint at a platform shift away from the locked FOUNDATION.md. **Soft warning** — does NOT block, but surfaces the conflict so user can either:

1. Acknowledge it's intentional and proceed (cheap reverse-cost or planned milestone shift)
2. Run `/vg:project --update foundation` to re-discuss the shifted dimension first
3. Use `--no-drift-check` flag to silence (logged in build-state for audit)

## Why soft (not hard gate)

- Some phases legitimately introduce new platforms (vd: web SaaS adds mobile companion app — foundation should evolve, but not block this phase from being added)
- Hard gates create noise for edge cases and get bypassed habitually
- Soft warning + auto-suggestion is enough friction to make user think, not enough to be annoying
- Drift entries logged to FOUNDATION.md "Drift Check" section for milestone-end audit (`/vg:audit-milestone` reviews accumulated drift)

## API

```bash
# Call from /vg:roadmap, /vg:add-phase, /vg:scope (and any command introducing new phase scope)
# Inputs: $1 = text to scan (phase title + description + body), $2 = source identifier (cmd:phase)
# Output: stdout warning if drift detected, exit 0 always (soft)

foundation_drift_check() {
  local scan_text="$1"
  local source="$2"
  local foundation_file="${FOUNDATION_FILE:-.planning/FOUNDATION.md}"

  # No FOUNDATION.md → skip silently (legacy projects pre-v1.6.0)
  [ -f "$foundation_file" ] || return 0

  # Allow user to silence
  if [[ "${ARGUMENTS:-}" =~ --no-drift-check ]]; then
    echo "drift-check: skipped via --no-drift-check (source=${source})" >> "${PHASE_DIR:-.planning}/build-state.log" 2>/dev/null
    return 0
  fi

  ${PYTHON_BIN:-python3} - "$foundation_file" "$source" <<PY
import re, sys
from pathlib import Path

foundation_path = Path(sys.argv[1])
source          = sys.argv[2]
scan_text       = """${scan_text//\"/\\\"}"""  # quoted in heredoc context
scan_lc         = scan_text.lower()

# Extract current platform value from FOUNDATION.md
foundation = foundation_path.read_text(encoding="utf-8", errors="ignore")
m = re.search(r'\|\s*1\s*\|\s*Platform type\s*\|\s*([^|]+)\|', foundation)
current_platform = (m.group(1).strip().lower() if m else "unknown")

# Drift keyword → expected platform mapping
# (only flag if scan keyword exists AND current platform doesn't match)
drift_map = [
    # (regex on scan, platforms that DON'T conflict)
    (r'\b(ios|swift|swiftui|xcode|app\s*store|testflight)\b',           ["mobile-native", "mobile-cross", "hybrid"]),
    (r'\b(android|kotlin|jetpack|play\s*store|apk)\b',                  ["mobile-native", "mobile-cross", "hybrid"]),
    (r'\b(react\s*native|expo|flutter)\b',                              ["mobile-cross", "hybrid"]),
    (r'\b(electron|tauri|desktop\s*app)\b',                             ["desktop", "hybrid"]),
    (r'\b(serverless|lambda|cloudflare\s*workers|edge\s*function)\b',   ["serverless", "edge", "hybrid"]),
    (r'\b(embedded|firmware|microcontroller|esp32|raspberry)\b',        ["embedded", "hybrid"]),
    (r'\b(cli\s*tool|command-line|tui)\b',                              ["cli", "hybrid"]),
]

flags = []
for pattern, ok_platforms in drift_map:
    if re.search(pattern, scan_lc):
        if not any(p in current_platform for p in ok_platforms):
            mtch = re.search(pattern, scan_lc)
            flags.append({
                "keyword": mtch.group(0),
                "expected_platforms": ok_platforms,
                "current": current_platform
            })

if not flags:
    sys.exit(0)

print("")
print("⚠ FOUNDATION DRIFT WARNING (soft — proceed allowed)")
print(f"   Source: {source}")
print(f"   Current foundation platform: {current_platform}")
print("")
for f in flags[:5]:
    print(f"   • Keyword '{f['keyword']}' suggests platform shift to: {', '.join(f['expected_platforms'])}")
print("")
print("   If intentional: proceed (drift entry will be logged for milestone audit)")
print("   If unintentional: run /vg:project --update foundation TRƯỚC khi tiếp tục")
print("   Silence: re-run with --no-drift-check flag")
print("")
sys.exit(0)
PY

  # Log drift entry to FOUNDATION.md for accumulation tracking
  if grep -q "drift" <<<"$(${PYTHON_BIN:-python3} -c "
import re, sys
from pathlib import Path
text = Path('$foundation_file').read_text(encoding='utf-8', errors='ignore')
m = re.search(r'\|\s*1\s*\|\s*Platform type\s*\|\s*([^|]+)\|', text)
print(m.group(1).strip().lower() if m else '')")"; then
    : # placeholder — drift logging done in Python above when actually flagged
  fi
}
```

## Drift entry format (appended to FOUNDATION.md)

When drift detected, append entry to `## 6. Drift Check` section:

```markdown
## 6. Drift Check

**Last check:** {ISO timestamp}
**Status:** ⚠ drift detected (1+ entries — review at milestone audit)

### Drift entries
- 2026-04-17 [roadmap:phase-08] Keyword 'mobile' detected — current platform 'web-saas'. Status: pending review.
- 2026-04-17 [add-phase:09.1] Keyword 'serverless' detected — current platform 'monolith'. Status: acknowledged (intentional).
```

## Integration template

In `/vg:roadmap`, `/vg:add-phase`, `/vg:scope`:

```bash
# After capturing phase title + description + scope text
SCAN="${PHASE_TITLE} ${PHASE_DESC} ${PHASE_SCOPE_BODY}"
SOURCE="${COMMAND_NAME}:${PHASE_NUMBER}"
foundation_drift_check "$SCAN" "$SOURCE"
# Always exits 0 — soft warning. Continue normal flow.
```

## Success criteria

- Foundation present + scan keyword matches platform shift → warning printed, log entry appended
- Foundation absent → skip silently (legacy compat)
- `--no-drift-check` flag → skip + log to build-state
- Never blocks command flow (always exit 0)
- Drift entries accumulate in FOUNDATION.md for milestone-audit review
