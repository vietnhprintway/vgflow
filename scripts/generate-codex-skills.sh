#!/bin/bash
# Generate Codex skill files from Claude command files.
# Usage: ./scripts/generate-codex-skills.sh [--force]
#
# For each .claude/commands/vg/*.md that doesn't have a codex-skills/vg-X/SKILL.md,
# create one by wrapping the original content with codex adapter prelude.
#
# Codex skill format:
#   - frontmatter: name, description, metadata.short-description
#   - <codex_skill_adapter> block mapping AskUserQuestion → request_user_input,
#     Task → agent_spawn, etc.
#   - Rest of content copied verbatim from source command
#
# Skip if codex-skills/vg-X/SKILL.md already exists (unless --force).

set -e

FORCE=false
for arg in "$@"; do
  [ "$arg" = "--force" ] && FORCE=true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"  # assume vgflow-repo is a sibling of dev RTB
DEV_ROOT="${DEV_ROOT:-$REPO_ROOT/RTB}"         # override via env if structure differs

# Find VG source commands
if [ -d "$DEV_ROOT/.claude/commands/vg" ]; then
  SOURCE_DIR="$DEV_ROOT/.claude/commands/vg"
elif [ -d "$REPO_ROOT/commands/vg" ]; then
  SOURCE_DIR="$REPO_ROOT/commands/vg"  # fallback to mirror
else
  echo "ERROR: Cannot find VG source commands. Set DEV_ROOT env var." >&2
  exit 1
fi

TARGET_DIR="$SCRIPT_DIR/../codex-skills"
mkdir -p "$TARGET_DIR"

GENERATED=0
SKIPPED=0

for src in "$SOURCE_DIR"/*.md; do
  [ -f "$src" ] || continue
  name=$(basename "$src" .md)
  # Skip partial/fragment files
  case "$name" in _*|*-insert) continue ;; esac

  target="$TARGET_DIR/vg-${name}/SKILL.md"

  if [ -f "$target" ] && [ "$FORCE" = "false" ]; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  mkdir -p "$(dirname "$target")"

  # Extract description from source frontmatter
  description=$(awk '/^description:/{gsub(/^description:\s*"?/,""); gsub(/"?\s*$/,""); print; exit}' "$src")

  # Write codex skill with adapter prelude
  cat > "$target" <<EOF
---
name: "vg-${name}"
description: "${description}"
metadata:
  short-description: "${description}"
---

<codex_skill_adapter>
## Codex ⇆ Claude Code tool mapping

This skill was originally designed for Claude Code. When running in Codex CLI, translate tool calls using the table + patterns below.

### Tool mapping table

| Claude tool | Codex equivalent | Notes |
|---|---|---|
| AskUserQuestion | request_user_input (free-form text, or number-prefix choices) | For multi-select, format as "1. Option / 2. Option" and parse reply |
| Task (agent spawn) | \`codex exec --model <model> "<prompt>"\` subprocess | Foreground: \`codex exec ... > /tmp/out.txt\`. Parallel: launch N subprocesses + \`wait\`. See "Agent spawn" below |
| TaskCreate/TaskUpdate/TodoWrite | N/A — use inline markdown headers + status narration | Codex does not have a persistent task tail UI. Write \`## ━━━ Phase X: step ━━━\` in stdout instead |
| Monitor | Bash loop with \`echo\` + \`sleep 3\` polling | Codex streams stdout directly, no separate monitor channel |
| ScheduleWakeup | N/A — Codex is one-shot; user must re-invoke | Skill must tolerate single-execution model; no sleeping |
| WebFetch | \`curl -sfL <url>\` or \`gh api <path>\` | For GitHub URLs prefer \`gh\` for auth handling |
| mcp__playwright{1-5}__* | See "Playwright MCP" below | Playwright MCP tools ARE available in Codex's main orchestrator |
| mcp__graphify__* | \`python -c "from graphify import ..."\` inline | Graphify CLI/module works identically in Codex |
| mcp__context7__*, mcp__exa__*, mcp__firecrawl__* | Skip or fall back to WebFetch | Only available via SDK; not bundled in Codex CLI |
| Bash/Read/Write/Edit/Glob/Grep | Same — Codex supports these natively | No adapter needed |

### Agent spawn (Task → codex exec)

Claude Code spawns isolated agents via \`Task(subagent_type=..., prompt=...)\`. Codex equivalent:

\`\`\`bash
# Single agent, foreground (wait for completion + read output)
codex exec --model gpt-5 "<full isolated prompt>" > /tmp/agent-result.txt 2>&1
RESULT=\$(cat /tmp/agent-result.txt)

# Multiple agents, parallel (Claude's pattern of 1 message with N Task calls)
codex exec --model gpt-5 "<prompt 1>" > /tmp/agent-1.txt 2>&1 &
PID1=\$!
codex exec --model gpt-5 "<prompt 2>" > /tmp/agent-2.txt 2>&1 &
PID2=\$!
wait \$PID1 \$PID2
R1=\$(cat /tmp/agent-1.txt); R2=\$(cat /tmp/agent-2.txt)
\`\`\`

**Critical constraints when spawning:**
- Subagent inherits working directory + env vars, but **no MCP server access** (Codex exec spawns fresh CLI instance without \`--mcp\` wired). Subagent CANNOT call \`mcp__playwright*__\`, \`mcp__graphify__\`, etc.
- Model mapping for this project: \`models.planner\` opus → \`gpt-5\`, \`models.executor\` sonnet → \`gpt-4o\`, \`models.scanner\` haiku → \`gpt-4o-mini\` (or project-configured equivalent). Check \`.claude/vg.config.md\` \`models\` section for actual values and adapt.
- Timeout: wrap in \`timeout 600s codex exec ...\` to prevent hung subagents.
- Return schema: if skill expects structured JSON back, prompt subagent with "Return ONLY a single JSON object with keys: {...}". Parse with \`jq\` or \`python -c "import json,sys; ..."\`.

### Playwright MCP — orchestrator-only rule

Playwright MCP tools (\`mcp__playwright1__browser_navigate\`, \`_snapshot\`, \`_click\`, etc.) ARE available to the main Codex orchestrator (same MCP servers as Claude Code). **BUT subagents spawned via \`codex exec\` do NOT inherit MCP access** — they are fresh CLI instances.

Implication for skills using Haiku scanner pattern (scanner spawns → uses Playwright):
- **Claude model:** spawn haiku agent with prompt → agent calls \`mcp__playwright__\` tools directly
- **Codex model:** TWO options:
  1. **Orchestrator-driven:** main orchestrator calls Playwright tools + passes snapshots/results to subagent as text → subagent returns instructions/analysis only (no tool calls). Slower but preserves parallelism benefit.
  2. **Single-agent:** orchestrator runs scanner workflow inline (no spawn). Simpler but no parallelism; suitable for 1-2 view scans but slow for 14+ views.

Default: **single-agent inline** unless skill explicitly documents the orchestrator-driven pattern for that step.

### Persistence probe (Layer 4) — execution model

For review/test skills that verify mutation persistence:
- Main orchestrator holds Playwright session (claimed via lock manager)
- Pre-snapshot + submit + refresh + re-read all run in orchestrator Playwright calls (not spawned)
- If skill delegates analysis to subagent, orchestrator must capture snapshots + pass text to subagent; subagent returns verdict JSON \`{persisted: bool, pre: ..., post: ...}\`

### Lock manager (Playwright)

Same as Claude:
\`\`\`bash
SESSION_ID="codex-\${skill}-\${phase}-\$\$"
PLAYWRIGHT_SERVER=\$(bash "\${HOME}/.claude/playwright-locks/playwright-lock.sh" claim "\$SESSION_ID")
trap "bash '\${HOME}/.claude/playwright-locks/playwright-lock.sh' release \"\$SESSION_ID\" 2>/dev/null" EXIT INT TERM
\`\`\`

Pool name in Codex: \`codex\` (separate from Claude's \`claude\` pool). Lock manager handles both without collision.

## Invocation

This skill is invoked by mentioning \`\$vg-${name}\`. Treat all user text after \`\$vg-${name}\` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>

EOF

  # Append source content after frontmatter (skip first frontmatter block)
  awk '
    BEGIN { in_fm = 0; past_fm = 0 }
    /^---$/ {
      if (in_fm == 0 && past_fm == 0) { in_fm = 1; next }
      if (in_fm == 1) { in_fm = 0; past_fm = 1; next }
    }
    past_fm == 1 { print }
  ' "$src" >> "$target"

  GENERATED=$((GENERATED + 1))
  echo "✓ Generated: vg-${name}"
done

echo ""
echo "Summary: ${GENERATED} generated, ${SKIPPED} skipped (use --force to overwrite)"
