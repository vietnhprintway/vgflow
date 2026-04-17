#!/bin/bash
# VGFlow Sync — keep source (.claude/commands/vg/) + mirror (vgflow/) + installations in sync
#
# Workflow này có 2 hướng:
#   1. SOURCE → MIRROR: edit tại .claude/commands/vg/ (source of truth trong dev repo)
#      → mirror sang vgflow/commands/vg/ để distribute
#   2. MIRROR → INSTALLATIONS: deploy vgflow/ tới các project install
#      + global ~/.codex/skills/ (cho Codex CLI dùng mọi project)
#
# Usage:
#   ./sync.sh              # full sync (source → mirror → installations)
#   ./sync.sh --check      # dry-run, chỉ report gaps
#   ./sync.sh --no-source  # skip source→mirror (dùng khi edit trực tiếp vgflow/)
#   ./sync.sh --no-global  # skip ~/.codex/ deploy

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE_CHECK=false
SKIP_SOURCE=false
SKIP_GLOBAL=false

for arg in "$@"; do
  case "$arg" in
    --check)    MODE_CHECK=true ;;
    --no-source) SKIP_SOURCE=true ;;
    --no-global) SKIP_GLOBAL=true ;;
    -h|--help)
      head -20 "$0" | tail -19 | sed 's/^# \?//'
      exit 0 ;;
  esac
done

SUMMARY=()
CHANGED=0
MISSING=0

# Helper: compare 2 files, report status
compare() {
  local src="$1" dst="$2" label="$3"
  if [ ! -f "$src" ]; then
    SUMMARY+=("  ✗ SRC MISSING: $label ($src)")
    MISSING=$((MISSING + 1))
    return
  fi
  if [ ! -f "$dst" ]; then
    SUMMARY+=("  + NEW: $label → $dst")
    CHANGED=$((CHANGED + 1))
    [ "$MODE_CHECK" = "false" ] && mkdir -p "$(dirname "$dst")" && cp "$src" "$dst"
    return
  fi
  if ! diff -q "$src" "$dst" >/dev/null 2>&1; then
    SUMMARY+=("  ~ UPDATED: $label")
    CHANGED=$((CHANGED + 1))
    [ "$MODE_CHECK" = "false" ] && cp "$src" "$dst"
  fi
}

# Discover files in a dir pair
sync_dir() {
  local src_dir="$1" dst_dir="$2" pattern="${3:-*}" label="$4"
  [ -d "$src_dir" ] || return
  while IFS= read -r src_file; do
    rel="${src_file#$src_dir/}"
    compare "$src_file" "$dst_dir/$rel" "$label: $rel"
  done < <(find "$src_dir" -name "$pattern" -type f 2>/dev/null)
}

# ============================================================
# 1. SOURCE → MIRROR (.claude/commands/vg/ → vgflow/commands/vg/)
# ============================================================
if [ "$SKIP_SOURCE" = "false" ] && [ -d "$REPO_ROOT/.claude/commands/vg" ]; then
  echo "━━━ 1. Source → Mirror (.claude/ → vgflow/) ━━━"
  sync_dir "$REPO_ROOT/.claude/commands/vg" "$SCRIPT_DIR/commands/vg" "*.md" "commands/vg"
  # Also sync non-markdown support files (yaml string tables, etc.)
  sync_dir "$REPO_ROOT/.claude/commands/vg/_shared" "$SCRIPT_DIR/commands/vg/_shared" "*.yaml" "_shared-yaml"
  sync_dir "$REPO_ROOT/.claude/commands/vg/_shared" "$SCRIPT_DIR/commands/vg/_shared" "*.yml" "_shared-yml"
  # v1.9.2 FIX: sync runnable bash helpers (lib/*.sh + lib/test-runners/*.sh)
  # Previously missed — caused /vg:doctor + test-runners to silently degrade when distributed via vgflow/.
  sync_dir "$REPO_ROOT/.claude/commands/vg/_shared/lib" "$SCRIPT_DIR/commands/vg/_shared/lib" "*.sh" "_shared-lib-sh"
  sync_dir "$REPO_ROOT/.claude/commands/vg/_shared/lib" "$SCRIPT_DIR/commands/vg/_shared/lib" "*.md" "_shared-lib-md"
  sync_dir "$REPO_ROOT/.claude/commands/vg/_shared/lib/test-runners" "$SCRIPT_DIR/commands/vg/_shared/lib/test-runners" "*.sh" "test-runners"

  # Shared Claude skills that VG workflow depends on
  for skill in api-contract vg-design-scanner vg-design-gap-hunter vg-haiku-scanner vg-crossai; do
    sync_dir "$REPO_ROOT/.claude/skills/$skill" "$SCRIPT_DIR/skills/$skill" "*" "skill:$skill"
  done

  # Scripts + templates
  sync_dir "$REPO_ROOT/.claude/scripts" "$SCRIPT_DIR/scripts" "*.py" "scripts"
  sync_dir "$REPO_ROOT/.claude/templates/vg" "$SCRIPT_DIR/templates/vg" "*" "templates"

  echo ""
fi

# ============================================================
# 2. MIRROR → CURRENT PROJECT (.claude/, .codex/ in repo being worked on)
# ============================================================
# Re-sync mirror back to .claude — ensures round-trip consistency
# (most useful when user edits vgflow/ directly)
echo "━━━ 2. Mirror → Current project (.codex/ in $REPO_ROOT) ━━━"
for skill in $(ls "$SCRIPT_DIR/codex-skills" 2>/dev/null); do
  src="$SCRIPT_DIR/codex-skills/$skill/SKILL.md"
  dst="$REPO_ROOT/.codex/skills/$skill/SKILL.md"
  compare "$src" "$dst" "codex-skill:$skill"
done
echo ""

# ============================================================
# 3. MIRROR → GLOBAL CODEX (~/.codex/skills/)
# ============================================================
if [ "$SKIP_GLOBAL" = "false" ] && [ -d "$HOME/.codex" ]; then
  echo "━━━ 3. Mirror → Global Codex (~/.codex/skills/) ━━━"
  for skill in $(ls "$SCRIPT_DIR/codex-skills" 2>/dev/null); do
    src="$SCRIPT_DIR/codex-skills/$skill/SKILL.md"
    dst="$HOME/.codex/skills/$skill/SKILL.md"
    compare "$src" "$dst" "global-codex:$skill"
  done
  echo ""
fi

# ============================================================
# Report
# ============================================================
echo "━━━ Summary ━━━"
if [ ${#SUMMARY[@]} -eq 0 ]; then
  echo "✓ All in sync. Nothing to do."
else
  printf '%s\n' "${SUMMARY[@]}"
  echo ""
  echo "Changed: $CHANGED · Missing src: $MISSING"
fi

if [ "$MODE_CHECK" = "true" ]; then
  echo ""
  echo "(dry-run — no files modified. Re-run without --check to apply.)"
  [ "$CHANGED" -gt 0 ] && exit 1 || exit 0
fi
