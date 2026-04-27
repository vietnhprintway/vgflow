# Phase 16 — Task Fidelity Lock — BLUEPRINT v1

**Lock date:** 2026-04-27
**Total tasks:** 14 across 6 waves
**Estimated effort:** 14–18h (revised after audit: PLAN format reality requires backward-compat paths, +2h vs HANDOFF estimate)
**Source:** `SPECS.md` (this folder)
**Pattern:** atomic commit per task with message `feat(phase-16-T<wave>.<task>): <subject>`.

---

## Wave plan

| Wave | Theme | Tasks | Effort | Parallelism | Depends on |
|------|-------|-------|--------|-------------|------------|
| 0 | Foundation: validator slots + canonical hashing helper + audit fixtures | T-0.1, T-0.2, T-0.3 | 2h | parallel | — |
| 1 | D-01 hash + meta.json sidecar in pre-executor-check.py + build.md persist | T-1.1, T-1.2 | 3h | sequential | W0 |
| 2 | D-02 task schema parser + verify-task-schema.py | T-2.1, T-2.2 | 3h | sequential | W0 |
| 3 | D-03 body cap Check E + D-04 R4 conditional caps | T-3.1, T-3.2 | 2h | parallel | W2 (parser) |
| 4 | D-05 cross-AI contract + verify-crossai-output.py + D-06 task-fidelity audit | T-4.1, T-4.2, T-4.3 | 3h | parallel | W1 (meta.json), W2 (parser) |
| 5 | Acceptance + integration smoke + Phase 15 acceptance extension | T-5.1, T-5.2 | 2h | sequential | W3, W4 |

**Critical path:** W0 → W1 → W4 (depends on W1 meta.json) → W5
**Wall-clock min:** 2h + 3h + max(3, 3) + 2h = 10h with full parallelism on W2, W3, W4
**Wall-clock max (sequential):** 15h

---

## Wave 0 — Foundation (2h)

### T-0.1 — Register 3 validator slots in registry.yaml
- **File:** `scripts/validators/registry.yaml`
- **Action:** Append entries for:
  - `task-schema` (severity: warn, domain: artifact, added_in: v2.11.0-phase-16)
  - `crossai-output` (severity: block, domain: crossai, added_in: v2.11.0-phase-16)
  - `task-fidelity` (severity: block, domain: artifact, added_in: v2.11.0-phase-16)
- **Validation:** YAML parses; `/vg:validators list` shows 3 new entries.
- **Commit:** `feat(phase-16-T0.1): register 3 P16 validator slots`
- **Effort:** 0.5h

### T-0.2 — Canonical task-block SHA256 helper
- **File:** `scripts/lib/task_hasher.py` (new — Phase 15 created `lib/` dir for `threshold-resolver.py`, reuse pattern)
- **Action:** Implement `task_block_sha256(text) → (hex, line_count, byte_count)` per SPECS D-01 normalization rules; include 4 unit-test fixtures in docstring.
- **Validation:** Pytest in T-0.3 covers the helper.
- **Commit:** `feat(phase-16-T0.2): scripts/lib/task_hasher.py — canonical SHA256 helper`
- **Effort:** 1h

### T-0.3 — Fixtures + early test scaffold
- **Files:**
  - `fixtures/phase16/plans/heading-format.PLAN.md` — current `## Task N:` style (3 tasks)
  - `fixtures/phase16/plans/xml-format.PLAN.md` — new `<task id="N">` style with frontmatter (3 tasks)
  - `fixtures/phase16/plans/mixed-format.PLAN.md` — 2 heading + 1 xml
  - `fixtures/phase16/plans/long-task.PLAN.md` — 1 task body 280 lines
  - `fixtures/phase16/plans/enriched-task.PLAN.md` — 1 task body 500 lines + sibling CONTEXT.md frontmatter `cross_ai_enriched: true`
  - `fixtures/phase16/contexts/enriched.CONTEXT.md` — minimal CONTEXT with `cross_ai_enriched: true`
  - `scripts/tests/root_verifiers/test_phase16_task_hasher.py` — covers T-0.2 hasher (whitespace normalize, NFC, line count, byte count)
- **Validation:** `pytest test_phase16_task_hasher.py` — 6 tests pass.
- **Commit:** `test(phase-16-T0.3): fixtures + task_hasher unit tests`
- **Effort:** 0.5h

---

## Wave 1 — D-01 hash + meta.json (3h)

### T-1.1 — Extend pre-executor-check.py: persist meta.json sidecar
- **File:** `scripts/pre-executor-check.py`
- **Action:**
  - Import `task_hasher` from `scripts/lib/task_hasher.py`
  - After `extract_task_section()` returns, compute hash + add to CONTEXT_JSON output:
    ```json
    "task_meta": {
      "source_block_sha256": "...",
      "source_block_line_count": 187,
      "source_block_byte_count": 8421,
      "source_format": "heading"
    }
    ```
  - When build.md step 8c persists prompt body, ALSO write `<task>.meta.json` sidecar with the full meta shape per SPECS D-01.
- **Constraints:**
  - Existing extract_task_section() return type stays `str` for backward compat (callers expect string body); add NEW `extract_task_section_v2()` returning dict; pre-executor-check.py main() switches to v2.
  - Total file LOC ≤ 600 (was 473, +127 budget).
- **Validation:** Pytest fixture: extract heading-format task → meta dict has 4 keys + correct hash.
- **Commit:** `feat(phase-16-T1.1): pre-executor-check.py — task SHA256 + meta sidecar (D-01)`
- **Effort:** 2h

### T-1.2 — Extend build.md step 8c: write .meta.json next to .md
- **File:** `commands/vg/build.md`
- **Action:** In the "Phase 15 D-12a — persist composed prompt" bash block (added in T11.2 commit `2985a47`), extend the redirection to ALSO write `${PROMPT_PERSIST}.meta.json`:
  ```bash
  # After the prompt body is written, persist meta sidecar (P16 D-01)
  echo "$CONTEXT_JSON" | ${PYTHON_BIN} -c "
  import json, sys
  ctx = json.load(sys.stdin)
  meta = ctx.get('task_meta', {})
  meta.setdefault('task_id', $TASK_NUM)
  meta.setdefault('phase', '${PHASE_NUMBER}')
  meta.setdefault('wave', 'wave-${N}')
  meta.setdefault('extracted_at', __import__('datetime').datetime.utcnow().isoformat() + 'Z')
  print(json.dumps(meta, indent=2))
  " > "${PROMPT_PERSIST}.meta.json"
  ```
- **Validation:** Run build on Phase 15 fixture — for spawned task, both `.md` and `.meta.json` exist.
- **Commit:** `feat(phase-16-T1.2): build.md step 8c — persist .meta.json sidecar (D-01)`
- **Effort:** 1h

---

## Wave 2 — D-02 task schema (3h)

### T-2.1 — Implement extract_task_section_v2 (XML + heading parser)
- **File:** `scripts/pre-executor-check.py`
- **Action:**
  - Add `extract_task_section_v2(phase_dir, task_num, plan_file=None) -> dict`:
    - Returns `{body, format, frontmatter, raw_block}`
    - Detection: scan PLAN for `<task id="N">` first; if found, parse XML + optional YAML frontmatter; else fallback to existing heading regex.
    - YAML frontmatter parsing: lightweight inline parser (no PyYAML dep — match `build-uat-narrative.py` pattern from Phase 15).
  - `extract_all_tasks(plan_path) -> list[dict]` — for vg_completeness_check.py Check E iteration.
- **Validation:** Pytest covering 3 fixture PLANs (heading, xml, mixed); each task extracted with correct format + body + frontmatter.
- **Commit:** `feat(phase-16-T2.1): pre-executor-check.py — extract_task_section_v2 (XML + heading)`
- **Effort:** 2h

### T-2.2 — Implement verify-task-schema.py
- **File:** `scripts/validators/verify-task-schema.py`
- **Action:** Per SPECS D-02 logic.
  - argparse: `--phase`, `--mode {legacy,structured,both}` (default reads `vg.config.task_schema` then falls back to `legacy`)
  - Per task: classify format; mode gate; assert XML tasks have `acceptance:` frontmatter ≥1 entry.
  - Wired in `commands/vg/scope.md` Check section + `commands/vg/blueprint.md` step 2d validation gate.
- **Validation:** Pytest fixtures: heading PLAN + legacy mode → PASS; XML PLAN no acceptance → BLOCK; mixed PLAN → WARN.
- **Commit:** `feat(phase-16-T2.2): verify-task-schema.py + scope.md + blueprint.md wires (D-02)`
- **Effort:** 1h

---

## Wave 3 — D-03 body cap + D-04 R4 caps (2h)

### T-3.1 — vg_completeness_check.py Check E (body cap BLOCK)
- **File:** `scripts/vg_completeness_check.py`
- **Action:**
  - Import `extract_all_tasks` from `pre-executor-check` (or duplicate the parser if cross-import too tangled).
  - Add `check_e_task_body_length()` per SPECS D-03 logic.
  - Wire into existing main() check loop; respect `--allow-long-task` override.
  - Update Check report block (existing in main()) to include "Check E (body lines): {PASS|⛔ N blockers}".
- **Validation:** Pytest fixtures: 280-line task default → BLOCK; same task in enriched phase → PASS; same with `body_max_lines: 350` → PASS.
- **Commit:** `feat(phase-16-T3.1): vg_completeness_check Check E — task body cap (D-03)`
- **Effort:** 1h

### T-3.2 — pre-executor-check.py: R4 conditional caps
- **File:** `scripts/pre-executor-check.py`
- **Action:**
  - Read CONTEXT.md frontmatter `cross_ai_enriched` (lightweight parser).
  - Build `applied_caps` dict per SPECS D-04 cap table.
  - Add to CONTEXT_JSON output:
    ```json
    "budget_mode": "default|enriched",
    "applied_caps": { "task_context": 600, ... },
    "hard_total_max": 4000
    ```
  - Stderr log: `ℹ R4 budget: enriched-mode caps applied`.
  - Update `commands/vg/build.md` R4 enforcement block (line ~1350 from T7.3) — replace literal `BUDGETS = {...}` with `BUDGETS = ctx['applied_caps']` and `HARD_TOTAL_MAX = ctx['hard_total_max']`.
- **Validation:** Pytest fixture: enriched CONTEXT → cap 600 in JSON; build.md R4 reads from CONTEXT_JSON.
- **Commit:** `feat(phase-16-T3.2): pre-executor-check.py + build.md — R4 conditional caps (D-04)`
- **Effort:** 1h

---

## Wave 4 — D-05 cross-AI + D-06 fidelity audit (3h)

### T-4.1 — Update crossai-invoke.md with output contract (D-05)
- **File:** `commands/vg/_shared/crossai-invoke.md`
- **Action:** Append "## Output contract for PLAN/CONTEXT enrichment (P16 D-05)" section per SPECS D-05.
- **Validation:** No code; doc-only. Skill body still parses cleanly.
- **Commit:** `docs(phase-16-T4.1): crossai-invoke.md — D-05 output contract`
- **Effort:** 0.5h

### T-4.2 — Implement verify-crossai-output.py validator
- **File:** `scripts/validators/verify-crossai-output.py`
- **Action:** Per SPECS D-05 logic.
  - argparse: `--phase`, `--diff-base` (default `HEAD~1`)
  - Run `git diff --no-color <base> -- PLAN.md CONTEXT.md` via subprocess
  - Per-task body-line growth count (lines starting `+` inside `<task>` block, excluding frontmatter)
  - BLOCK threshold: > 30 added body lines AND no `<context-refs>` ID added
  - WARN: `cross_ai_enriched: true` flag missing in CONTEXT.md frontmatter when any change made
- **Wiring:** `commands/vg/scope.md` after Check E (T-3.1) + `commands/vg/blueprint.md` after Check section, only triggered when `--crossai` flag in args.
- **Validation:** Pytest fixtures with `git init` temp repo; commit base; commit cross-AI changes; run validator; assert BLOCK/PASS per scenario.
- **Commit:** `feat(phase-16-T4.2): verify-crossai-output.py + scope/blueprint wires (D-05)`
- **Effort:** 1.5h

### T-4.3 — Implement verify-task-fidelity.py + build.md wire (D-06)
- **File:** `scripts/validators/verify-task-fidelity.py` + `commands/vg/build.md` step 8d
- **Action:**
  - Validator per SPECS D-06 3-way comparison logic.
  - Tolerance: ≤10% body shortfall PASS; 10-30% WARN; >30% BLOCK; PLAN drift always WARN.
  - argparse: `--phase`, `--prompts-dir`
  - Wire into build.md step 8d after Phase 15 D-12a injection audit (line ~1985 of current build.md). Override `--skip-task-fidelity-audit` logs debt.
- **Validation:** Pytest fixtures: verbatim prompt → PASS; 30% removed → BLOCK; paraphrased same length → BLOCK (hash mismatch); PLAN modified → WARN.
- **Commit:** `feat(phase-16-T4.3): verify-task-fidelity.py + build.md 8d wire (D-06)`
- **Effort:** 1h

---

## Wave 5 — Acceptance + integration (2h)

### T-5.1 — Phase 16 acceptance smoke (test_phase16_acceptance.py)
- **File:** `scripts/tests/root_verifiers/test_phase16_acceptance.py`
- **Action:** Per Phase 15 acceptance pattern (8 dimensions). Cover:
  - 6 deliverables present (3 validators + task_hasher + helper integrations)
  - Hash determinism (same input → same SHA twice)
  - meta.json shape (9 required keys)
  - Both PLAN formats parse correctly
  - Body cap default 250 / enriched 600 / per-task override
  - R4 caps adapt per cross_ai_enriched flag
  - 3-way audit detects 30% truncation; tolerates ≤10%
  - crossai-output BLOCK on prose growth without context-refs
- **Validation:** All ~25 acceptance tests pass.
- **Commit:** `test(phase-16-T5.1): acceptance suite — 25 checks across 8 dimensions`
- **Effort:** 1.5h

### T-5.2 — Extend Phase 15 acceptance: integration smoke
- **File:** `scripts/tests/root_verifiers/test_phase15_acceptance.py`
- **Action:** Extend `TestPhase15RegressionGreen.test_phase15_suite_passes` to ALSO invoke Phase 16 + Phase 17 test files in subprocess; assert all green.
- **Validation:** Combined run pytest test_phase15_*.py test_phase16_*.py test_phase17_*.py PASS.
- **Commit:** `test(phase-16-T5.2): Phase 15 acceptance extends to cover P16+P17`
- **Effort:** 0.5h

---

## Goal-backward verification

**Phase 16 goal:** AI orchestrator KHÔNG được paraphrase task body when composing executor prompt; cross-AI enriched PLANs preserved end-to-end without R4 silent truncation.

| Failure mode | Pre-P16 | Post-P16 | Mechanism |
|---|---|---|---|
| Task body 400 lines silently truncated to 300 | YES (R4 cap, only WARN) | BLOCK at scope (D-03 cap 250 default) OR PASS (cap 600 enriched) | D-03 + D-04 |
| Cross-AI prose between tasks ignored by extraction | YES (regex skips) | BLOCK at cross-AI invocation (D-05 contract) | D-05 |
| `<context-refs>` 7 IDs × 100 lines truncated | YES (silent contract_context truncate) | PASS in enriched mode (cap 800) | D-04 |
| Orchestrator paraphrases task body | YES (no check) | BLOCK at build.md step 8d (D-06 hash mismatch) | D-06 |
| PLAN format inconsistency between waves | YES (silent) | WARN per task (D-02 mode=both default) | D-02 |

Goal achieved if T-5.1 acceptance test passes AND a manual dogfood with intentionally-paraphrased prompt fixture surfaces BLOCK at expected gate.

---

## Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| extract_task_section_v2() breaking change cascades to other callers | MED | HIGH | Keep v1 unchanged for backward compat; v2 is opt-in additive function |
| Cross-AI invocation contract too restrictive — cross-AI tools refuse to comply | MED | MED | D-05 validator at WARN initially (1 release cycle); cross-AI authors get migration window |
| Hash whitespace normalization produces collisions across 2 different task bodies | VERY LOW | HIGH | SHA256 collision space is astronomical even after normalization; documented |
| build.md `cat > "${PROMPT_PERSIST}.meta.json"` shell escape risk on Windows | LOW | LOW | Use Python heredoc to write JSON instead of shell echo; consistent with Phase 15 W3 deferred-fix theme |
| Phase 15 acceptance regression from build.md edits in T-1.2 + T-3.2 + T-4.3 | MED | MED | T-5.2 cross-phase regression test catches; rollback plan = revert atomic commits one at a time |

---

## Out-of-blueprint follow-ups

- Auto-rewrite PLAN when D-03 BLOCK fires — Phase 18+ candidate.
- Sub-agent self-verify reading PLAN directly — orthogonal architecture; defer.
- Hash chain HMAC signature — defer (current trust model = local dev OK).
- D-02 task schema v2 (priority + risk + estimated_hours fields) — Phase 19+ candidate.
- W3 deferred (Phase 15) — bash shell escape hardening on Windows path interpolation. Same fix path applies to T-1.2 build.md edits.
