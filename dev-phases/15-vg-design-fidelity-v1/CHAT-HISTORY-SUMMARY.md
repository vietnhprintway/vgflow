# Chat History Summary — Phase 15 Discovery + Scope

Timeline of decisions across the scope discussion (2026-04-26 → 2026-04-27). Captures user reasoning, AI counter-proposals, and pushbacks that shaped the 17 decisions. Read this if you need *why* not just *what*.

---

## 1. Trigger — visual fidelity pain (Phase 7.14.3 evidence)

User attached 2 screenshots:
- **HTML mẫu** (`html/Internal Demand/Advertiser Dashboard/campaigns.html`) — sidebar 6 items với Vollx DSP branding cam, topbar có balance chip xanh `$3,084.22` + bell + avatar QD, title "Campaigns" lớn, button "+ New Campaign" cùng row, filter row đầy đủ (Today + 2 date pickers + UTC dropdown + search + All/With/No traffic toggle + Campaign group + status + Ad Format + Pricing Model + Archive + Edit Columns + Filter), bảng 18 cột với pricing model column có input field thực sự `0.003 CPC`, status sub-tag.
- **AI build output** (`apps/web/src/pages/advertiser/CampaignsPage.tsx` deployed local 5175) — sidebar có section labels "MAIN/ACCOUNT" (mẫu không có), title "Chiến dịch" + subtitle "Quản lý các chiến dịch quảng cáo" (mẫu EN không subtitle), breadcrumb "Advertiser > Campaigns" (mẫu không có), topbar balance trong outline button (mẫu badge xanh có icon), filter row thiếu Today/date range/Campaign group/Edit Columns, pricing model gộp tag "CPM $1.50" thay input.

User question: "Là do AI không nhìn ra, hay cách mà tôi enforce để AI nó hiểu phải làm như thế nào chưa hợp lý?"

AI verify trước reply: confirm phase 7.14.3 đã có decision "100% structurally match HTML campaigns.html" (P7.14.3.D-01..D-10), 18 cột exact list, visual gate ≤2% pixel ở /vg:test (TS-22). Vẫn lệch.

AI diagnosis end-to-end (prose, per memory `feedback_prose_explain_end_to_end`):
- Reference dạng prose `Read first: campaigns.html` cho AI tự diễn giải.
- AI có 3 thiên hướng đè lên reference: pattern bias (TanStack Table → sort arrows + edit pencil), best-practice bias (sidebar labels + breadcrumb + subtitle), locale bias (project có vi → tự dịch "Campaigns" dù mẫu EN).
- Visual gate 2% pixel ở /vg:test là phase-end gate — sau khi 16 task đã commit, fix tốn gấp 5 lần catch ngay tại wave.

AI fix conceptual: chuyển reference từ prose link sang structural artifact (DOM-AST JSON + screenshot pin per state + i18n-lock decision); per-task hard-required design-ref; per-wave incremental DOM-AST diff (count node, verify class, check text); pre-commit DOM-AST diff dist build vs structural.json.

User reply: "tôi muốn bạn thử scope để biết lỏng ở đâu... Đồng thời bạn cũng phải enforce cho khâu UAT ở accept, là AI phải diễn giải theo ngôn ngữ loài người, có câu chuyện, có mô tả rõ là phải vào trang nào/màn hình nào/hoặc không có màn hình thì phải làm thế nào... ví dụ UAT hỏi tôi bấm vào Thẻ này thấy gì chưa, trong khi không mô tả login ra làm sao, ở trang nào, role nào... TÔi muốn giải quyết triệt để khâu nếu đã có giao diện mẫu html/ảnh/pencil/penboard/png thì phải có luật bắt buộc chặt chẽ được phải làm tỷ lệ trên 90% giống"

→ Phase scope expanded từ visual fidelity sang dual-track: (a) visual fidelity, (b) UAT narrative.

---

## 2. Round 1 scope — 7 decision proposals

AI rà 4 chỗ lỏng (verify thật, không bịa):

- `.planning/design-normalized/` không tồn tại trong repo (blueprint.md line 374 đọc folder này nhưng nếu rỗng AI fall back đọc HTML thô).
- R4 design-ref MED warn-only.
- Visual gate phase-end only.
- Step `5_interactive_uat` accept.md sinh prompt 1 dòng "Decision D-04: Inline editable inputs — Was this implemented? [p/f/s]" — không có URL, role, account, navigation, precondition, expected.

AI proposed D-01..D-07:
- D-01 extractor 4-format
- D-02 design-ref hard-required (R4 → CRITICAL)
- D-03 per-wave structural diff (option not yet picked)
- D-04 i18n lock per phase
- D-05 UAT narrative 4-field
- D-06 UAT narrative source data
- D-07 design-ref UAT prompt format

5 questions cần user lock:
1. Source format coverage — HTML+PNG only hay full Pencil/Penboard?
2. Threshold cứng 90% hay slider per profile?
3. i18n strict — option A (mẫu EN → app EN tuyệt đối) hay option B (lock mẫu, AI dịch ngoài mẫu)?
4. UAT narrative — tự generate từ artifact đã có hay scope thêm step chuyên trách?
5. Phase shape — 1 phase chung hay split 2?

User answer:
1. Full coverage
2. Theo recommend của AI
3. Theo AI
4. Scope thêm + auto-wire vào luồng chính ("không ai nhớ hết command để gõ đâu")
5. Theo AI

User pushback nghiêm túc: "tôi nhớ đã có yêu cầu làm component hierarchy rồi mà nhỉ, tôi còn đưa cả 1 cái repo github cho bạn để bạn tham khảo cơ mà. sao giờ lại nói rằng phần đó AI toàn tự đoán?"

---

## 3. AI nhận sai về "AI tự đoán" — UI-MAP đã có

AI verify codebase:
- `.claude/scripts/generate-ui-map.mjs` — header file ghi rõ "PORT FROM: gist TongDucThanhNam" (chính là repo github user đưa).
- Blueprint step `2b6b_ui_map` (line 1735) — sinh `UI-MAP.md` cây component đích.
- Skill `vg-haiku-scanner` tồn tại.
- crossai audit `.vg/.tmp/crossai-build-audit/codex.out:14459` đã chỉ ra problem: *"Blueprint presents UI-MAP.md as the executor's target component tree, but build never injects it into executor context and only checks it after code has already been written."*

3 chỗ lỏng đã có nhưng chưa wire close:
- (1) Planner viết UI-MAP, executor không đọc — build step 8c không inject.
- (2) Drift check chạy sau khi code đã viết — không incremental per wave.
- (3) Skip silent khi FE_TASKS grep miss → phase 7.14.3 không có UI-MAP.md (`find` returns 0).

AI pivot scope round 2: thêm D-12 (5-part UI-MAP fix) thay vì build cơ chế mới.

---

## 4. Round 2 — D-08..D-13 lock

AI propose lock theo answer round 1:
- D-08 threshold per profile (prototype 0.7, production 0.95, default 0.9)
- D-09 i18n option B confirmed
- D-10 /vg:uat-narrative-build auto-fire
- D-11 1 phase chung shape (split A/B timeline)
- D-12 5-part UI-MAP fix (12a inject, 12b per-wave drift, 12c explicit decision, 12d aggregator, 12e holistic gate)
- D-13 auto-wire pipeline default

4 question:
1. Pencil + Penboard parser — viết tay (~150-200 LOC) hay deprioritize?
2. UI-MAP injection scope — full (~200-500 lines) hay subtree (~50 lines)?
3. Per-wave drift threshold — wave-level hard block (option A) hay warn-only + phase-end hard (option B)?
4. UAT-NARRATIVE language — VN hay EN?
5. Phase timeline split — 1 phase ship hết hay split A (HTML+PNG+UAT, 5-6 ngày) → B (Pencil/Penboard, 3-4 ngày)?

User answer:
1. Pencil + Penboard tương đồng, dùng MCP kết nối: `D:\Workspace\Messi\Code\PenBoard`
2. Subtree, thậm chí spawn Haiku sub-agent để rẻ
3. User chưa hiểu Q3 — AI giải thích lại
4. Theo `vg.config.md narration.locale` (đã có field này, line 702: `locale: "vi"`)
5. OK split

→ AI verify PenBoard MCP path: confirmed `dist/mcp-server.cjs` compiled, 24 tools (open_document, batch_get, snapshot_layout, entities, connections, design-skeleton, design-content, design-prompt, etc). Bỏ kế hoạch viết parser tay — tiết kiệm 3 ngày.

D-14 added: Subtree extraction Haiku sub-agent.

---

## 5. AI giải thích Q3 lại bằng ví dụ cụ thể

User chưa hiểu wave-level drift threshold. AI explain:
- Wave = batch task parallel trong /vg:build (Wave 1 task 1-5, Wave 2 task 6-10).
- Drift = chênh giữa cây component as-built sau wave so cây UI-MAP.md as-planned.
- Vấn đề: sau Wave 1 chỉ có sidebar+topbar, table chưa build → diff toàn UI-MAP báo drift 50% → hard-block sẽ false-fail.

3 option:
- A. Hard-block toàn cây mỗi wave — too many false alarm.
- B. Warn-only wave, hard-block phase-end — drift tích lũy.
- C. Scoped wave drift (option mới AI nghĩ ra khi viết) — wave declare scope subtree it touches; diff CHỈ trong scope đó. Cost: planner tag `owner-wave-id` mỗi UI-MAP node.

AI nghiêng C. User reply: "c, nhưng ở review cũng nên có tổng hợp từ từng wave để review đánh giá chứ. bạn phản biện đi"

---

## 6. AI phản biện user proposal "tổng hợp từng wave ở review"

AI confirm 80% đúng — wave history giúp review hiểu trajectory. Nhưng risk khi gộp: review aggregate "all wave pass" rồi rubber-stamp → bỏ qua holistic check.

Counter-example: Wave 1 build Sidebar OK (subtree đúng), Wave 2 build Topbar OK. Nhưng layout container parent của cả hai có thể `grid-cols-12 → flex` drift mà không wave nào declare touch container → wave-aggregate không catch.

AI counter-proposal: tách 2 panel rõ vai trò:
- **D-12d wave drift history aggregator** (informational only) — table wave-id, scope subtree, drift %, status pass/rollback/recover, timestamp. Display review report. KHÔNG phải gate.
- **D-12e holistic phase drift gate** (hard) — chạy lại extractor toàn dist build vs UI-MAP toàn cây, không aggregate từ wave. Threshold per profile (D-08). BLOCK.

User confirm: "có cả 2 vẫn tốt, dù sao thì quan trọng nhất vẫn là kỷ luật, AI bắt buộc làm việc phải theo trình tự chứ AI hay lười, đọc lướt, rồi không có validator chặt là sẽ lại bỏ qua"

→ AI save memory `feedback_ai_discipline_validator`: rule không có hard validator chặt sẽ bỏ qua. Mọi spec phải bind hard-block, không warn-only.

---

## 7. UI-MAP schema gap — D-15 added

User question sắc: "nhưng nếu ở cuối wave mới gen cây thì làm sao lúc build nó biết cây thế nào là đúng nhỉ, blueprint đảm nhiệm vai trò này à?"

AI tách rõ 2 thứ dễ nhầm:
- **UI-MAP.md** = bản vẽ cây ĐÍCH (as-planned tree), sinh ở blueprint step 2b6b BỞI PLANNER OPUS, TRƯỚC khi build start.
- **generate-ui-map.mjs** = TOOL scan AST code → emit cây as-built. Chỉ chạy sau khi có code (post-wave hoặc post-phase).

Luồng đầy đủ:
1. Blueprint planner viết UI-MAP.md cây đích, mỗi node tag owner-wave-id.
2. Build step 8c grep UI-MAP theo owner-wave-id → extract subtree → inject executor prompt.
3. Wave end scan code → diff vs UI-MAP subtree.
4. Phase-end review scan toàn dist → diff vs UI-MAP toàn cây.

Caveat: UI-MAP phải đủ chi tiết. Nếu planner viết lỏng `Sidebar > NavItem × 6`, executor build cấu trúc đúng nhưng class/props sai → diff không catch.

→ D-15 **UI-MAP.md schema lock** — bắt buộc 5 field per node (tag, class, children count+order, props bound, text static). Validator `verify-uimap-schema.py` chặn blueprint nếu node thiếu field.

User: "ok"

---

## 8. Filter + Pagination — D-16 added

User: "thêm phần bắt chặt test filter nữa nhé, chọn hết tất cả các filter value, chọn đi chọn lại, chọn tốc độ nhanh, thêm các behavior khác mà bạn biết để mục đích test phần filter nó phạt đạt kết quả cao, hiển thị được dữ liệu. không lỗi"

→ D-16 Filter Test Rigor Pack — 4 layer × 14 case (initial). Codegen extension `vg-codegen-interactive` skill. Validator `verify-filter-test-coverage.py` BLOCK.

User follow-up: "đã có phần thắt chặt paging chưa, tôi nhớ là có yêu cầu rồi đó, bản chất thì paging nó cũng là 1 phần của filter, cũng có truyền url lên querystring, và cách hiển thị như tôi đã mô tả dành cho web app đó"

AI verify: D-16 chỉ touch pagination ở mục "filter+sort+pagination interaction" (state integrity #8) — không có pagination test pack riêng. Phase 7.14.3 bug B6 (envelope drift `meta.total` undefined) chính xác cần test rigor.

→ D-16 extend thành 2 group: Filter (14 case) + Pagination (18 case). Pagination subgroup gồm navigation correctness + URL/state sync + envelope contract verify (B6 fix) + display correctness + stress + edge.

---

## 9. Review Haiku spawn regression — D-17 added

User: "ở phần review mấy hôm nay tôi thấy có vẻ nó không spawn sub agent haiku để test nữa hay sao ấy, nó là phần wide see, nhìn rộng, dùng haiku để vẽ ra bản đồ những gì mà playwright, hay mastreo (của mobile) nhìn thấy. từ đó nó dò được hết theo goals, và các bug error nằm ngoài vùng cover của goals nữa"

AI verify:
- Skill `/vg:review` step 2b-2 line 2183 vẫn ghi "**You MUST spawn Haiku agents in step 2b-2**".
- Skill `vg-haiku-scanner/SKILL.md` vẫn tồn tại.
- BUT events.db run /vg:review 7.14.3 ở 18:05:38Z → run.blocked + run.aborted ở 18:06:31Z. Tổng 53s — không thể tới 2b-2 (skill ghi 30+ min).
- Root cause khả năng: contract gate `contract.marker_warn` chặn run-complete vì phase markers chưa emit, hoặc phantom hook (đã hành 4 lần phiên trước).

→ D-17 added — verify-haiku-spawn-fired BLOCK + investigation tied to fix.

---

## 10. /vg:scope skill invocation — Phase 15 added to ROADMAP

User gõ `/vg:scope vg-design-fidelity-v1` → skill BLOCK ở step 0 (SPECS.md missing). AI explain sequence: add-phase → specs → scope. User pick path A (Phase 15 RTB ROADMAP full pipeline). 

AI run /vg:add-phase: register run-start, emit add_phase.started, append Phase 15 block vào ROADMAP.md (32 dòng), tạo `.vg/phases/15-vg-design-fidelity-v1/` empty dir, commit `chore(vg-roadmap): add Phase 15 ...` (commit 249c7dfe), emit add_phase.completed, run-complete PASS.

Note: 4 phantom run-start incidents trong session — entry-hook regex bắt nhầm `/vg:` literal từ message content (SPEC documents, prose discussions). Workaround: run-abort cleanly mỗi lần.

---

## 11. Sync to vgflow-repo — current step

User: "tôi nghĩ bạn có thể sync cả vg của project này vào vg repo được rồi. sau đó bê cái phase chúng ta đang làm sang đó, tôi muốn bật ở 1 cửa sổ khác để fix repo sau đó sync ngược sang project này, repo sẽ coi project rtb này như là dogfood để kiểm nghiệm. bạn cũng nên lưu context vào để sang thư mục repo, tôi có thể yêu cầu AI đọc lại mà hiểu được workflow vg đang làm những gì rồi"

→ Sync RTB `.claude/` → vgflow-repo via `DEV_ROOT=/d/Workspace/Messi/Code/RTB ./sync.sh` (clean, 0 changes). Tạo `vgflow-repo/dev-phases/15-vg-design-fidelity-v1/` với 4 context files (HANDOFF + DECISIONS + ROADMAP-ENTRY + CHAT-HISTORY-SUMMARY + README). Working from vgflow-repo cửa sổ khác, AI đọc HANDOFF first.

---

## Pending — chưa làm

- [ ] `/vg:specs 15` — generate SPECS.md từ 17 decisions
- [ ] `/vg:scope 15` — 5-round structured discussion → emit CONTEXT.md ở RTB
- [ ] `/vg:blueprint 15` — task breakdown
- [ ] `/vg:build 15` — execute
- [ ] Investigation D-17: tại sao /vg:review 7.14.3 abort 53s

## Memory rules saved during this session

- `feedback_ai_discipline_validator.md` — rule không có hard validator chặt sẽ bỏ qua. Mọi spec phải bind hard-block, không warn-only.

## Files written this session (RTB project)

- `.vg/ROADMAP.md` (line 759-790, +32 dòng Phase 15 block) — commit 249c7dfe
- `.vg/phases/15-vg-design-fidelity-v1/` (empty dir, populate qua /vg:specs)

## Files written this session (vgflow-repo)

- `dev-phases/15-vg-design-fidelity-v1/HANDOFF.md`
- `dev-phases/15-vg-design-fidelity-v1/DECISIONS.md`
- `dev-phases/15-vg-design-fidelity-v1/ROADMAP-ENTRY.md`
- `dev-phases/15-vg-design-fidelity-v1/CHAT-HISTORY-SUMMARY.md`
- `dev-phases/15-vg-design-fidelity-v1/README.md`
