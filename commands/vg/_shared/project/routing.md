<step name="1_route_mode">
## Step 1: Route to mode (state-aware suggestion if MODE not explicit)

If user passed an explicit flag (`--update`, `--migrate`, etc.), validate flag matches state — warn if mismatch but proceed. If NO flag, present **state-tailored menu** (different options shown based on STATE category — không cần user nhớ flag nào).

```bash
# Validate explicit flags against state — warn if mismatch
if [ -n "$MODE" ]; then
  case "${MODE}-${STATE}" in
    migrate-greenfield|migrate-fully-initialized)
      echo "⚠ --migrate yêu cầu PROJECT.md cũ tồn tại + FOUNDATION.md missing."
      echo "   Hiện trạng: ${STATE}. Migration không cần thiết."
      echo "   Bạn có thể đang muốn: $([ "$STATE" = "greenfield" ] && echo "/vg:project (first-time)" || echo "/vg:project --update")"
      exit 0
      ;;
    init_only-greenfield|init_only-legacy-v1)
      echo "⚠ --init-only yêu cầu FOUNDATION.md tồn tại."
      echo "   Hiện trạng: ${STATE}."
      echo "   Bạn có thể đang muốn: $([ "$STATE" = "legacy-v1" ] && echo "/vg:project --migrate" || echo "/vg:project (first-time)")"
      exit 0
      ;;
    update-greenfield|milestone-greenfield)
      echo "⚠ --${MODE} yêu cầu artifacts đã tồn tại. Hiện trạng: greenfield."
      echo "   Bạn có thể đang muốn: /vg:project (first-time)"
      exit 0
      ;;
  esac
fi

# Auto-detect mode based on state if no explicit flag
if [ -z "$MODE" ]; then
  case "$STATE" in
    draft-in-progress)    MODE="resume_check" ;;     # Always offer resume/discard first
    fully-initialized)    MODE="state_menu_full" ;;  # Show full re-run menu (view/update/milestone/rewrite)
    legacy-v1)            MODE="state_menu_legacy" ;;# Recommend migrate, offer alternatives
    brownfield-fresh)     MODE="state_menu_brown" ;; # Recommend first-time with codebase scan, or migrate hint
    greenfield)           MODE="first_time" ;;       # Direct to capture (Round 1)
  esac
fi
```

### State menus (presented to user — proactive suggestion, no need to remember flags)

**state=fully-initialized → `state_menu_full`:**
```
✅ Project đã đầy đủ artifacts (PROJECT + FOUNDATION + config). Bạn muốn:

   [v] View      In hiện trạng, không đổi gì                  (default safe)
   [u] Update    Discussion bổ sung, MERGE giữ phần không touch
   [m] Milestone Append milestone mới (foundation untouched)
   [w] Rewrite   Reset toàn bộ (backup → .archive/{ts}/, full re-run)
   [c] Cancel    Exit, không làm gì

   Nhập 1 ký tự: [v/u/m/w/c]
```
Map answer to MODE: v→view, u→update, m→milestone, w→rewrite. Default if cancelled = view.

**state=legacy-v1 → `state_menu_legacy`:**
```
⚠ Project legacy v1 format — có PROJECT.md cũ nhưng chưa có FOUNDATION.md.

   Đề xuất: ⭐ [m] Migrate (RECOMMENDED)
            Tự extract FOUNDATION.md từ PROJECT.md + scan codebase + vg.config.md cũ
            Backup PROJECT.md v1 → ${PLANNING_DIR}/.archive/{ts}/PROJECT.v1.md
            → /vg:project --migrate

   Lựa chọn khác:
   [v] View    In PROJECT.md hiện có, không đổi
   [w] Rewrite Bỏ hết v1, làm lại từ đầu (backup v1)
   [c] Cancel  Exit

   Nhập 1 ký tự: [m/v/w/c]   (default: m)
```
Map: m→migrate, v→view, w→rewrite, c→exit.

**state=brownfield-fresh → `state_menu_brown`:**
```
🗂  Phát hiện codebase hiện có ($CODEBASE_HINT) nhưng chưa có planning artifacts.

   Đề xuất: ⭐ [f] First-time với codebase scan (RECOMMENDED)
            Bot sẽ scan codebase trước, suggest defaults cho 7-round discussion.
            User chỉ cần xác nhận / điều chỉnh.
            → /vg:project (sẽ auto detect codebase trong Round 2)

   Lựa chọn khác:
   [d] Describe — chỉ mô tả thuần text, bỏ qua scan codebase (greenfield-style)
   [c] Cancel   Exit

   Nhập 1 ký tự: [f/d/c]   (default: f)
```
Map: f→first_time (codebase-aware), d→first_time (no scan), c→exit.

**state=draft-in-progress → `resume_check`:** (same as before — offer resume/discard/view of draft)

**state=greenfield → `first_time` direct:** No menu, jump straight to Round 1 capture (most common new-project case).

### Pretty header before menu

Always print MODE chosen + brief explanation before invoking handler:
```
━━━ Mode: [view|update|milestone|rewrite|migrate|first_time|init_only] ━━━
{1-line description of what's about to happen}
```

User chỉ cần gõ `/vg:project` — toàn bộ logic tự dẫn dắt.
</step>

<step name="2a_resume_check">
## Step 2a: Resume draft check (if `.project-draft.json` exists)

Read draft, show progress, ask user:

```bash
if [ "$MODE" = "resume_check" ]; then
  ${PYTHON_BIN} - "$DRAFT_FILE" <<'PY'
import json, sys, datetime
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ts = d.get("started_at", "?")
try:
  started = datetime.datetime.fromisoformat(ts)
  age_min = int((datetime.datetime.now(started.tzinfo) - started).total_seconds() / 60)
except Exception:
  age_min = "?"
print(f"Draft from {ts} (age {age_min}m), at Round {d.get('current_round','?')}/7")
print(f"Captured description: {d.get('captured', {}).get('description', '(none)')[:120]}...")
PY
fi
```

Use AskUserQuestion:
- "Resume draft from Round X?" → [r] Resume / [d] Discard + restart / [v] View draft only

If resume → load draft state → jump to current round.
If discard → `rm -f $DRAFT_FILE` → set `MODE=first_time`.
If view → pretty-print draft → exit.
</step>

<step name="2b_mode_menu">
## Step 2b: Mode menu (when artifacts exist, no explicit mode flag)

Use AskUserQuestion with exact wording:

```
"PROJECT.md + FOUNDATION.md đã tồn tại. Bạn muốn:
 [v] View          — In hiện trạng, không đổi gì (default safe)
 [u] Update        — Discussion bổ sung, MERGE giữ phần không touch
 [m] New milestone — Append milestone mới + mô tả mục tiêu
 [w] Rewrite       — Reset toàn bộ (backup → .archive/{ts}/, full re-run)"
```

Map answer to MODE: v→view, u→update, m→milestone, w→rewrite. Default if cancelled = view.
</step>

<step name="3_mode_view">
## Step 3 (mode=view): Pretty-print current state

```bash
if [ "$MODE" = "view" ]; then
  echo ""
  echo "## ━━━ Project Overview ━━━"
  echo ""
  if [ -f "$FOUNDATION_FILE" ]; then
    # Print Foundation table + Decisions section
    sed -n '/^## Platform/,/^## Open/p' "$FOUNDATION_FILE"
    echo ""
    sed -n '/^## Decisions/,/^## /p' "$FOUNDATION_FILE" | head -60
  else
    echo "(no FOUNDATION.md — run /vg:project --migrate to create)"
  fi
  echo ""
  echo "## ━━━ Project ━━━"
  [ -f "$PROJECT_FILE" ] && head -50 "$PROJECT_FILE"
  echo ""
  echo "## ━━━ Config (auto-derived) ━━━"
  [ -f "$CONFIG_FILE" ] && grep -E "^(name|dev_command|build_command|deploy|infra_markers):" "$CONFIG_FILE" | head -20
  echo ""
  echo "Modes: --update | --milestone | --rewrite | --migrate"
  exit 0
fi
```
</step>
