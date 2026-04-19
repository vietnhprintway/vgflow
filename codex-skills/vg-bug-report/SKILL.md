---
name: "vg-bug-report"
description: "Auto-detect workflow bugs + push to GitHub issues on vietdev99/vgflow. Opt-out default, anonymous URL fallback if no gh auth."
metadata:
  short-description: "Auto-detect workflow bugs + push to GitHub issues on vietdev99/vgflow. Opt-out default, anonymous URL fallback if no gh auth."
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

This skill is invoked by mentioning `$vg-bug-report`. Treat all user text after `$vg-bug-report` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<rules>
1. **Opt-out default** — first install prompts consent. User can disable via `--disable-all`.
2. **Privacy-first** — redact project paths, names, emails, phase IDs before upload.
3. **Dedup** — local sent cache + GitHub issue search by signature.
4. **Rate limit** — max 5 events per session (configurable via `config.bug_reporting.max_per_session`).
5. **3-tier send** — gh CLI (authenticated) → URL fallback (anonymous) → silent queue (if auto_send_minor=false).
6. **Severity threshold** — only immediate-send if severity >= threshold. Lower severities queued for weekly flush.
</rules>

<objective>
Auto-report workflow bugs to vietdev99/vgflow. Users help improve VG by letting AI detect issues (schema violations, helper errors, user pushback, gate loops) and report them.

Modes:
- `--flush` — send queued events now
- `--queue` — show pending local queue
- `--disable=<signature>` — suppress future reports of a specific signature
- `--disable-all` — disable entire bug reporter
- `--enable` — re-enable after disable
- `--stats` — local statistics
- `--test` — send test bug to verify setup
- Without flags → prompt consent if not yet configured, else show status
</objective>

<process>

**Source:**
```bash
source "${REPO_ROOT}/.claude/commands/vg/_shared/lib/bug-reporter.sh"
```

<step name="0_parse">
Parse flags:
```bash
MODE="status"
SIG=""
for arg in $ARGUMENTS; do
  case "$arg" in
    --flush)          MODE="flush" ;;
    --queue)          MODE="queue" ;;
    --disable=*)      MODE="disable"; SIG="${arg#*=}" ;;
    --disable-all)    MODE="disable-all" ;;
    --enable)         MODE="enable" ;;
    --stats)          MODE="stats" ;;
    --test)           MODE="test" ;;
  esac
done
```
</step>

<step name="1_dispatch">

### Mode: `status` (default)

```bash
bug_reporter_consent_prompt  # prompts if not yet configured
if bug_reporter_enabled; then
  echo "✓ Bug reporting enabled"
  count=$(bug_reporter_session_count)
  echo "  Session events: ${count}"
  local queue="${CONFIG_BUG_REPORTING_QUEUE:-.claude/.bug-reports-queue.jsonl}"
  if [ -f "$queue" ]; then
    echo "  Queued (pending flush): $(wc -l < "$queue")"
  fi
  local sent="${CONFIG_BUG_REPORTING_SENT_CACHE:-.claude/.bug-reports-sent.jsonl}"
  if [ -f "$sent" ]; then
    echo "  Total sent: $(wc -l < "$sent")"
  fi
else
  echo "⚠ Bug reporting disabled. Enable: /vg:bug-report --enable"
fi
```

### Mode: `flush`

```bash
bug_reporter_queue_flush
```

### Mode: `queue`

```bash
bug_reporter_queue_show
```

### Mode: `disable=SIG`

```bash
local disabled="${CONFIG_BUG_REPORTING_DISABLED:-.claude/.bug-reports-disabled.txt}"
mkdir -p "$(dirname "$disabled")"
echo "$SIG" >> "$disabled"
echo "✓ Signature $SIG suppressed. Future reports ignored."
```

### Mode: `disable-all`

```bash
${PYTHON_BIN} -c "
import re
cfg = '.claude/vg.config.md'
txt = open(cfg, encoding='utf-8').read()
txt = re.sub(r'(bug_reporting:\n  enabled:)\s*true', r'\1 false', txt)
open(cfg, 'w', encoding='utf-8').write(txt)
print('✓ Bug reporting disabled. Existing queue preserved but not sent.')
"
```

### Mode: `enable`

```bash
${PYTHON_BIN} -c "
import re
cfg = '.claude/vg.config.md'
txt = open(cfg, encoding='utf-8').read()
txt = re.sub(r'(bug_reporting:\n  enabled:)\s*false', r'\1 true', txt)
open(cfg, 'w', encoding='utf-8').write(txt)
print('✓ Bug reporting enabled. Run /vg:bug-report --flush to send queued events.')
"
```

### Mode: `stats`

```bash
echo "=== Bug Reporter Stats ==="
local queue_count=0 sent_count=0 disabled_count=0
[ -f "${CONFIG_BUG_REPORTING_QUEUE:-.claude/.bug-reports-queue.jsonl}" ] && queue_count=$(wc -l < "${CONFIG_BUG_REPORTING_QUEUE:-.claude/.bug-reports-queue.jsonl}")
[ -f "${CONFIG_BUG_REPORTING_SENT_CACHE:-.claude/.bug-reports-sent.jsonl}" ] && sent_count=$(wc -l < "${CONFIG_BUG_REPORTING_SENT_CACHE:-.claude/.bug-reports-sent.jsonl}")
[ -f "${CONFIG_BUG_REPORTING_DISABLED:-.claude/.bug-reports-disabled.txt}" ] && disabled_count=$(wc -l < "${CONFIG_BUG_REPORTING_DISABLED:-.claude/.bug-reports-disabled.txt}")
echo "  Queued: $queue_count"
echo "  Sent: $sent_count"
echo "  Disabled signatures: $disabled_count"
echo ""
echo "Top 5 most-reported types (from sent cache):"
[ -f "${CONFIG_BUG_REPORTING_SENT_CACHE}" ] && ${PYTHON_BIN} -c "
import json, collections
from pathlib import Path
p = Path('${CONFIG_BUG_REPORTING_SENT_CACHE:-.claude/.bug-reports-sent.jsonl}')
if p.exists():
    types = [json.loads(l).get('signature','') for l in p.read_text().splitlines() if l]
    for t, c in collections.Counter(types).most_common(5):
        print(f'  - {t}: {c}')
"
```

### Mode: `test`

```bash
echo "=== Test bug report (dry run) ==="
report_bug "test-$(date +%s)" "test_event" "This is a test event from /vg:bug-report --test" "minor"
echo "Check: /vg:bug-report --queue"
echo "Send: /vg:bug-report --flush"
```
</step>

</process>

<success_criteria>
- `status` mode prompts consent if config missing, shows state otherwise
- `flush` sends queue via gh CLI or URL fallback
- `disable=SIG` adds signature to disabled list, suppresses future reports
- `disable-all` / `enable` toggle config.bug_reporting.enabled
- `stats` shows queued/sent/disabled counts + top types
- `test` creates sample event end-to-end
</success_criteria>
