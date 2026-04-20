#!/bin/bash
# bootstrap-inject.sh — render <bootstrap_rules> prompt block for agent spawn paths.
#
# PURPOSE (enforces user's hard rule): rules promoted via /vg:learn in any prior
# phase MUST be loaded + injected into the subagent prompts of later phases when
# their scope DSL matches the current step. Without this, `/vg:bootstrap --view`
# reports "7 rules active" but agents never see them — learnings rot in overlay.
#
# USAGE (called from command bash blocks before Agent spawn):
#
#   source "${REPO_ROOT:-.}/.claude/commands/vg/_shared/lib/bootstrap-inject.sh"
#   BOOTSTRAP_RULES_BLOCK=$(vg_bootstrap_render_block "$BOOTSTRAP_PAYLOAD_FILE" "$STEP_NAME")
#
# Then interpolate ${BOOTSTRAP_RULES_BLOCK} into the Agent prompt ~= after the
# static rules block, before task/contract/goals context. On empty → block is
# the string "(no project-specific rules match this step)" so grep gates can
# verify the block always appears (no silent skip).
#
# HARD RULE (enforced by callers, not this helper): every Agent spawn path in
# build/blueprint/review/scope MUST include <bootstrap_rules>${BOOTSTRAP_RULES_BLOCK}
# </bootstrap_rules>. The integrity checker `vg_bootstrap_verify_injection` below
# verifies this statically.

set +e  # never block caller on helper failure — we fail open to empty block

vg_bootstrap_render_block() {
  local payload_file="${1:-}"
  local step_name="${2:-unknown}"

  if [ -z "$payload_file" ] || [ ! -s "$payload_file" ]; then
    echo "(no bootstrap payload — helper not called or loader failed)"
    return 0
  fi

  # Payload shape (from bootstrap-loader.py --emit all):
  #   { "rules": [{"id","title","prose","target_step","scope",...}],
  #     "overlay": {...}, "overlay_rejected": [...] }
  #
  # Rule selection:
  #   - target_step == $step_name OR target_step == 'global' OR absent (matches all)
  #   - loader already pre-filtered by scope DSL against phase metadata

  ${PYTHON_BIN:-python3} - "$payload_file" "$step_name" <<'PY' 2>/dev/null
import json, sys
from pathlib import Path

payload_path = sys.argv[1]
step = sys.argv[2]

try:
    data = json.loads(Path(payload_path).read_text(encoding='utf-8'))
except Exception as e:
    print(f"(bootstrap payload unreadable: {e})")
    sys.exit(0)

rules = data.get('rules') or []
if not rules:
    print("(no project-specific rules match this step — bootstrap empty or scope no-match)")
    sys.exit(0)

matched = []
for r in rules:
    target = (r.get('target_step') or '').strip()
    if target in ('', 'global', step):
        matched.append(r)

if not matched:
    print(f"(no project-specific rules target step='{step}' — skipped {len(rules)} rules with other targets)")
    sys.exit(0)

# Emit one PROJECT RULE block per matched rule. Prose is the executable prompt;
# title is the human-readable label; id is for telemetry correlation.
out = []
for r in matched:
    rid = r.get('id', 'L-???')
    title = (r.get('title') or '(untitled)').strip()
    prose = (r.get('prose') or '').rstrip()
    out.append(f"### PROJECT RULE {rid}: {title}\n{prose}\n")

print('\n'.join(out))
PY
}

# Emit telemetry event for each rule actually rendered into a prompt. Called AFTER
# vg_bootstrap_render_block succeeds and BEFORE Agent spawn, so downstream tools
# (`/vg:bootstrap --trace L-042`, `/vg:telemetry --gate bootstrap.rule_fired`)
# can correlate rule firings with phase outcomes.
vg_bootstrap_emit_fired() {
  local payload_file="${1:-}"
  local step_name="${2:-unknown}"
  local phase="${3:-unknown}"
  local command="${VG_COMMAND:-unknown}"

  [ -z "$payload_file" ] || [ ! -s "$payload_file" ] && return 0

  local telemetry_file="${PLANNING_DIR:-.vg}/telemetry.jsonl"

  ${PYTHON_BIN:-python3} - "$payload_file" "$step_name" "$phase" "$command" "$telemetry_file" <<'PY' 2>/dev/null
import json, sys, os
from datetime import datetime
from pathlib import Path

payload, step, phase, command, telemetry = sys.argv[1:6]

try:
    data = json.loads(Path(payload).read_text(encoding='utf-8'))
except Exception:
    sys.exit(0)

rules = data.get('rules') or []
fired = []
for r in rules:
    target = (r.get('target_step') or '').strip()
    if target in ('', 'global', step):
        fired.append(r.get('id') or 'L-unknown')

if not fired:
    sys.exit(0)

ts = datetime.utcnow().isoformat() + 'Z'
Path(telemetry).parent.mkdir(parents=True, exist_ok=True)
with open(telemetry, 'a', encoding='utf-8') as f:
    for rid in fired:
        f.write(json.dumps({
            'event_type': 'bootstrap.rule_fired',
            'timestamp': ts,
            'rule_id': rid,
            'command': command,
            'phase': phase,
            'step': step,
        }) + '\n')
PY
}

# Static self-check: scan every vg/*.md command file and verify that every
# Agent(subagent_type=...) spawn block contains a <bootstrap_rules> tag. Used
# by CI and by /vg:doctor to enforce the hard injection rule. Missing injection
# in any spawn path is a workflow bug — fix the source file.
#
# Returns 0 if all spawn paths inject; non-zero with per-file violation list
# otherwise. Safe to run on a clean repo — read-only.
vg_bootstrap_verify_injection() {
  local commands_dir="${1:-.claude/commands/vg}"

  ${PYTHON_BIN:-python3} - "$commands_dir" <<'PY'
import re, sys
from pathlib import Path

root = Path(sys.argv[1])
# Find every Agent spawn (orchestrator-spawned subagent) and check its prompt
# body has a <bootstrap_rules> block. We scope to prompts that use the
# executor/planner/reviewer/scanner/scope-discuss role archetype — admin
# commands like /vg:bootstrap --view don't need injection.
SPAWN_RE = re.compile(
    r'Agent\(subagent_type=["\']general-purpose["\'].*?model=\$\{MODEL_'
    r'(EXECUTOR|PLANNER|TEST_GOALS|SCANNER|REVIEWER)\}[^\n]*\n'
    r'(?P<body>(?:[^\n]*\n){1,120})',
    re.MULTILINE,
)
BOOTSTRAP_RE = re.compile(r'<bootstrap_rules>', re.MULTILINE)

violations = []
checked = 0

for md in sorted(root.glob('*.md')):
    text = md.read_text(encoding='utf-8', errors='replace')
    for m in SPAWN_RE.finditer(text):
        checked += 1
        body = m.group('body')
        if not BOOTSTRAP_RE.search(body):
            line = text[:m.start()].count('\n') + 1
            violations.append(f"{md.name}:{line} — Agent spawn (model=MODEL_{m.group(1)}) missing <bootstrap_rules> block")

if violations:
    print(f"⛔ Bootstrap injection violations ({len(violations)} of {checked} spawn paths):")
    for v in violations:
        print(f"   - {v}")
    sys.exit(1)

print(f"✓ All {checked} Agent spawn paths inject <bootstrap_rules>")
sys.exit(0)
PY
}

# If sourced with argument `--verify`, run the static check and exit.
if [ "${1:-}" = "--verify" ]; then
  vg_bootstrap_verify_injection "${2:-.claude/commands/vg}"
  exit $?
fi
