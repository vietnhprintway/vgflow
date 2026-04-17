---
name: "vg-sync"
description: "Sync VG workflow across source → mirror → installations (.claude/ → vgflow/ → ~/.codex/)"
metadata:
  short-description: "Sync VG workflow across source → mirror → installations (.claude/ → vgflow/ → ~/.codex/)"
---

<codex_skill_adapter>
## Codex ⇆ Claude Code tool mapping

This skill was originally designed for Claude Code. When running in Codex CLI:

| Claude tool | Codex equivalent |
|------|------------------|
| AskUserQuestion | request_user_input (free-form text, or number-prefix choices) |
| Task (agent spawn) | Use `codex exec --model <model>` subprocess with isolated prompt |
| TaskCreate/TaskUpdate | N/A — use inline markdown headers and status narration |
| WebFetch | `curl -sfL` or `gh api` for GitHub URLs |
| Bash/Read/Write/Edit/Glob/Grep | Same — Codex supports these natively |

## Invocation

This skill is invoked by mentioning `$vg-sync`. Treat all user text after `$vg-sync` as arguments.

If argument-hint in source frontmatter is not empty and user provides no args, ask once via request_user_input before proceeding.
</codex_skill_adapter>


<objective>
Keep VG workflow files consistent across 3 locations:
1. **Source**: `.claude/commands/vg/` (edit here trong dev repo)
2. **Mirror**: `vgflow/` (distribute this to other projects)
3. **Installations**:
   - `.codex/skills/vg-*/` (current project Codex)
   - `~/.codex/skills/vg-*/` (global Codex — dùng cho mọi project)

Script delegates to `vgflow/sync.sh`. Runs bidirectional sync: edit ở source → mirror về vgflow → deploy tới installations.
</objective>

<process>

<step name="0_detect">

**v1.11.0 R5 — `vgflow/` folder deprecated. Use external `vgflow-repo` clone:**

```bash
# Resolution priority (highest first):
SYNC_SH=""
for candidate in \
  "${VGFLOW_REPO:-}/sync.sh" \
  "../vgflow-repo/sync.sh" \
  "../../vgflow-repo/sync.sh" \
  "${HOME}/Workspace/Messi/Code/vgflow-repo/sync.sh" \
  "vgflow/sync.sh"  ; do
  if [ -f "$candidate" ]; then
    SYNC_SH="$candidate"
    break
  fi
done

if [ -z "$SYNC_SH" ]; then
  echo "⛔ vgflow-repo sync.sh not found."
  echo "   Setup options:"
  echo "   1. Set env: export VGFLOW_REPO=/path/to/vgflow-repo"
  echo "   2. Clone sibling: git clone https://github.com/vietdev99/vgflow ../vgflow-repo"
  echo "   Then re-run /vg:sync"
  exit 1
fi

echo "✓ Using sync script: $SYNC_SH"
export DEV_ROOT="$(pwd)"
```
</step>

<step name="1_run_sync">
Parse args: `--check` (dry-run), `--no-source` (skip source→mirror), `--no-global` (skip ~/.codex)

```bash
bash "$SYNC_SH" $ARGUMENTS
```

Output shows:
- Files changed (new/updated)
- Summary count
- Dry-run indication nếu --check

Exit code:
- 0: nothing to do OR sync applied
- 1 (with --check): drift detected, needs sync
</step>

<step name="2_report">
After apply (not --check), surface:
- Số files synced
- Locations touched
- Nếu có global deploy: remind user Codex sessions hiện tại cần restart để load skills mới

Nếu --check báo drift:
- Suggest: `/vg:sync` (without --check) để apply
- Hoặc `/vg:sync --no-global` nếu không muốn deploy global
</step>

</process>

<success_criteria>
- `.claude/commands/vg/*.md` ↔ `vgflow/commands/vg/*.md` identical
- `.claude/skills/{api-contract,vg-*}/` ↔ `vgflow/skills/` identical
- `.claude/scripts/*.py` ↔ `vgflow/scripts/*.py` identical
- `vgflow/codex-skills/*/SKILL.md` deployed to both `.codex/skills/` và `~/.codex/skills/`
- Report accurate file count delta
- Zero data loss (no silent overwrites khi src missing)
</success_criteria>
