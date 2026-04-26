# Phase 15 — VG Design Fidelity + UAT Narrative + Filter Test Rigor — HANDOFF

> **Read this first if you are an AI session opened in `vgflow-repo/`.**
> This phase is being developed concurrently from two sides:
> - **vgflow-repo (you are here)** — fix workflow harness code, ship validators + skills + scripts
> - **RTB project** (`/d/Workspace/Messi/Code/RTB/`) — dogfood test, sync ngược về để verify gate behavior

**Phase ID:** 15-vg-design-fidelity-v1
**Status:** Phase added to RTB ROADMAP (commit `249c7dfe`), SPECS not yet written
**Locked decisions:** 17 (D-01..D-17)
**Estimated dev time:** 7-8 ngày (Phase A); Phase B 3-4 ngày (post-battle-test)

---

## TL;DR — what this phase does

Tighten 4 weak spots trong VG harness mà Phase 7.14.3 RTB phơi bày:

1. **Visual fidelity gate** — khi project có HTML/PNG/Pencil/Penboard mẫu, AI build ra UI lệch nhiều (ảnh thật vs mẫu khác sidebar labels, topbar balance, table format, font, layout spacing, translation tự ý "Campaigns"→"Chiến dịch"). Root cause: reference dạng prose link "Read first: campaigns.html" cho AI tự diễn giải; UI-MAP.md được sinh nhưng không inject vào executor prompt; drift check chỉ chạy phase-end ≤2% pixel khi code đã commit. **Fix:** structural extractor (HTML cheerio + PNG OCR + Pencil/Penboard MCP) → `.planning/design-normalized/refs/{slug}.structural.json` + screenshots + interactions.md; design-ref hard-required (R4 MED → CRITICAL); per-wave structural diff scoped subtree (option C — chỉ check trong scope wave declare touch để tránh false alarm cross-subtree); holistic phase-end gate riêng để catch container drift; UI-MAP schema lock 5-field-per-node.

2. **UAT narrative** — Step `5_interactive_uat` sinh prompt 1 dòng "Decision D-04: Inline editable inputs — Was this implemented? [p/f/s]" — không có URL, role, login account, navigation path, precondition data state, expected behavior. Dev/tester mất phương hướng phải hỏi lại. **Fix:** new step `4b_build_uat_narrative` auto-fire trong accept (no manual command), generate `UAT-NARRATIVE.md` map mỗi D-XX/G-XX/design-ref → 4 field (entry URL+role+account, navigation, precondition, expected). Source: port-role mapping từ config.environments.local + accounts.json seed + TEST-GOALS interactive_controls.entry_path. Ngôn ngữ theo `narration.locale` (vi/en).

3. **Filter + Pagination test rigor** — Phase 7.14.3 bug B5 (filter no-data) + B6 (pagination envelope drift `meta.total` undefined → totalPages=0). **Fix:** Filter Test Rigor Pack 4 layer × 18 case per filter type — coverage (cardinality enumeration + pairwise combinatorial + boundary + empty), stress (toggle storm + spam click debounce + in-flight cancellation), state integrity (filter+sort+pagination + URL sync + cross-route persistence), edge (XSS sanitize + empty result + 500 error). Pagination subgroup (vì pagination là filter có URL sync): navigation correctness + URL/state sync + envelope contract verify (fix B6) + display correctness + stress + edge. Validator `verify-filter-test-coverage.py` BLOCK nếu test count < ma trận expected. Codegen extension trong `vg-codegen-interactive` skill.

4. **Review wide-see Haiku spawn regression** — Skill body line 2183 ghi rõ "**You MUST spawn Haiku agents in step 2b-2**" nhưng recent run /vg:review 7.14.3 abort sau 53 giây (skill ghi "30+ min" cho 5-20 scanner) — chưa tới step 2b-2. Effect: VIEW-MAP exhaustive không được tạo, bug ngoài goals scope không catch. **Fix:** validator `verify-haiku-spawn-fired.py` ở review run-complete BLOCK nếu phase UI profile + 0 spawn event. Telemetry `review.haiku_scanner_spawned` emit ngay trước Task tool call. Output `VIEW-MAP.md` exhaustive + `BUG-REPORT-OUTSIDE-GOALS.md`. Investigation: tại sao 7.14.3 review abort 53s — có thể contract gate fire quá sớm, hoặc phantom hook entry-pattern, hoặc profile detection sai.

---

## How to start work in this session

1. Read this HANDOFF.md (done).
2. Read `DECISIONS.md` — full 17 decisions với rationale + acceptance criteria per decision.
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

**Non-goals (Phase A — push to Phase B):**
- Pencil/Penboard MCP integration: `D:\Workspace\Messi\Code\PenBoard` (dist/mcp-server.cjs compiled, 24 tools available). Phase B v2 sẽ wire `mcp.servers.penboard.command` vào vg.config.md.
- Threshold tune from production data (Phase B sau khi có battle-test data từ Phase A).

---

## Open questions (chưa lock — surface trong /vg:scope round 1)

- Phase A có ship Pencil/Penboard support **hidden behind feature flag** ngay không, hay hoàn toàn defer Phase B? User đã nói "phải làm full" nhưng Phase B split độc lập sau.
- Threshold default 0.9 có conservative quá cho prototype phase không? Có thể profile-aware default đã cover (prototype 0.7).
- UAT narrative ngôn ngữ — đã chốt theo `narration.locale`, nhưng strings có hardcode trong template không? Phải reuse `narration-strings.yaml`.

---

## Acceptance gate (Phase A done = ship)

- 6 success criteria từ ROADMAP entry:
  1. Visual fidelity ≥90% AST node match (per-wave + holistic)
  2. 0 silent skip cho UI task thiếu `<design-ref>`
  3. UAT prompt 100% có 4 field
  4. Filter + Pagination test coverage ≥ ma trận expected
  5. Review phase UI profile spawn ≥1 Haiku scanner
  6. Phase 7.14.3 bugs B1-B6 root cause prevented qua workflow gates (regression test trên next FE phase)
