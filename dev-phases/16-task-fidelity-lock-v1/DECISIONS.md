# Phase 16 — Task Fidelity Lock — DECISIONS (draft)

**Lock status:** DRAFT — chờ user review từng D-XX trước khi viết SPECS.

---

## D-01 — Task body SHA256 hash + persist `<task>.meta.json`

**Why:** Cần ground truth để verify orchestrator KHÔNG paraphrase task
body khi composing executor prompt. SHA256 của task block raw là
canonical fingerprint.

**What:**
- `pre-executor-check.py` extract `<task id="N">...</task>` block, compute
  SHA256 (whitespace-normalized — strip trailing space mỗi line, collapse
  blank-line runs).
- Persist cạnh prompt body:
  ```
  ${PHASE_DIR}/.build/wave-${N}/executor-prompts/${TASK_NUM}.md
  ${PHASE_DIR}/.build/wave-${N}/executor-prompts/${TASK_NUM}.meta.json
  ```
- meta.json shape:
  ```json
  {
    "task_id": "T-3",
    "phase": "7.14.3",
    "wave": "wave-2",
    "source_path": "PLAN.md",
    "source_block_sha256": "abc123...",
    "source_block_line_count": 187,
    "source_block_byte_count": 8421,
    "extracted_at": "2026-04-27T10:00:00Z"
  }
  ```

**Acceptance:**
- Run `/vg:build` trên fixture phase, verify mỗi task có 2 file `.md` +
  `.meta.json` cạnh nhau, hash khớp lại task block trong PLAN.

---

## D-02 — Structured task schema (YAML frontmatter required)

**Why:** Task body free-form prose là root cause của lazy-read. Buộc
structured = orchestrator KHÔNG cần đọc dài để pick info.

**What:**
- PLAN.md task block format mới:
  ```xml
  <task id="T-3">
  ---
  acceptance:
    - "POST /api/sites returns 201 + site.id"
    - "Validator allows 'example.com' rejects 'not a url'"
  edge_cases:
    - "Domain with subdomain levels > 4 → reject"
    - "Concurrent POST same domain → 409"
  decision_refs: [P7.14.3.D-04, P7.14.3.D-05]
  design_refs: [sites-list.modal-add]
  body_max_lines: 200
  ---

  <description>
  Plain markdown body (≤ 200 lines per body_max_lines).
  </description>

  <file-path>apps/web/src/sites/SitesList.tsx</file-path>
  </task>
  ```
- Structured fields PASS verbatim qua `pre-executor-check.py` → executor
  prompt — không bao giờ summarize.
- Body markdown vẫn copied as-is, nhưng cap `body_max_lines` enforced
  bởi D-03 gate.

**Acceptance:**
- `verify-task-schema.py` validator BLOCK PLAN tasks không có
  frontmatter `acceptance:` block.
- Existing PLAN format (no frontmatter) → WARN với migration hint
  trong 1 release cycle, sau đó BLOCK.

---

## D-03 — PLAN body length BLOCK gate (250 lines default; bump tới 600 nếu cross_ai_enriched)

**Why:** Task body > 300 dòng = R4 silent truncate. Phải BLOCK upfront ở
blueprint stage thay vì swallow ở build stage.

**What:**
- `vg_completeness_check.py` (đã exist trong scope.md/blueprint.md) thêm
  Check E:
  - Mỗi task body line count > 250 → BLOCK (default).
  - Trừ phase CONTEXT.md có frontmatter `cross_ai_enriched: true` → cap
    tăng lên 600.
  - Override flag `--allow-long-task` (logs override-debt as kind=long-task).
- Error message hint: "Split task into smaller subtasks OR move prose
  to <decision-refs> in CONTEXT.md."

**Acceptance:**
- PLAN với 1 task 280 dòng + flag mặc định → BLOCK.
- Same PLAN với CONTEXT.md có `cross_ai_enriched: true` → PASS (vì cap
  600).

---

## D-04 — R4 budget conditional cap (phase metadata aware)

**Why:** R4 hiện hardcoded 300/500/200/etc — không adapt cho enriched
phase nơi context dày là intentional, không phải bloat.

**What:**
- `pre-executor-check.py` đọc CONTEXT.md frontmatter `cross_ai_enriched`.
  Khi true:
  - `task_context`: 300 → 600
  - `contract_context`: 500 → 800
  - `goals_context`: 200 → 400
  - `design_context`: 200 → 400 (giữ — design asset binary đã capped riêng)
  - `ui_map_subtree`: 80 → 200 (D-14 subtree có thể dày khi nhiều waves)
- Hard total max: 2500 → 4000 cho enriched phase.
- Log emit: "ℹ R4 budget: enriched-mode caps applied (cross_ai_enriched=true)."

**Acceptance:**
- Cùng PLAN, 2 lần build: với/không `cross_ai_enriched` → log thấy cap
  khác nhau.
- Enriched phase với tasks 500 dòng body → no truncation, no R4 BLOCK.

---

## D-05 — Cross-AI enrichment contract (must use `<context-refs>`)

**Why:** Cross-AI tools (Codex, Gemini) hiện inline prose vào task body.
Cần contract: enrichment OUTPUT phải structured.

**What:**
- Update `commands/vg/_shared/crossai-invoke.md` (existing) với rule:
  - Cross-AI khi enrich PLAN PHẢI emit changes dạng:
    1. Append decision IDs vào `<context-refs>`.
    2. Add new decision blocks vào CONTEXT.md (không vào PLAN body).
    3. Append edge cases vào task frontmatter `edge_cases:` array.
  - KHÔNG inline prose block > 30 dòng vào task body.
- Add `verify-crossai-output.py` validator chạy SAU `/vg:scope --crossai`
  hoặc `/vg:blueprint --crossai`: scan diff, BLOCK nếu task body grew >
  30 dòng prose mà không có corresponding `<context-refs>` ID added.

**Acceptance:**
- Cross-AI run thêm 50 dòng prose vào task → BLOCK với hint "Move to
  CONTEXT.md decision + reference via context-refs."
- Cross-AI run thêm 50 dòng prose nhưng cũng add 3 IDs vào context-refs
  + content tương ứng vào CONTEXT.md → PASS.

---

## D-06 — Validator `verify-task-fidelity.py` (post-spawn hash check)

**Why:** Catch orchestrator paraphrase tại runtime — final defense line.

**What:**
- Wired vào `/vg:build` step 8d (cùng position như verify-uimap-injection).
- Logic:
  1. Đọc `${PHASE_DIR}/.build/wave-${N}/executor-prompts/<task>.meta.json`
     để get expected `source_block_sha256` + `source_block_line_count`.
  2. Đọc tương ứng `<task>.md` (executor prompt body).
  3. Re-extract task block from PLAN.md by ID → recompute SHA256
     (whitespace-normalized cùng hàm như D-01).
  4. So 3-way: PLAN.md raw vs meta.json hash vs prompt body.
  5. Mismatch:
     - meta.json hash != PLAN re-extract → orchestrator có thể đã extract sai task
     - prompt body line_count < meta.json line_count × 0.9 → orchestrator
       paraphrased / truncated body
     - Cả hai mismatches → BLOCK
- Override `--skip-task-fidelity-audit` (logs debt as
  kind=task-fidelity-audit-skipped).

**Acceptance:**
- Test fixture: composed prompt = task body verbatim → PASS.
- Test fixture: composed prompt = task body với 30% lines removed →
  BLOCK với evidence "expected 187 lines, prompt has 130".
- Test fixture: composed prompt = task body paraphrased same length →
  BLOCK with hash mismatch evidence.

---

## Deferred / explicit non-decisions

- **Multi-AI orchestrator chain** (Claude → Codex executor) — separate phase.
- **PLAN auto-rewrite** khi BLOCK gate fire — Phase 18+ candidate.
- **Sub-agent reads PLAN directly** thay vì rely on orchestrator-passed
  prompt — orthogonal architecture change; Phase 16 lock orchestrator
  side trước.
- **CrossAI enrichment auto-formatter** — defer; D-05 chỉ BLOCK +
  hint, không tự reformat.
