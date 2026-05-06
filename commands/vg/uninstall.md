---
name: vg:uninstall
description: Remove VGFlow-owned workflow files and hooks from this project
argument-hint: "[--apply] [--purge-state]"
allowed-tools:
  - Bash
  - Read
mutates_repo: true
---

<rules>
1. Default is dry-run. Do not remove files unless user passes `--apply`.
2. Preserve project application code. Remove VGFlow-owned workflow surfaces only.
3. `--purge-state` is extra destructive: also removes `.vg/` and `.planning/`.
4. Removed files are moved to `.vgflow-uninstall-backup/<timestamp>/`.
5. Project-local only: do not modify global `~/.codex` or `~/.claude` config.
</rules>

<process>

```bash
set -euo pipefail

ARGS="${ARGUMENTS:-}"
HELPER=".claude/scripts/vg_uninstall.py"
if [ ! -f "$HELPER" ]; then
  echo "vg_uninstall.py missing at ${HELPER}"
  echo "Fallback: remove VG hooks manually, then delete .claude/commands/vg and .claude/scripts."
  exit 1
fi

python3 "$HELPER" --root . $ARGS
```

</process>
