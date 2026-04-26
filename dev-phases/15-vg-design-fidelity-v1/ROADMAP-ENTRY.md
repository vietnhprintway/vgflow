# RTB ROADMAP entry — Phase 15

> **Source:** `RTB/.vg/ROADMAP.md` line 759-790, commit `249c7dfe`.
> Copy here so AI session in `vgflow-repo/` doesn't need to cross repo boundary.
> Authoritative version stays in RTB; sync direction RTB → vgflow-repo via copy-paste (no automated sync).

---

### Phase 15: VG Design Fidelity + UAT Narrative + Filter Test Rigor — Phase A

**Goal:** Tighten visual fidelity gate (HTML/PNG mẫu → AST diff ≥90%), wire UAT narrative auto-fire, enforce filter+pagination test rigor, fix review wide-see Haiku spawn regression.

**Requirements:** None — VG workflow infrastructure phase (not product feature). Triggers: pain points trong Phase 7.14.3 (visual drift evidence ảnh sản phẩm vs HTML mẫu + UAT prompt thiếu login URL/role/navigation + B5 filter no-data bug + B6 pagination envelope drift + review aborted before Haiku spawn 53s vs 30min expected).

**Depends on:** None hard. Soft dep: Phase 7.14.3 evidence (bugs B1-B6 reference) + PenBoard MCP server tại `D:\Workspace\Messi\Code\PenBoard` (Phase B v2 dependency).

**Category:** vg-workflow-infra (meta-phase — improves harness for all subsequent product phases).

**Plans:** 0 plans (to be created in `/vg:blueprint 15`)

**Scope summary** (locked qua /vg:scope draft chat, 17 decisions awaiting CONTEXT.md emission):

- **D-01..D-04:** Design source-of-truth extractor (HTML cheerio + PNG OCR for Phase A; Pencil/Penboard via PenBoard MCP for Phase B), design-ref hard-required (R4 MED → CRITICAL), per-wave structural diff scoped option C, i18n option B.
- **D-05..D-07:** UAT narrative 4-field (entry URL+role+account, navigation step-by-step, precondition data state, expected behavior), source from port-role mapping + accounts seed + TEST-GOALS interactive_controls, design-ref UAT prompt with URL+role+region.
- **D-08..D-09:** Design fidelity threshold per profile (prototype 0.7, production 0.95, default 0.9), i18n lock option B confirmed (lock mẫu strings, AI dịch những gì không có trong mẫu).
- **D-10..D-11:** `/vg:uat-narrative-build` auto-fire trong accept step `4b_build_uat_narrative` (no manual command), 1 phase chung shape.
- **D-12 (5-part UI-MAP fix):** 12a inject UI-MAP subtree vào executor prompt build step 8c + verify-uimap-injection.py BLOCK; 12b per-wave drift scoped subtree (option C); 12c explicit `phase_has_ui_changes: true|false` decision thay skip-silent; 12d wave history aggregator → WAVE-DRIFT-HISTORY.md (informational only); 12e holistic phase drift hard gate ở review fix-loop cuối.
- **D-13:** Auto-wire pipeline mặc định (scope auto-extract design assets, blueprint R4 hard-required, build inject, review aggregate + holistic, test visual baseline, accept narrative auto-fire — không user gõ).
- **D-14:** Subtree extraction Haiku sub-agent per UI task (rẻ, scoped).
- **D-15:** UI-MAP.md schema lock (5 field/node: tag, key class names, children count+order, props-bound, text-static); validator `verify-uimap-schema.py` chặn blueprint nếu node thiếu field.
- **D-16:** Filter + Pagination Test Rigor Pack — 4 layer (coverage/stress/state/edge) × ~18 case per filter type, codegen extension `vg-codegen-interactive` skill, validator `verify-filter-test-coverage.py` BLOCK.
- **D-17:** Review wide-see Haiku spawn mandate — validator `verify-haiku-spawn-fired.py` ở review run-complete BLOCK nếu phase UI profile + 0 spawn event; investigate why phase 7.14.3 review aborted 53s before reaching step 2b-2; output VIEW-MAP.md exhaustive (separate from RUNTIME-MAP goals scope) + BUG-REPORT-OUTSIDE-GOALS.md.

**Phase B (future, post-battle-test of Phase A):** Pencil/Penboard MCP integration via `bun run mcp:dev` (PenBoard exposes 24 tools: open_document, batch_get readDepth, snapshot_layout, design-skeleton, entities, connections, project-context) + threshold tune from real data + VG config wire `mcp.servers.penboard.command`.

**Estimated timeline:** 7-8 days dev (Phase A); Phase B 3-4 days.

**Success criteria:**

- Visual fidelity ≥90% AST node match cho UI task có HTML/PNG mẫu (validated qua incremental per-wave + holistic phase-end gate)
- 0 silent skip cho UI task thiếu `<design-ref>` (R4 hard-block enforced)
- UAT prompt 100% có 4 field (entry URL+role+account, navigation, precondition, expected) — không còn case user "mất phương hướng phải hỏi lại"
- Filter + Pagination test coverage ≥ ma trận expected (cardinality + pairwise + 7 stress/state/edge fixed) cho mọi `interactive_controls.filter` + `interactive_controls.pagination`
- Review phase UI profile spawn ≥1 Haiku scanner (0% silent skip qua early abort)
- Phase 7.14.3 bugs B1-B6 root cause prevented qua workflow gates (regression test trên next FE phase)
