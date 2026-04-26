# Phase 17 — Test Session Reuse — DECISIONS (draft)

**Lock status:** DRAFT — chờ user review từng D-XX trước khi viết SPECS.
**Convention:** Mỗi decision có Why / What / Acceptance criterion; flag
`(LOCKED)` khi user ack.

---

## D-01 — Storage state lifecycle (auth.json per role per run)

**Why:** Login flow tốn 3-5s mỗi lần; nhân số spec files Phase 15 D-16
ship → 15 phút wall-clock thuần login. Storage state là Playwright
canonical pattern cho auth reuse.

**What:**
- Mỗi role declared trong `vg.config.md.environments.local.accounts[]`
  (admin, publisher, advertiser, demand_admin, ...) → 1 storage state
  file: `.auth/<role>.json`.
- Lifecycle: tạo bởi `global-setup.ts` (D-04) trước khi test runner
  chạy; expire sau 24h hoặc nếu Playwright config hash thay đổi.
- Path resolved qua `vg.config.md.test.storage_state_path` (default
  `apps/web/e2e/.auth/`); `.gitignore` thêm pattern này (init step).

**Acceptance:**
- Run `/vg:test {phase}` lần 1: thấy `.auth/admin.json` được tạo, tests
  pass.
- Run lần 2 trong < 24h: KHÔNG thấy login form trong network log; thời
  gian giảm ≥ 30%.
- Xoá `.auth/admin.json` → next run auto-recreate.

---

## D-02 — Helper template: `loginOnce` + `useAuth`

**Why:** `interactive-helpers.template.ts` hiện chỉ có `loginAs(page, role)`
chạy form mỗi lần. Cần extension API mới để consumer có path migrate dần.

**What:**
- Thêm 2 export mới (giữ `loginAs` legacy):
  ```typescript
  // Login một lần, persist storage state. Idempotent.
  export async function loginOnce(role: string, opts?: { storagePath?: string }): Promise<string>
  // Returns: absolute path to .auth/<role>.json

  // Decorator dùng trong test.use; reads vg.config.test.storage_state_path
  export function useAuth(role: string): { storageState: string }
  ```
- `loginOnce` đọc credentials từ `vg.config.environments.local.accounts[role]`
  (KHÔNG hardcode); sử dụng Playwright `request.context()` để login lập
  trình (bypass UI khi project có API auth) HOẶC fallback browser flow.
- Generated specs sẽ dùng `test.use(useAuth(ROLE))` thay cho `beforeEach
  loginAs`.

**Acceptance:**
- TypeScript check pass; `interactive-helpers.template.ts` thêm 2 exports
  + 1 unit test stub trong consumer apps/web/e2e/__test__/.
- Migrate guide ở `_shared/templates/MIGRATION-helpers.md` 1 trang.

---

## D-03 — Update Phase 15 D-16 templates: `test.use(useAuth)` thay `beforeEach(loginAs)`

**Why:** 10 templates Phase 15 D-16 hiện có pattern:
```typescript
test.beforeEach(async ({ page }) => {
  await loginAs(page, ROLE);
  await page.goto(ROUTE);
});
```
→ login mỗi test trong file. Với 4 + 6 = 10 file × N test/file → bùng nổ.

**What:**
- Thay 10 `*.test.tmpl` files (filter-{coverage,stress,state-integrity,
  edge} + pagination-{navigation,url-sync,envelope,display,stress,edge})
  pattern thành:
  ```typescript
  test.use(useAuth(ROLE));
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTE);   // chỉ goto, KHÔNG login
  });
  ```
- Matrix renderer (`filter-test-matrix.mjs`) thêm validator: nếu
  template kết quả vẫn còn `loginAs(page, ROLE)` trong file body → emit
  warning ở stderr.

**Acceptance:**
- Re-render matrix với canonical fixture G-CAMPAIGN-LIST × status × page
  → 10 file output không có `loginAs` call (chỉ `useAuth`).
- Phase 15 acceptance test (`test_phase15_acceptance.py::TestPhase15Templates`)
  thêm assertion: mỗi template có `useAuth` không có `loginAs`.

---

## D-04 — Playwright `global-setup.ts` template

**Why:** Playwright `globalSetup` chạy 1 lần trước toàn test run — nơi
lý tưởng để pre-create tất cả storage state files. Hiện vgflow-repo
KHÔNG ship template này; consumer phải tự viết.

**What:**
- Thêm `commands/vg/_shared/templates/playwright-global-setup.template.ts`
  content:
  ```typescript
  // Đọc vg.config roles, loginOnce mỗi role, write .auth/<role>.json
  // Skip nếu file < 24h (cache hit).
  ```
- Thêm `commands/vg/_shared/templates/playwright-config.partial.ts` —
  fragment user merge vào `playwright.config.ts`:
  ```typescript
  globalSetup: require.resolve('./e2e/global-setup'),
  ```
- `/vg:init` (init.md) detect Playwright project → copy 2 templates +
  show merge instructions.

**Acceptance:**
- Sample consumer (RTB) chạy `npx playwright test --list` thấy
  `globalSetup` được wire; 1 lần `npm run test` thấy `.auth/admin.json`
  được tạo lần đầu, lần 2 skip (cache log).

---

## D-05 — vg.config defaults: workers + fullyParallel + storage_state_path

**Why:** Default Playwright config trong consumer projects thường
`workers: 1` + `fullyParallel: false` (an toàn nhưng chậm). VG biết test
shape (independent specs from codegen) nên có thể đề xuất defaults tốt
hơn.

**What:**
- Thêm vào `vg.config.template.md`:
  ```yaml
  test:
    storage_state_path: "apps/web/e2e/.auth/"
    storage_state_ttl_hours: 24
    playwright:
      workers: 4
      fully_parallel: true
      reuse_existing_server: true
  ```
- `/vg:test` step 5d-pre đọc 4 keys này, emit Playwright config snippet
  vào console nếu detect mismatch với existing `playwright.config.ts`.

**Acceptance:**
- Fresh `vg.config.md` từ template có `test:` block.
- `/vg:test` log "ℹ Playwright config: workers=4, fullyParallel=true,
  storage at apps/web/e2e/.auth/".

---

## D-06 — Validator `verify-test-session-reuse.py`

**Why:** Catch regression — generated specs vẫn còn `beforeEach loginAs`
sau Phase 17 ship → validator BLOCK. Cũng catch khi consumer xoá
`global-setup.ts` (bug class).

**What:**
- New `scripts/validators/verify-test-session-reuse.py`:
  - Scan `${PHASE_DIR}/.vg-tmp/generated-tests/` (hoặc
    `apps/web/e2e/generated/`) cho `loginAs(` calls outside global-setup.
  - WARN nếu tìm thấy ≥ 1 spec dùng `loginAs` trong `beforeEach` (không
    BLOCK — backward compat consumer chưa migrate).
  - Sau 2 release cycle: escalate WARN → BLOCK (D-XX-followup).
- Wired vào `/vg:test` step 5d-r7 (existing console monitoring gate
  position, easy add).
- Registered trong `scripts/validators/registry.yaml`.

**Acceptance:**
- Test fixture spec với `beforeEach loginAs` → validator emits WARN.
- Test fixture spec với `test.use(useAuth)` → validator PASS.
- Wired in `/vg:test` step 5d-r7.

---

## Deferred / explicit non-decisions

- **API auth bypass** (Playwright `request.post('/api/login')` trong
  loginOnce) — sẽ optional auto-detect nhưng KHÔNG required; consumer
  có thể disable qua `test.login_strategy: ui_form` nếu API auth phức tạp.
- **Multi-browser storage state** (Chromium + Firefox + WebKit khác
  format) — defer; default chỉ Chromium (đã cover 95% VG use case).
- **Encrypted storage state** (auth tokens trong `.auth/`) — defer;
  documented `.gitignore .auth/` là đủ cho dev workflow.
