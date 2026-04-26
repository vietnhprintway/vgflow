# Phase 16 — Task Fidelity Lock — HANDOFF

**Status:** PLANNING (decisions drafted, awaiting user lock)
**Created:** 2026-04-27
**Estimated effort:** 14–18h (lớn hơn P17 vì đụng pre-executor-check.py, R4
budget logic, build.md persist flow, + 2 validators mới)
**Dependencies:** Phase 15 D-12a (executor prompt persist tới
`.build/wave-N/executor-prompts/<task>.md` — cơ sở để hash check)
**Risk:** MEDIUM (đụng path critical pre-spawn; rollout cần feature flag)

---

## TL;DR — what this phase does

Đóng gap dự đoán bởi user 2026-04-27 sau khi Phase 15 ship: **AI
orchestrator có thể "lười đọc" PLAN dài, đặc biệt khi blueprint enriched
bởi cross-AI (Codex/Gemini) — tóm tắt task body thay vì pass verbatim, làm
sub-agent (Sonnet executor) build code thiếu acceptance criteria/edge
cases**.

5 failure modes hiện không có cơ chế bảo vệ (xem analysis HANDOFF §"Why now"):
1. Task body > 300 dòng → R4 budget TRUNCATE silently (chỉ WARN không BLOCK).
2. Cross-AI prose context giữa `<task>` blocks → regex `<task...>...</task>`
   skip toàn bộ.
3. `<context-refs>` 5+ IDs × 100 dòng/ID → CONTRACT_CONTEXT vượt 500 cap →
   truncate silently.
4. T11.2 (Phase 15) chỉ check H2 markers tồn tại + ≥10 chars body — body
   "TODO: insert subtree here" cũng pass.
5. Không có hash-check task block ↔ persisted prompt — orchestrator
   paraphrase thoải mái.

**Fix shape (6 decisions):**
- Persist task block hash (SHA256) vào `<task>.meta.json` cạnh
  `<task>.md` prompt persist; validator post-spawn so hash match.
- PLAN task schema chuẩn hóa: YAML frontmatter (acceptance, edge_cases,
  decision_refs) bắt buộc; body markdown ≤ 250 dòng (BLOCK quá ngưỡng
  trừ flag `--allow-long-task`).
- R4 budget conditional cap: phase frontmatter `cross_ai_enriched: true`
  → bump task=600, contract=800.
- Cross-AI enrichment contract: tools enrich PHẢI append vào
  `<context-refs>`, KHÔNG inline prose blob.
- Validator `verify-task-fidelity.py`: so SHA256 task body trong PLAN
  ↔ trong persisted prompt; mismatch BLOCK.
- Pre-spawn integrity check: orchestrator validate composed prompt
  contains all `<task-id>` body content from PLAN verbatim (line count
  diff ≤ 10% tolerance for whitespace).

**Expected impact:**
- AI orchestrator KHÔNG được paraphrase task → sub-agent nhận instruction
  hoàn chỉnh.
- Acceptance criteria + edge cases SURVIVE từ planner ý đồ → executor
  code thực thi.
- Cross-AI enrichment value PRESERVED thay vì bị summarize away.

---

## Why now (vs defer)

User đã thử workflow trên dự án khác, gặp PLAN dài enriched cross-AI và
LO ÂU rõ ràng về failure mode này. Không phải "khi nào sẽ fail" mà là
"đã từng fail, không có gate catch."

Phase 15 vừa ship đóng PHẦN (T11.2 persist + H2 marker check) nhưng
KHÔNG đóng task body fidelity. Defer = mỗi run /vg:build trên enriched
phase = roulette: orchestrator có thể paraphrase, sub-agent build mơ
hồ, chỉ phát hiện ở review/UAT khi đã commit nhiều code.

**Cost của không fix:** 1 wave (~8h dev work) bị throw away vì paraphrase
→ rollback + replan. Một lần thôi đã eat hết Phase 16 budget.

---

## Out of scope (defer)

- **Multi-AI orchestrator** (Claude orchestrator → Codex executor) —
  separate chuyên đề; Phase 16 chỉ siết Claude → Sonnet path.
- **PLAN auto-rewrite** khi task body quá dài — Phase 16 BLOCK + đề xuất
  user split task; auto-rewrite là Phase 18+ candidate.
- **Sub-agent self-verify** (sub-agent đọc full PLAN, không chỉ task block)
  — orthogonal pattern; Phase 16 lock orchestrator side trước.

---

## Files trong working folder

- `HANDOFF.md` — bạn đang đọc
- `DECISIONS.md` — 6 decisions D-01..D-06 detail
- `ROADMAP-ENTRY.md` — block draft cho roadmap
- `SPECS.md` — sẽ tạo SAU khi user lock decisions
- `BLUEPRINT.md` — sẽ tạo SAU SPECS

---

## Recommended sequence vs Phase 17

| Phase | ROI | Risk | Suggest |
|---|---|---|---|
| **17** Test Session Reuse | Wall-clock test -50%/-80% NGAY | LOW (template + helper) | Ship trước |
| **16** Task Fidelity Lock | Tránh build code thiếu (asymmetric — 1 lần fail = -8h) | MEDIUM (đụng critical path) | Ship sau, có thời gian thiết kế kỹ |

**Dogfood note:** Phase 17 ship trước cho phép RTB Phase 7.15+ test
nhanh hơn → có nhiều cycle hơn để dogfood Phase 16 protection.
