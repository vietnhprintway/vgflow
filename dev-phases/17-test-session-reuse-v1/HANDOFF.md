# Phase 17 — Test Session Reuse — HANDOFF

**Status:** PLANNING (decisions drafted, awaiting user lock)
**Created:** 2026-04-27
**Estimated effort:** 8–10h
**Dependencies:** Phase 15 D-16 (filter+pagination rigor pack ships 10 spec files/control — multiplier for the waste this phase fixes)
**Risk:** LOW (template + helper changes; backward-compatible — old generated specs keep working until regen)

---

## TL;DR — what this phase does

Trong Phase 7.14.3 RTB user quan sát: cửa sổ test dashboard mở đi mở lại
nhiều lần khi `/vg:test` chạy. Browser launch + login + load dashboard
mỗi spec file → tốn tài nguyên + thời gian wall-clock, đặc biệt nghiêm
trọng SAU Phase 15 D-16 (rigor pack tạo 10 spec files / filter control;
1 control × admin + publisher + advertiser × 10 files = 30 lần restart).

**Root cause** (3 lớp):
1. `interactive-helpers.template.ts` `loginAs(page, ROLE)` chạy form login
   FULL FLOW mỗi lần — không produce/consume `storageState.json`.
2. Generated specs mặc định `test.beforeEach(loginAs)` — mỗi test chạy
   lại login.
3. Playwright project config trong consumer projects thường default
   `workers: 1` + `fullyParallel: false` → spec files chạy tuần tự,
   browser context không share.

**Fix shape:**
- Helper template thêm `loginOnce(role) → .auth/${role}.json` + helper
  `useAuth(role)` wrap `test.use({ storageState })`.
- Generated spec templates (Phase 15 10 templates) chuyển từ `beforeEach
  loginAs` → `test.use(useAuth(ROLE))`.
- Ship `playwright.global-setup.ts` template auto-discover roles từ vg.config
  + login một lần per role per run.
- Default vg.config profile bump: `playwright.workers: 4`,
  `fullyParallel: true`, `storage_state_path: '.auth/'`.
- `/vg:test` step 5d-pre setup gate: nếu thấy storage state file stale
  (>24h) → re-run global setup.

**Expected impact** (measured in Phase 15 dogfood once shipped):
- Login flow runs: O(N spec files) → O(M roles), thường M ≤ 5.
- Wall-clock test time: -50% đến -80% với phase đông spec files.
- Browser process churn: từng start/stop per file → 4 worker processes
  pool reuse trong toàn run.

---

## Why now (vs defer)

Phase 15 D-16 vừa ship sẽ bùng nổ vấn đề này:
- 1 filter control = 4 spec files; 1 pagination control = 6.
- RTB Phase 7.14.3 demo có ~3 list views × ~2 controls × ~3 roles =
  ~180 spec files generated.
- Mỗi spec login lại = ~5s overhead → **15 phút wall-clock thuần login**
  trên một phase test.

Ship Phase 17 trước khi consumer dogfood Phase 15 sẽ tránh spike user
phẫn nộ về chi phí test.

---

## Out of scope (defer Phase 18+)

- Network mocking / API stubbing để bypass real backend (orthogonal — D-16
  edge cases vẫn cần real 500 errors).
- Visual regression baseline storage (Phase 15 D-12 đã cover wave-scoped
  drift; phase-level baseline là khác chuyên đề).
- Test data factory / seed orchestration — separate chuyên đề.

---

## Files trong working folder

- `HANDOFF.md` — bạn đang đọc
- `DECISIONS.md` — 6 decisions D-01..D-06 detail (auth lifecycle,
  template updates, global setup, config defaults)
- `ROADMAP-ENTRY.md` — block draft cho `vgflow-repo/dev-phases/ROADMAP.md`
- `SPECS.md` — sẽ tạo SAU khi user lock decisions
- `BLUEPRINT.md` — sẽ tạo SAU SPECS

---

## Source-of-truth & sync

Per Phase 15 pattern (HANDOFF §"How to start work"):
- Edit ở **vgflow-repo top-level** (commands/, scripts/, schemas/, skills/, templates/)
- Sync sang RTB (consumer dogfood) qua `./install.sh` hoặc patched `./sync.sh`
- Planning docs (HANDOFF, DECISIONS, SPECS, BLUEPRINT) **không sync** —
  meta workspace chỉ cho dev.
