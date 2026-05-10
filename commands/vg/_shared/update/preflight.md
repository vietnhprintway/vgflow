<!-- v2.73.0 T6-T10 extraction — verbatim step blocks from commands/vg/update.md -->
<!-- v2.88.0 marker-aware: read .vg/.install-target so global mode bypasses
     project-local merge in favor of ~/.vgflow/ refresh + stale cleanup -->
<!-- Group: preflight | Steps: 0_preflight, 0b_marker_branch, 1_check_only_mode -->

<process>

<step name="0_preflight">
```bash
set -u

REPO_ROOT="$(pwd)"
ARGS="${ARGUMENTS:-}"

# Parse --repo= (defaults to vietdev99/vgflow)
REPO="$(printf '%s' "$ARGS" | grep -oE -- '--repo=[^ ]+' | sed 's/^--repo=//' | head -n1)"
REPO="${REPO:-vietdev99/vgflow}"

# Preflight tooling
command -v git      >/dev/null 2>&1 || { echo "git CLI required"; exit 1; }
command -v curl     >/dev/null 2>&1 || { echo "curl required"; exit 1; }
command -v python3  >/dev/null 2>&1 || { echo "python3 required"; exit 1; }

# v2.88.0: detect v3 install-target marker
INSTALL_TARGET=""
if [ -f "${REPO_ROOT}/.vg/.install-target" ]; then
  INSTALL_TARGET="$(tr -d '[:space:]' < "${REPO_ROOT}/.vg/.install-target")"
fi
echo "install-target marker: ${INSTALL_TARGET:-(absent — legacy project mode)}"

HELPER="${REPO_ROOT}/.claude/scripts/vg_update.py"
# Project-mode helper required only when we'll do the project-local merge.
# Global-mode update doesn't touch .claude/ helpers.
if [ "$INSTALL_TARGET" != "global" ] && [ ! -f "$HELPER" ]; then
  echo "vg_update.py missing at ${HELPER}"
  echo "Legacy install detected. Re-install vgflow first:"
  echo "  curl -fsSL https://raw.githubusercontent.com/${REPO}/main/install.sh | bash"
  exit 1
fi

echo "repo=${REPO}"
```
</step>

<step name="0b_marker_branch">
**v2.88.0 — marker-aware divergence.**

When `.vg/.install-target=global`, the project's harness lives in `~/.vgflow/`,
not `.claude/`. `/vg:update` MUST refresh `~/.vgflow/` (via npm or git pull),
re-install hooks at `~/.claude/settings.json` with `--mode global`, AND clean
up any stale legacy files left in `.claude/` that should have been removed
during the original v3 migration but remained from a partial run.

When marker is `project` or absent, fall through to the v2.x project-local
3-way-merge flow (steps 5-9 below).

```bash
if [ "$INSTALL_TARGET" = "global" ]; then
  echo ""
  echo "Global update path (marker=global) — refreshing ~/.vgflow/..."

  HOME_VGFLOW="${HOME}/.vgflow"
  GLOBAL_OK=0

  # Strategy 1: git pull when ~/.vgflow/.git exists (dev clone)
  if [ -d "${HOME_VGFLOW}/.git" ]; then
    echo "  ~/.vgflow is a git clone — running git pull --ff-only origin main"
    if (cd "$HOME_VGFLOW" && git pull --ff-only origin main >/dev/null 2>&1); then
      GLOBAL_OK=1
      echo "  ✓ ~/.vgflow updated to $(cat "${HOME_VGFLOW}/VERSION" 2>/dev/null || echo unknown)"
    else
      echo "  ⚠ git pull failed — falling back to npm"
    fi
  fi

  # Strategy 2: npm global update
  if [ "$GLOBAL_OK" = "0" ] && command -v npm >/dev/null 2>&1; then
    echo "  Updating via npm install -g vgflow@latest..."
    if npm install -g vgflow@latest >/dev/null 2>&1; then
      GLOBAL_OK=1
      echo "  ✓ npm install -g vgflow@latest done"
    else
      echo "  ⚠ npm install failed"
    fi
  fi

  if [ "$GLOBAL_OK" = "0" ]; then
    echo "⛔ Could not update global ~/.vgflow/. Either:"
    echo "   - Make ~/.vgflow a git clone:  git clone https://github.com/${REPO} ~/.vgflow"
    echo "   - Or install npm + run:        npm install -g vgflow@latest"
    exit 1
  fi

  # Re-install hooks with --mode global so settings.json points at ~/.vgflow/
  INSTALL_HOOKS=""
  for candidate in \
    "${HOME_VGFLOW}/scripts/hooks/install-hooks.sh" \
    "${REPO_ROOT}/.claude/scripts/hooks/install-hooks.sh"; do
    if [ -f "$candidate" ]; then
      INSTALL_HOOKS="$candidate"
      break
    fi
  done
  if [ -n "$INSTALL_HOOKS" ]; then
    echo "  Re-installing hooks at ~/.claude/settings.json (--mode global)..."
    if bash "$INSTALL_HOOKS" --target "${HOME}/.claude/settings.json" --mode global >/dev/null 2>&1; then
      echo "  ✓ hooks refreshed"
    else
      echo "  ⚠ hook re-install failed — run manually:"
      echo "     bash ${INSTALL_HOOKS} --target ${HOME}/.claude/settings.json --mode global"
    fi
  fi

  # Clean up stale project-local files that should not exist in global mode.
  # Backup first to .vg/.backup-<ts>/ in case user wants to revert.
  STALE_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  STALE_BACKUP="${REPO_ROOT}/.vg/.backup-${STALE_TS}-stale-cleanup"
  STALE_FOUND=0
  for d in ".claude/commands/vg" ".claude/scripts" ".claude/schemas" ".claude/templates/vg"; do
    if [ -d "${REPO_ROOT}/${d}" ]; then
      STALE_FOUND=$((STALE_FOUND + 1))
    fi
  done
  for d in "${REPO_ROOT}"/.claude/skills/vg-*; do
    [ -d "$d" ] && STALE_FOUND=$((STALE_FOUND + 1))
  done

  if [ "$STALE_FOUND" -gt 0 ]; then
    echo "  Cleaning ${STALE_FOUND} stale project-local dir(s) (backup → ${STALE_BACKUP})..."
    mkdir -p "$STALE_BACKUP"
    for d in ".claude/commands/vg" ".claude/scripts" ".claude/schemas" ".claude/templates/vg"; do
      if [ -d "${REPO_ROOT}/${d}" ]; then
        mkdir -p "$(dirname "${STALE_BACKUP}/${d}")"
        mv "${REPO_ROOT}/${d}" "${STALE_BACKUP}/${d}" 2>/dev/null || true
        echo "    moved ${d} → backup"
      fi
    done
    for d in "${REPO_ROOT}"/.claude/skills/vg-*; do
      [ -d "$d" ] || continue
      base="$(basename "$d")"
      mkdir -p "${STALE_BACKUP}/.claude/skills"
      mv "$d" "${STALE_BACKUP}/.claude/skills/${base}" 2>/dev/null || true
      echo "    moved .claude/skills/${base} → backup"
    done
    echo "  ✓ stale cleanup done. Recover via: cp -r ${STALE_BACKUP}/* ${REPO_ROOT}/"
  fi

  # Bump VGFLOW-VERSION marker for global mode tracking
  if [ -f "${HOME_VGFLOW}/VERSION" ]; then
    cp "${HOME_VGFLOW}/VERSION" "${REPO_ROOT}/.vg/.global-vgflow-version" 2>/dev/null || true
  fi

  echo ""
  echo "✓ Global /vg:update complete. Restart Claude Code / Codex session to load updated harness."
  exit 0
fi

# Marker absent or =project: continue to legacy v2.x project-local merge below.
```
</step>

<step name="1_check_only_mode">
```bash
if printf '%s' "$ARGS" | grep -qE -- '(^|[[:space:]])--check([[:space:]]|$)'; then
  python3 "$HELPER" check --repo "$REPO"
  exit $?
fi
```
</step>

</process>
