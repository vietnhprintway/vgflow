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

4. **Review wide-see Haiku spawn regression** — Skill body line 2183 ghi rõ "**You MUST spawn Haiku agents in step 2b-2**" nhưng recent run /vg:review 7.14.3 abort sau 53 giây (skill ghi "30+ min" cho 5-20 scanner) — chưa tới step 2b-2. Effect: VIEW-MAP exhaustive không được tạo, bug ngoài goals scope không catch. **Fix:** validator `verify-haiku-spawn-fired.py` ở review run-complete BLOCK nếu phase UI profile + 0 spawn event. Telemetry `review.haiku_scanner_spawned` emit ngay trước Task tool call. Output `VIEW-MAP.md` exhaustive + `BUG-REPORT-OUTSIDE-GOALS.md`. Investigation: tại sao 7.14.3 review abort 53s — có thể contract gate fire quá sớm, hoặc phantom hook entry-pattern, hoặc profile detection sai.

---

## How to start work in this session

1. Read this HANDOFF.md (done).
2. Read `DECISIONS.md` — full 18 decisions với rationale + acceptance criteria per decision.
3. Read `CHAT-HISTORY-SUMMARY.md` — timeline of decisions với why-because reasoning.
4. Read `ROADMAP-ENTRY.md` — block ROADMAP RTB cho phase này.
5. Decide entry point:
   - **Path A — write SPECS first** (recommended): từ DECISIONS.md tổng hợp SPECS.md draft → user review → emit `.vg/phases/15-vg-design-fidelity-v1/SPECS.md` ở RTB project (sync sang vgflow-repo qua sync.sh).
   - **Path B — start blueprint draft**: nếu user pick build-first mode, generate task breakdown 17 decisions → 30-40 task batches.
   - **Path C — investigate review regression first** (D-17 unblock): tại sao /vg:review abort 53s — có thể là blocker cho test infra, fix trước.

---

## Files trong working folder này

- `HANDOFF.md` — bạn đang đọc, overview
- `DECISIONS.md` — full 17 decisions detail (D-01..D-17)
- `ROADMAP-ENTRY.md` — block từ RTB `.vg/ROADMAP.md` line ~759-810
- `CHAT-HISTORY-SUMMARY.md` — timeline + reasoning
- `README.md` — dogfood pattern explained (vgflow-repo ↔ RTB)

---

## Workflow đồng bộ vgflow-repo ↔ RTB project

**Source of truth:**
- `.claude/commands/vg/*.md` — skill bodies, edit ở RTB
- `.claude/scripts/validators/*.py` — validators, edit ở RTB
- `.claude/scripts/vg-orchestrator/` — orchestrator code, edit ở RTB

**Mirror (read-only output):**
- `vgflow-repo/commands/vg/*.md`, `skills/`, `scripts/` — bản distribute
- `~/.codex/skills/` — global Codex CLI deploy

**Sync command** (run từ vgflow-repo dir):
```bash
DEV_ROOT="/d/Workspace/Messi/Code/RTB" ./sync.sh
```
Hoặc dry-run check delta: `./sync.sh --check`

**Inverse direction (vgflow-repo → RTB):** chưa có script tự động. Để bring vgflow-repo changes về RTB, edit `.claude/commands/vg/<file>.md` trực tiếp (manual diff hoặc copy-paste).

**Gotcha:** `.vg/phases/` chỉ tồn tại ở RTB (project state). vgflow-repo có `dev-phases/` riêng cho meta phase work — không sync giữa hai.

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
