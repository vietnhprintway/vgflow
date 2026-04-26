# Phase 15 — VG Design Fidelity + UAT Narrative + Filter Test Rigor — HANDOFF

> **Read this first if you are an AI session opened in `vgflow-repo/`.**
> This phase is being developed concurrently from two sides:
> - **vgflow-repo (you are here)** — fix workflow harness code, ship validators + skills + scripts
> - **RTB project** (`/d/Workspace/Messi/Code/RTB/`) — dogfood test, sync ngược về để verify gate behavior

**Phase ID:** 15-vg-design-fidelity-v1
**Status:** Phase scoped in vgflow-repo dev-phases only (RTB ROADMAP entry reverted in RTB commit `a6036f1f` — Phase 15 is VG workflow infra, not RTB product feature; tracked here exclusively for separation of concerns). SPECS not yet written. **3 open questions đã chốt 2026-04-27** (Pencil/Penboard ship Phase A FULL, threshold default = 0.85, UAT strings reuse `narration-strings.yaml` strict).
**Locked decisions:** 18 (D-01..D-18)
**Estimated dev time:** 9-11 ngày Phase A (revised từ 7-8 ngày — thêm wire 2 MCP); Phase B 2-3 ngày post-battle-test threshold tune

---

## TL;DR — what this phase does

Tighten 4 weak spots trong VG harness mà Phase 7.14.3 RTB phơi bày:

1. **Visual fidelity gate** — khi project có HTML/PNG/Pencil/Penboard mẫu, AI build ra UI lệch nhiều (ảnh thật vs mẫu khác sidebar labels, topbar balance, table format, font, layout spacing, translation tự ý "Campaigns"→"Chiến dịch"). Root cause: reference dạng prose link "Read first: campaigns.html" cho AI tự diễn giải; UI-MAP.md được sinh nhưng không inject vào executor prompt; drift check chỉ chạy phase-end ≤2% pixel khi code đã commit. **Fix:** structural extractor (HTML cheerio + PNG OCR + Pencil MCP + Penboard MCP — **2 MCP riêng biệt, tool set khác nhau**) → `.planning/design-normalized/refs/{slug}.structural.json` + screenshots + interactions.md; design-ref hard-required (R4 MED → CRITICAL); per-wave structural diff scoped subtree (option C — chỉ check trong scope wave declare touch để tránh false alarm cross-subtree); holistic phase-end gate riêng để catch container drift; UI-MAP schema lock 5-field-per-node.

2. **UAT narrative** — Step `5_interactive_uat` sinh prompt 1 dòng "Decision D-04: Inline editable inputs — Was this implemented? [p/f/s]" — không có URL, role, login account, navigation path, precondition data state, expected behavior. Dev/tester mất phương hướng phải hỏi lại. **Fix:** new step `4b_build_uat_narrative` auto-fire trong accept (no manual command), generate `UAT-NARRATIVE.md` map mỗi D-XX/G-XX/design-ref → 4 field (entry URL+role+account, navigation, precondition, expected). Source: port-role mapping từ config.environments.local + accounts.json seed + TEST-GOALS interactive_controls.entry_path. Ngôn ngữ theo `narration.locale` (vi/en).

3. **Filter + Pagination test rigor** — Phase 7.14.3 bug B5 (filter no-data) + B6 (pagination envelope drift `meta.total` undefined → totalPages=0). **Fix:** Filter Test Rigor Pack 4 layer × 18 case per filter type — coverage (cardinality enumeration + pairwise combinatorial + boundary + empty), stress (toggle storm + spam click debounce + in-flight cancellation), state integrity (filter+sort+pagination + URL sync + cross-route persistence), edge (XSS sanitize + empty result + 500 error). Pagination subgroup (vì pagination là filter có URL sync): navigation correctness + URL/state sync + envelope contract verify (fix B6) + display correctness + stress + edge. Validator `verify-filter-test-coverage.py` BLOCK nếu test count < ma trận expected. Codegen extension trong `vg-codegen-interactive` skill.

4. **Review wide-see Haiku spawn — phantom-run diagnosis (corrected 2026-04-27)** — Initial hypothesis (53s abort = scanner spawn failure) **was wrong**. `INVESTIGATION-D17.md` traces the abort to a *phantom run started by hook during /vg:learn invocation* — args:"" + 0 step.marked + manual abort within 60s. The v2.8.6 hotfix (commit `411a278`, 2026-04-26 22:22) landed 4 hours AFTER the phantom event and already addressed the entry-pattern hook bug; no scanner regression existed. **Real fix shipped:** (a) `verify-haiku-spawn-fired.py` validator (T3.11) is *phantom-aware* — ignores runs matching the D-17 signature so future hook noise can't false-positive the gate; (b) `review.haiku_scanner_spawned` telemetry emit moved to BEFORE the Agent() call (Wave 9 commit `4edbaa2`) so spawn audit survives even if the Agent crashes mid-spawn. No source-code regression to revert; what was missing was *evidence-of-firing*, which the new emit + validator pair now provide.

---

## How to start work in this session

1. Read this HANDOFF.md (done).
2. Read `DECISIONS.md` — full 18 decisions với rationale + acceptance criteria per decision.
3. Read `CHAT-HISTORY-SUMMARY.md` — timeline of decisions với why-because reasoning.
4. Read `ROADMAP-ENTRY.md` — block ROADMAP RTB cho phase này.
5. Decide entry point:
   - **Path A — write SPECS first** (recommended): từ DECISIONS.md tổng hợp `SPECS.md` draft trong cùng folder này (`dev-phases/15-vg-design-fidelity-v1/SPECS.md`) → user review → lock. **Implementation code** (skills, validators, scripts) edit ở RTB `.claude/...` per source-of-truth pattern → sync về vgflow-repo distribute mirror qua `./sync.sh`. SPECS planning doc KHÔNG sync (vgflow-repo dev-phases/ là meta workspace, không mirror).
   - **Path B — start blueprint draft**: nếu user pick build-first mode, generate task breakdown 18 decisions → 30-40 task batches.
   - **Path C — investigate review regression first** (D-17 unblock): tại sao /vg:review abort 53s — có thể là blocker cho test infra, fix trước.

---

## Files trong working folder này

- `HANDOFF.md` — bạn đang đọc, overview
- `DECISIONS.md` — full 18 decisions detail (D-01..D-18)
- `ROADMAP-ENTRY.md` — **historical reference** (block draft cho RTB `.vg/ROADMAP.md`, đã revert ở RTB commit `a6036f1f` — Phase 15 tách khỏi RTB roadmap, giờ là vgflow-repo infra phase exclusively). Giữ file để trace decision lịch sử.
- `CHAT-HISTORY-SUMMARY.md` — timeline + reasoning
- `README.md` — dogfood pattern explained (vgflow-repo ↔ RTB)
- `SPECS.md` — (sẽ tạo Path A) executable specification per-decision implementation contract

---

## Workflow đồng bộ vgflow-repo (source) ↔ RTB project (test target)

**Corrected 2026-04-27:** Phase 15 = VG workflow infra → **edit ở vgflow-repo top-level**. RTB là project tham chiếu (dogfood test downstream consumer), không phải source. Sync.sh comment cũ "edit tại .claude/commands/vg/" đã misleading — vgflow-repo không có `.claude/` folder.

**Source of truth (edit ở đây):**
- `vgflow-repo/commands/vg/*.md` — skill bodies
- `vgflow-repo/scripts/*.py` `*.mjs` `*.js` — orchestrator + extractor + helper scripts
- `vgflow-repo/scripts/validators/*.py` — validators
- `vgflow-repo/schemas/*.json` — JSON Schema draft-07 contracts
- `vgflow-repo/commands/vg/_shared/narration-strings.yaml` — i18n strings
- `vgflow-repo/skills/` — skill bodies (dist tree)

**Distribute targets (sync.sh writes):**
- `RTB/.claude/commands/vg/`, `.claude/scripts/`, `.claude/schemas/` — installation copy
- `~/.codex/skills/` — global Codex CLI deploy

**Sync command** (run từ vgflow-repo dir):
```bash
DEV_ROOT="/d/Workspace/Messi/Code/RTB" ./sync.sh           # full sync source → mirror → installations
./sync.sh --check                                           # dry-run delta
./sync.sh --no-source                                       # skip source→mirror (rare; only if editing mirror directly)
./sync.sh --no-global                                       # skip ~/.codex/ deploy
```

**Gotcha:**
- `.vg/phases/` chỉ tồn tại ở RTB (project state, ephemeral). vgflow-repo có `dev-phases/` riêng cho meta phase work — không sync giữa hai.
- After Phase 15 wave commit ở vgflow-repo, run `./sync.sh` để dogfood test ở RTB.

---

## Constraints + non-goals

**Constraints:**
- VG là workflow global, **không hardcode RTB-specific paths** trong skill body (CLAUDE.md feedback rule). Reference paths qua `vg.config.md`.
- File prompt cho AI (commands, skills, workflows) — viết English; chat reply Vietnamese (memory rule `feedback_skill_command_language`).
- Pronoun "tôi - bạn", không "em" tự xưng (memory rule `feedback_pronoun_toi_ban`).
- Mọi rule có gate validator được — phải BLOCK, không warn-only (memory rule `feedback_ai_discipline_validator`).

**Phase A scope (FULL — chốt 2026-04-27):**
- HTML extractor (cheerio AST)
- PNG extractor (OCR + region detection — opencv-wasm + tesseract.js)
- **Pencil MCP extractor** (`mcp__pencil__*` — 13 tools: `get_editor_state`, `open_document`, `batch_get`, `batch_design`, `get_screenshot`, `export_nodes`, `get_guidelines`, `snapshot_layout` v.v.). File `.pen` ENCRYPTED — **bắt buộc qua MCP, Read/Grep fail**. Đã connect OK trong session này (`/mcp` confirmed).
- **Penboard MCP extractor** (`mcp__penboard__*` — ~43 tools: `read_doc`/`write_doc`, `read_flow`/`write_flow`, `list_flows`, `manage_entities`, `manage_connections`, `manage_data_binding`, `design_skeleton`/`design_content`/`design_refine`, `generate_preview`, `import_svg`, `export_workflow`, `set_themes` v.v.). Source: `D:\Workspace\Messi\Code\PenBoard\dist\mcp-server.cjs`.
- Extractor router: detect file ext → route MCP tương ứng (`.pen` → Pencil; `.penboard`/`.flow`/project có `penboard.config` → Penboard).
- 2 MCP server **wire RIÊNG BIỆT** trong `vg.config.md`: `mcp.servers.pencil.*` + `mcp.servers.penboard.*`. Không gộp 1 entry.
- Toàn bộ feature D-02..D-18 ship Phase A.

**Non-goals (Phase B — defer mỏng):**
- Threshold tune from production data (cần ≥2 phase battle-test data trước khi tune).
- Edge case fix MCP integration (deadlock, timeout, MCP server down handling).
- Cross-format diff (phase có cả `.pen` và `.penboard` — merge tree thế nào).

---

## Open questions — RESOLVED 2026-04-27

✅ **Q1 (Pencil/Penboard ship Phase A?)** → CÓ, ship FULL trong Phase A, không hidden flag, không defer. Lý do: Pencil MCP đã connect OK + Penboard MCP đã compile, tách 2 phase tăng integration risk + vi phạm rule "không warn-only" (D-11 updated).

✅ **Q2 (Threshold default 0.9 quá conservative?)** → Hạ default xuống **0.85** (3 profile: prototype 0.7, default 0.85, production 0.95). Lý do: 0.9 quá gần production 0.95 (gap 5%, dày đặc). 0.85 equidistant từ prototype/production (15% gap mỗi bên), middle phase ít false-fail (D-08 updated).

✅ **Q3 (UAT strings hardcode trong template?)** → KHÔNG hardcode, phải reuse `narration-strings.yaml` strict. Validator BLOCK literal string ngoài interpolation `{{key}}`. Lý do: UAT là gate quality cuối cùng, cần discipline cao nhất (D-18 mới, lock).

**No open questions remaining cho Phase A scope.**

---

## Acceptance gate (Phase A done = ship)

- 6 success criteria từ ROADMAP entry:
  1. Visual fidelity ≥90% AST node match (per-wave + holistic)
  2. 0 silent skip cho UI task thiếu `<design-ref>`
  3. UAT prompt 100% có 4 field
  4. Filter + Pagination test coverage ≥ ma trận expected
  5. Review phase UI profile spawn ≥1 Haiku scanner
  6. Phase 7.14.3 bugs B1-B6 root cause prevented qua workflow gates (regression test trên next FE phase)
