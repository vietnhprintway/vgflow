# dev-phases/15-vg-design-fidelity-v1/

Working folder for **Phase 15** of VG workflow harness — being developed concurrently from two repos under dogfood pattern.

## Dogfood pattern

```
RTB project (/d/Workspace/Messi/Code/RTB)         vgflow-repo (/d/Workspace/Messi/Code/vgflow-repo)
─────────────────────────────────────             ─────────────────────────────────────────────
Source of truth for VG harness:                    Distribution mirror:
  .claude/commands/vg/*.md                  ───→   commands/vg/*.md
  .claude/skills/vg-*/SKILL.md              ───→   skills/vg-*/SKILL.md
  .claude/scripts/validators/*.py           ───→   scripts/validators/*.py
                                                   
                                                   Codex skills (auto-generated):
                                                   codex-skills/vg-*/SKILL.md

Phase tracking + dogfood test:                     Phase planning workspace:
  .vg/ROADMAP.md                                   dev-phases/15-vg-design-fidelity-v1/
  .vg/phases/15-vg-design-fidelity-v1/             ├── HANDOFF.md
  .vg/events.db                                    ├── DECISIONS.md
                                                   ├── ROADMAP-ENTRY.md
                                                   ├── CHAT-HISTORY-SUMMARY.md
                                                   └── README.md (this file)
```

## Sync direction

**Forward (source → mirror):**
```bash
cd vgflow-repo && DEV_ROOT="/d/Workspace/Messi/Code/RTB" ./sync.sh
```
Run after editing `.claude/commands/vg/*.md` ở RTB. Propagates skill bodies + scripts + schemas.

**Inverse (vgflow-repo → RTB):** chưa có script. Edit `.claude/...` ở RTB trực tiếp; vgflow-repo dev-phases có thể edit độc lập (planning/spec doc), không cần sync ngược.

## Workflow

1. **Cửa sổ A — RTB project:** dogfood test. Run /vg:* commands trên phase 7.14.x feature work để battle-test gates đang ship trong Phase 15. Báo bug → log evidence → save vào `.vg/events.db`.

2. **Cửa sổ B — vgflow-repo:** ship workflow code. Edit dev-phases/15/* để track decisions, refine. Khi ready để code:
   - Edit skill body / validator ở **RTB `.claude/`** (source of truth, không edit ở vgflow-repo).
   - Run sync.sh propagate.
   - Test ở RTB dogfood.
   - Commit RTB.
   - Sync sang vgflow-repo lần nữa, commit vgflow-repo.

3. **Iteration:** mỗi gate added (vd verify-uimap-injection.py) → ship qua sync → run dogfood test trên RTB phase 7.14.x kế (vd 7.14.4 nếu user roadmap cho phép) → measure false positive/negative → tune.

## Files

- **HANDOFF.md** — overview cho AI session khác đọc đầu tiên. Where to start, what's done, what's next.
- **DECISIONS.md** — full 17 decisions với rationale + dependencies + acceptance per decision.
- **ROADMAP-ENTRY.md** — block từ RTB ROADMAP.md (line 759-790) copy here for offline reference.
- **CHAT-HISTORY-SUMMARY.md** — timeline of decisions với why-because reasoning, useful for context-restore khi session compact.
- **README.md** — bạn đang đọc.

## When to update which file

| What changed | Update |
|---|---|
| New decision locked | DECISIONS.md + RTB ROADMAP.md scope summary |
| RTB ROADMAP entry edited | ROADMAP-ENTRY.md (manual copy) |
| New round of discussion | CHAT-HISTORY-SUMMARY.md (append) |
| Workflow changed | README.md (this file) |
| Pending task done | HANDOFF.md "Pending" section |

## Don't track here

- Skill body code (lives `.claude/...` ở RTB → mirrored vào vgflow-repo `commands/`)
- Validator scripts (lives `.claude/scripts/validators/` ở RTB)
- Test fixtures (`.claude/scripts/tests/` ở RTB)
- Phase artifacts SPECS.md/CONTEXT.md/PLAN.md (lives `.vg/phases/15-*/` ở RTB)

These are tracked in source repo, mirrored automatically. Don't duplicate trong dev-phases — sẽ stale.
