# Phase 15 — Locked Decisions (D-01..D-17)

Decisions extracted from `/vg:scope` draft chat session (2026-04-26 → 2026-04-27). Final lock awaits formal `/vg:scope 15` skill emission to CONTEXT.md ở RTB project.

---

## D-01: Design source-of-truth extractor (4 format coverage)

**Category:** technical / infra
**Decision:** Extract HTML / PNG (Phase A) + Pencil/Penboard via PenBoard MCP (Phase B) → emit per slug:
- `.planning/design-normalized/refs/{slug}.structural.json` — DOM-AST tree (HTML cheerio AST → tag/class/role/text/order); element box-list (x/y/w/h/style/text) cho Pencil/Penboard XML; OCR + region detection cho PNG-only (opencv-wasm + tesseract.js)
- `.planning/design-normalized/screenshots/{slug}.{state}.png` — pin per state (default/hover/loading/error)
- `.planning/design-normalized/refs/{slug}.interactions.md` — handler map click/hover/keyboard

**Rationale:** Phase 7.14.3 dùng `Read first: campaigns.html` prose link → AI tự diễn giải, output drift nhiều. Reference structured (AST level) cho phép machine compare node-by-node.

**Phase split:** Phase A ship HTML + PNG (cover 90% project). Phase B wire PenBoard MCP server (24 tools available tại `D:\Workspace\Messi\Code\PenBoard\dist\mcp-server.cjs`) — không tự viết Pencil parser.

---

## D-02: design-ref hard-required (R4 MED → CRITICAL)

**Category:** enforcement
**Decision:** Task có `<file-path>` chứa `.tsx/.vue/.jsx/.svelte` mà thiếu `<design-ref slug>` → blueprint reject (plan-checker BLOCK).
**Rationale:** R4 hiện ở MED warn-only, AI bỏ qua. Per memory `feedback_ai_discipline_validator` — rule có thể auto-detect phải hard-block, không warn-only.

---

## D-03: Per-wave structural diff scoped (option C)

**Category:** test rigor
**Decision:** Sau wave commit, chạy `generate-ui-map.mjs --src wave-touched-files --format json` scan code as-built → diff vs `UI-MAP.md` (planner-written as-planned tree, từ blueprint step `2b6b_ui_map`), CHỈ trong scope subtree wave declare touch (mỗi UI-MAP node tag `owner-wave-id`). Drift > threshold trong scope → hard-block, rollback wave.
**Rationale:** Wave có thể build 50% cây (vd Wave 1 = sidebar+topbar, Wave 2 = table). Diff toàn cây sẽ false-fail Wave 1 vì table thiếu. Scope diff catch real drift trong wave's responsibility, không alarm phần wave khác chưa làm.

**Why option C over A/B:**
- Option A (hard-block toàn cây mỗi wave) — too many false alarm.
- Option B (warn-only wave, hard-block phase-end) — drift tích lũy, fix muộn.
- Option C (scoped wave drift) — chặt + chính xác, cost: planner tag `owner-wave-id` cho mỗi UI-MAP node (~30 phút/blueprint).

---

## D-04: i18n option B (lock mẫu strings, AI dịch những gì không có trong mẫu)

**Category:** translation policy
**Decision:** Mẫu EN → app strings xuất hiện trong mẫu phải lock EN. Strings KHÔNG xuất hiện trong mẫu (toast "Saved", error message backend, validation copy) AI dịch theo `i18n.runtime_locale`. AST diff text-node level-by-level — text mismatch trong mẫu = fail.
**Rationale:** Phase 7.14.3 AI tự dịch "Campaigns" → "Chiến dịch" mặc dù mẫu EN. Strict lock EN tuyệt đối quá cứng (toast/error không có trong mẫu cũng phải EN = không practical). Option B: lock cái mẫu có, mở rộng cái mẫu thiếu.

---

## D-05: UAT narrative 4-field template

**Category:** UAT UX
**Decision:** Mỗi UAT prompt phải có 4 field hard-required trước câu p/f/s:
1. `entry` — URL truy cập + role + tài khoản test (vd `http://localhost:5175 + advertiser + advertiser@demo.com / Test123!`)
2. `navigation` — bước-by-bước ("Sidebar > Campaigns > click row có status Working > scroll Daily Budget cell")
3. `precondition` — data state cần thiết ("≥1 campaign status=Working có daily_budget > 0")
4. `expected_behavior` — 1-2 câu mô tả hành vi đúng ("click ô Daily Budget mở inline editor; ESC hủy, Enter save → toast Success + cell render giá trị mới")

---

## D-06: UAT narrative source data

**Category:** infra
**Decision:** AI generate 4 field từ:
- `entry` ← `config.environments.local.dev_command` port-role mapping (5173 admin, 5174 publisher, 5175 advertiser, 5176 demand_admin per CLAUDE.md) + accounts seed file (`apps/api/seed/accounts.json` hoặc tương tự)
- `navigation` ← TEST-GOALS `interactive_controls.entry_path` (đã có ở phase test infra) hoặc routes file inspect
- `precondition` ← TEST-GOALS `precondition` field nếu có (per memory `project_vg_test_goals_enrichment`) hoặc default từ phase seed state
- `expected_behavior` ← TEST-GOALS goal title + acceptance_criteria + CONTEXT D-XX rationale

**Rationale:** Reuse artifact đã có, không hỏi user repeat.

---

## D-07: design-ref UAT narrative (URL + role + region)

**Category:** UAT UX (design fidelity)
**Decision:** UAT design-fidelity prompt ngoài screenshot path còn ghi: "Mở `${URL_TỪ_ENTRY}` đăng nhập `${ROLE}/${PASSWORD}`, navigate `${PATH}`, so với screenshot `${SCREENSHOT_PATH}`. Khu vực focus: `${REGION}` (vd 'sidebar', 'topbar balance chip', 'table header row')."
**Rationale:** Phase 7.14.3 UAT design prompt chỉ ghi `Screenshot: {path}` — user không biết "built output" ở URL nào.

---

## D-08: Design fidelity threshold per profile

**Category:** config
**Decision:** `design_fidelity.thresholds: { prototype: 0.7, production: 0.95, default: 0.9 }` trong `vg.config.md`. Phase scope khai báo profile (`design_fidelity.profile: prototype | production | default`). Validator đọc profile → apply threshold tương ứng.
**Rationale:** Cứng 90% cho mọi case là sai — prototype phase chấp nhận lệch nhiều (UX iteration), production phase khoá chặt.

---

## D-09: i18n lock — option B confirmed

**Category:** translation (closure of D-04)
**Decision:** Option B (lock mẫu strings, mở rộng strings ngoài mẫu) confirmed. Implementation qua AST text-node diff level-by-level — node text trong mẫu phải khớp; text node KHÔNG match mẫu được tự do (skip diff cho node không có twin trong mẫu).

---

## D-10: `/vg:uat-narrative-build` auto-fire

**Category:** workflow auto-wire
**Decision:** New step `4b_build_uat_narrative` trong `accept.md`, **auto-fire** giữa `4_build_uat_checklist` và `5_interactive_uat`. Output `${PHASE_DIR}/UAT-NARRATIVE.md` map mỗi D-XX/G-XX/design-ref → 4 field. Step 5 đọc UAT-NARRATIVE thay vì sinh prompt 1 dòng.
**Rationale:** Per memory `feedback_learn_automation` — không user gõ command. Tự fire trong luồng chính.

---

## D-11: 1 phase chung shape (split A/B)

**Category:** scope
**Decision:** Phase 15 (Phase A) ship HTML + PNG extractor + UAT narrative + filter rigor + review Haiku fix. Phase 16 (Phase B, future) ship Pencil/Penboard MCP integration + threshold tune. Shared infra: slug registry + 4-format extractor + design-ref enforcement.
**Rationale:** Battle-test Phase A trên FE phase tiếp theo (vd 7.14.4 nếu user roadmap cho phép) → data drive Phase B threshold + format priority.

---

## D-12: 5-part UI-MAP fix

**Category:** UI-MAP integration
**Decision:**
- **12a (executor inject):** build step 8c grep UI-MAP.md theo `owner-wave-id` của wave hiện tại → extract subtree → inject vào executor Sonnet prompt cùng design-ref structural+screenshot. Validator `verify-uimap-injection.py` chặn task không có UI-MAP block trong prompt.
- **12b (per-wave drift scoped):** sau wave commit chạy `generate-ui-map.mjs` lên wave-touched files → diff vs UI-MAP subtree cùng `owner-wave-id`. Drift > threshold scope → hard-block (đây là D-03).
- **12c (skip-silent → explicit):** scope phase phải khai báo `phase_has_ui_changes: true|false` trong CONTEXT.md decision frontmatter. True + UI-MAP thiếu/rỗng → blueprint reject. False → skip 2b6b_ui_map cleanly.
- **12d (wave history aggregator informational):** review reads all wave drift logs → emit `WAVE-DRIFT-HISTORY.md` table (wave-id, scope subtree, drift %, status pass/rollback/recover, timestamp). Display ở review report. Không phải gate.
- **12e (holistic phase drift hard gate):** sau review fix-loop, chạy `generate-ui-map.mjs` toàn dist build → diff vs UI-MAP toàn cây. Threshold per profile (D-08). Block nếu fail. Catch container drift + cross-subtree integration drift mà wave-scoped không thấy.

**Rationale:** Crossai audit `.vg/.tmp/crossai-build-audit/codex.out:14459` chỉ rõ "build never injects [UI-MAP] into executor context and only checks it after code has already been written." Fix toàn diện 5 chỗ wire chưa close.

---

## D-13: Auto-wire pipeline default (no manual gate flip)

**Category:** workflow ergonomics
**Decision:** Sau khi extractor + design-ref + per-wave diff sẵn sàng, wire mặc định:
- `/vg:scope` → đọc `.planning/design-source/` → auto-fire extractor → emit slug registry vào CONTEXT.md
- `/vg:blueprint` → R4 design-ref auto-required cho UI task (không cần config flag)
- `/vg:build` step 8c → auto-inject UI-MAP + design-ref structural+screenshot+interactions cho mỗi UI task
- `/vg:review` → auto-fire structural diff full phase + Haiku spawn (D-17)
- `/vg:test` → keep visual baseline 2% pixel làm gate cuối, nhưng đã có 3 layer trước nên ít fail
- `/vg:accept` → auto-fire UAT-NARRATIVE generation (D-10)

**Rationale:** "Không ai nhớ hết command để gõ đâu" — user feedback round 2.

---

## D-14: Subtree extraction Haiku sub-agent (per UI task)

**Category:** cost optimization
**Decision:** Mỗi UI task spawn Haiku sub-agent scoped extract subtree UI-MAP liên quan `<file-path>` task + tag `owner-task-id` + `owner-wave-id`. Subtree ~50 dòng so với full UI-MAP ~200-500 dòng — context gọn hơn 4-5 lần.
**Rationale:** User đề xuất "spawn Haiku để rẻ". Wave-build context đã chật.

---

## D-15: UI-MAP.md schema lock (5-field-per-node)

**Category:** validation
**Decision:** UI-MAP.md schema bắt buộc 5 field per node: (1) tag/component name, (2) key class names (vd Tailwind utility-bound), (3) children count + order, (4) props bound (data prop name), (5) text content nếu static. Validator `verify-uimap-schema.py` chặn blueprint nếu node thiếu field.
**Rationale:** Nếu planner viết lỏng `"Sidebar > NavItem × 6"`, executor build cấu trúc đúng nhưng class/props sai → drift check không catch. Spec phải lock detail level.

---

## D-16: Filter + Pagination Test Rigor Pack

**Category:** test rigor
**Decision:** Codegen extension trong `vg-codegen-interactive` skill. Per filter declared trong TEST-GOALS `interactive_controls.filter` + `interactive_controls.pagination`, sinh test 4 layer:

**Filter (group 1 — 14 case):**
- Coverage: cardinality enumeration + pairwise combinatorial + boundary values + empty state
- Stress: toggle storm (≥10 lần) + spam click debounce + in-flight cancellation
- State integrity: filter+sort+pagination interaction + URL sync + cross-route persistence
- Edge: XSS sanitize + empty result + 500 error handling

**Pagination (group 2 — 18 case, vì pagination = filter có URL sync):**
- Navigation correctness: next/prev/first/last/jump-to-page input/page size dropdown
- URL + state sync: paste full query → reload restored, filter change → reset page=1
- Envelope contract verify (B6 fix): assert `meta.total/page/limit/has_next` shape khớp TEST-GOALS declaration. Drift → BLOCK
- Display correctness: "Showing X-Y of Z total", empty/single page, last partial
- Stress: spam next, in-flight cancel
- Edge: out-of-range page=0/-1, cursor-based integrity

Validator `verify-filter-test-coverage.py` BLOCK ở `/vg:test` step `5d_codegen` nếu test count generated < ma trận expected.

**Rationale:** Phase 7.14.3 B5 (filter no-data) + B6 (pagination envelope drift). Pagination về bản chất là filter với URL sync — gộp 1 D nhưng 2 subgroup.

---

## D-17: Review wide-see Haiku spawn mandate + verify-spawn-fired BLOCK

**Category:** regression fix
**Decision:**
- Validator `verify-haiku-spawn-fired.py`: phase có UI profile (web-fullstack/web-frontend-only/mobile-*) → events.db phải có ≥1 `review.haiku_scanner_spawned` event trong run. Thiếu → BLOCK ở review run-complete.
- Telemetry: spawn step thêm `emit-event review.haiku_scanner_spawned` ngay trước Task tool call cho mỗi Haiku.
- Output `VIEW-MAP.md` (exhaustive elements/routes/modals/states) — separate với `RUNTIME-MAP.json` (goals scope).
- Bug detector phase 2c: đọc VIEW-MAP → flag console error, network 4xx/5xx, missing required button (compare design-ref), broken image, stuck loading state → emit `BUG-REPORT-OUTSIDE-GOALS.md`.
- Profile cli-tool/library bypass spawn: scope khai báo `spawn_mode: none` explicit; phase UI bypass = blueprint reject.

**Investigation tied to fix:** Tại sao /vg:review 7.14.3 abort 53s (skill ghi 30+ min) — log contract gate decision tree, phantom hook entry pattern. Fix root cause song song với verify-spawn validator.

**Evidence:** events.db `vg:review` phase=7.14.3 sequence:
- 18:05:38Z run.started
- 18:06:00-05Z validation events
- 18:06:05Z run.blocked + contract.marker_warn x2
- 18:06:31Z run.aborted

Total runtime 53s — không thể tới 2b-2 (skill nói 30+ min). 0 spawn event. → root cause: contract gate fire trước spawn step có chance mark.

---

## Cross-decision dependencies

```
D-01 (extractor) ─┬─ D-02 (design-ref hard) ─── D-12a (executor inject)
                 ├─ D-03 (per-wave drift) ─── D-12b
                 └─ D-15 (schema lock) ─── D-12 (5-part)
D-04/D-09 (i18n) ─── D-12e (holistic gate text-node diff)
D-05/D-06/D-07 (UAT 4-field) ─── D-10 (auto-fire)
D-08 (threshold per profile) ─── D-03/D-12e (used by both gates)
D-11 (phase split) ─── boundary Phase A vs Phase B
D-13 (auto-wire) ─── glue all gates into pipeline
D-14 (Haiku subtree) ─── D-12a optimization
D-16 (filter rigor) ─── independent, codegen extension
D-17 (Haiku spawn mandate) ─── independent, regression fix
```

---

## Acceptance per decision

Each D-XX must have:
- 1+ validator script (verify-*.py)
- 1+ telemetry event
- 1+ test fixture demonstrating BLOCK trigger
- 1+ test fixture demonstrating PASS path
- Documentation update trong skill body

Trace mỗi D → file changes ở blueprint phase.
