# Phase 15 — Implementation Blueprint v2 (Task Breakdown)

**Status:** v2 DRAFT 2026-04-27 — awaiting user lock
**Replaces:** v1 (preserved in git history; major rebase per `EXISTING-INFRA-AUDIT.md`)
**Source-of-truth path:** `vgflow-repo/` top-level (NOT `RTB/.claude/`) — corrected per user 2026-04-27
**Total tasks:** 36 across 10 waves (down from v1 40 — consolidation per existing infra)
**Estimated effort:** 70-80h Phase A (down from v1 109h — heavy reuse of existing scaffolding)

---

## v2 vs v1 — Top changes

| Area | v1 (wrong) | v2 (correct) |
|---|---|---|
| Source path | `RTB/.claude/...` | `vgflow-repo/{commands,scripts,schemas,skills}/` |
| Schemas | YAML | JSON Schema draft-07 (`*.v1.json`) |
| narration-strings | Nested `uat:` namespace | Flat keys `uat_entry_label`, `uat_role_label`, ... |
| HTML extractor | Create new `html-extractor.mjs` | EXTEND `design-normalize-html.js` (cheerio AST output) |
| PNG extractor | Replace passthrough with OCR | Keep passthrough default; ADD OCR for `.structural.png` marker (per user decision #3) |
| Pencil handler | New `pencil-extractor.mjs` | Keep `.xml` legacy handler + ADD MCP handler `handler_pencil_mcp` for `.pen` (per user decision #2) |
| Penboard handler | New `penboard-extractor.mjs` | Keep `.pb` JSON legacy + ADD MCP handler `handler_penboard_mcp` for `.penboard` workspace (per user decision #1) |
| Router | New `extract-router.mjs` | EXTEND existing `FORMAT_HANDLERS` map in `design-normalize.py` |
| design-extract skill | Create new | EXISTS — 4-layer Haiku scan; just enhance Layer 1 inventory + Layer 4 manifest schema |
| UI-MAP generator | Slight extend | REFACTOR existing 1007-line `generate-ui-map.mjs` to add `--scope owner-wave-id=N` mode (per user decision #4) |
| `verify-wave-drift.py` | Build from scratch | EXTEND existing `verify-ui-structure.py` (already does MISSING/UNEXPECTED/LAYOUT_SHIFT/STRUCTURE_SHIFT) |
| `verify-holistic-drift.py` | Build from scratch | WIRE existing `visual-diff.py` (already pixelmatch) into `/vg:review` post-fix-loop |
| Telemetry | Custom emit | Use existing `python3 scripts/vg-orchestrator emit-event <event_type> <payload>` |
| Validator registration | Just create files | Files + REGISTER in `scripts/validators/registry.yaml` (id, severity, phases_active, domain, runtime_target_ms) |

---

## Conventions

- `T<wave>.<n>` = task ID, owner-wave-id = `wave-<wave>`
- **Files** = relative to `vgflow-repo/` (top-level, NOT under `.claude/`)
- **Validator registration** = each new validator MUST add entry to `scripts/validators/registry.yaml` per existing schema (id, path, severity, phases_active, domain, runtime_target_ms, added_in: v2.9.0-phase-15, description)
- **Telemetry** = call `_emit_event(event_type, payload)` helper pattern (see `scripts/sync-vg-skills.py:69`); wraps `vg-orchestrator emit-event` subprocess
- After wave complete: `git commit` atomically per task → `./sync.sh` to dogfood test on RTB
- **Est** = engineering hours
- Parallel-safe within each wave unless noted

---

## Wave 0 — Foundation (deps: none) — ~4h (down from 6h)

### T0.1 — Schemas (4 JSON Schema files)
- **Deliverable** at `vgflow-repo/schemas/`:
  - `slug-registry.v1.json`
  - `structural-json.v1.json`
  - `ui-map.v1.json` (5-field-per-node lock per D-15)
  - `narration-strings.v1.json` (validates UAT keys flat-pattern)
- **Pattern:** JSON Schema draft-07, `$id: https://vgflow.dev/schemas/<name>.v1.json`, additionalProperties false where strict
- **Note:** existing `interactive-controls.v1.json` is canonical reference for style
- **Decision:** D-01, D-15, D-18
- **Est:** 2h

### T0.2 — vg.config.template.md additions
- **Deliverable:** edit `vgflow-repo/vg.config.template.md`. ADD to existing `design_assets:` block:
  - `handlers.pen: pencil_mcp`
  - `handlers.penboard: penboard_mcp`
  - `mcp_pencil.command: <harness-resolved>` + `mcp_pencil.tools_namespace: mcp__pencil__`
  - `mcp_penboard.command: node D:/Workspace/Messi/Code/PenBoard/dist/mcp-server.cjs` + `mcp_penboard.tools_namespace: mcp__penboard__`
- ADD new sections:
  - `design_fidelity: { thresholds: {prototype: 0.7, default: 0.85, production: 0.95}, default_profile: default, threshold_override_allowed: true }`
  - `narration: { strings_file: commands/vg/_shared/narration-strings.yaml, locale: vi }` (if missing — confirm)
- **Decision:** D-01, D-08, D-13, D-18
- **Est:** 1h

### T0.3 — narration-strings.yaml UAT keys append
- **Deliverable:** edit `vgflow-repo/commands/vg/_shared/narration-strings.yaml`. ADD section comment `# ─── UAT narrative (D-18) ───` then 9 flat keys:
  - `uat_entry_label`, `uat_role_label`, `uat_account_label`, `uat_navigation_label`, `uat_precondition_label`, `uat_expected_label`, `uat_region_label`, `uat_screenshot_compare`, `uat_prompt_pfs`
  - Each: `{vi: "...", en: "..."}` per existing pattern
- **Decision:** D-18
- **Est:** 1h

---

## Wave 1 — Extractor extensions (deps: T0.1, T0.2) — ~12h (down from 24h)

**Goal:** ADD 2 MCP handlers + ADD HTML cheerio AST + ADD PNG OCR (marker-conditional). Keep all legacy handlers.

### T1.1 — HTML cheerio AST output
- **Deliverable:** EXTEND `vgflow-repo/scripts/design-normalize-html.js`:
  - After existing `extractCleanedHtml(page)` step, ADD parallel `extractStructuralAst()` using cheerio (`require('cheerio')`)
  - Walk DOM → emit unified node tree per `structural-json.v1.json` schema
  - Write to `refs/<slug>.structural.json` (sibling to existing `.structural.html`)
  - Append to JSON result payload: `structural_json: "refs/<slug>.structural.json"`
- **Validator:** T3.1 (extractor output)
- **Decision:** D-01 (HTML arm)
- **Est:** 3h

### T1.2 — PNG OCR for `.structural.png` marker (per user decision #3)
- **Deliverable:** EXTEND `vgflow-repo/scripts/design-normalize.py`:
  - In `handler_passthrough`, detect filename pattern `*.structural.png` OR sibling marker file `<slug>.structural.marker`
  - When detected → ADD opencv-wasm region detection + tesseract.js OCR pipeline → emit `refs/<slug>.structural.json` (box-list schema)
  - When not detected → keep current passthrough (default, photo screenshots untouched)
- **Decision:** D-01 (PNG arm, conditional)
- **Est:** 4h (opencv-wasm + tesseract install/test)

### T1.3 — Pencil MCP handler `handler_pencil_mcp` (per user decision #2)
- **Deliverable:** EDIT `vgflow-repo/scripts/design-normalize.py`:
  - ADD `'.pen': 'pencil_mcp'` to `FORMAT_HANDLERS` map
  - ADD `handler_pencil_mcp(input_path, output_dir, slug, **kwargs)` — wraps MCP tool calls (or shells to a Python MCP-client helper):
    - `mcp__pencil__open_document(input_path)`
    - `mcp__pencil__get_editor_state` → metadata
    - `mcp__pencil__batch_get` → node tree
    - `mcp__pencil__export_nodes` → element box-list
    - `mcp__pencil__get_screenshot` → save to `screenshots/<slug>.default.png`
  - Convert Pencil node format → unified box-list schema → write `refs/<slug>.structural.json`
  - Keep existing `handler_pencil_xml` for `.xml` legacy (no change)
- **Note:** MCP tools called from Python — likely need a small Node/Bun bridge OR use `vg-orchestrator` MCP shim. Spec the bridge contract during execution.
- **Decision:** D-01 (Pencil arm)
- **Est:** 4h

### T1.4 — Penboard MCP handler `handler_penboard_mcp` (per user decision #1)
- **Deliverable:** EDIT `vgflow-repo/scripts/design-normalize.py`:
  - ADD `'.penboard': 'penboard_mcp'` and `'.flow': 'penboard_mcp'` (workspace dir or flow file) to `FORMAT_HANDLERS`
  - ADD `handler_penboard_mcp(input_path, output_dir, slug, **kwargs)` — wraps MCP tools:
    - `mcp__penboard__list_flows`
    - `mcp__penboard__read_flow(flow_name)` per flow
    - `mcp__penboard__read_doc` for doc nodes
    - `mcp__penboard__manage_entities({operation: 'list'})` for entity bindings
    - `mcp__penboard__manage_connections` for data binding map → `refs/<slug>.interactions.md`
    - `mcp__penboard__generate_preview` → `screenshots/<slug>.default.png`
  - Combine flows → flow-tree schema → write `refs/<slug>.structural.json`
  - Keep existing `handler_penboard_render` for `.pb` legacy (no change)
- **Decision:** D-01 (Penboard arm)
- **Est:** 4h

### T1.5 — design_assets config + design-extract skill alignment
- **Deliverable:**
  - EDIT `vgflow-repo/vg.config.template.md` `design_assets.handlers` map (covered by T0.2)
  - EDIT `vgflow-repo/commands/vg/design-extract.md`: update Step 2 inventory display strings to include "Pencil MCP (.pen)" and "Penboard MCP (.penboard/.flow)"; update Step 5 manifest schema to include `mcp_handler_used` field
- **Decision:** D-01 (router glue), D-13 (auto-wire)
- **Est:** 1h

---

## Wave 2 — Extractor test fixtures (deps: Wave 1) — ~4h

### T2.1 — Fixture bundle
- **Deliverable** at `vgflow-repo/fixtures/extractor/`:
  - `html-basic.html` + `.expected.structural.json`
  - `png-mockup.structural.png` + `.expected.boxlist.json` (note `.structural.png` marker)
  - `png-photo.png` + `.expected.passthrough.json` (verify default passthrough preserved)
  - `pencil-sample.pen` + `.expected.tree.json` (pre-recorded MCP output)
  - `penboard-sample.flow` + `.expected.tree.json` (pre-recorded MCP output)
- **Decision:** D-01 acceptance per arm
- **Est:** 4h

---

## Wave 3 — Validators (deps: T0.1 schemas; partial deps Wave 1) — ~14h (down from 22h, due to extending verify-ui-structure.py and visual-diff.py)

### T3.0 — `lib/threshold-resolver.py` (helper)
- **Deliverable:** `vgflow-repo/scripts/lib/threshold-resolver.py` — reads phase CONTEXT + vg.config → returns effective threshold (override > profile > default fallback + warning)
- **Decision:** D-08
- **Est:** 1h
- **Depends on:** T0.2

### T3.1 — `verify-design-extractor-output.py` (D-01)
- **Logic:** every file in `.planning/design-source/` → matching slug-registry entry + outputs exist + `structural.json` parses against schema
- **Register in `registry.yaml`:** id `design-extractor-output`, severity `block`, phases_active `[scope]`, domain `extractor`
- **Est:** 2h

### T3.2 — `verify-design-ref-required.py` (D-02)
- **Logic:** walk PLAN.md → UI files require `<design-ref slug>`; slug exists in registry
- **Register:** id `design-ref-required`, severity `block`, phases_active `[blueprint]`, domain `artifact`
- **Est:** 2h

### T3.3 — `verify-uimap-schema.py` (D-15)
- **Logic:** parse UI-MAP.md (extract JSON code block per existing convention in `verify-ui-structure.py`) → assert each node has 5 required fields per schema
- **Register:** id `uimap-schema`, severity `block`, phases_active `[blueprint]`, domain `contract`
- **Est:** 2h

### T3.4 — `verify-phase-ui-flag.py` (D-12c)
- **Logic:** CONTEXT.md frontmatter `phase_has_ui_changes: true|false` present + downstream consistency
- **Register:** id `phase-ui-flag`, severity `block`, phases_active `[scope]`, domain `contract`
- **Est:** 1h

### T3.5 — `verify-uimap-injection.py` (D-12a)
- **Logic:** before executor invocation, inspect prepared prompt → assert headers `## UI-MAP-SUBTREE-FOR-THIS-WAVE` + `## DESIGN-REF` present + non-empty
- **Register:** id `uimap-injection`, severity `block`, phases_active `[build]`, domain `executor-input`
- **Est:** 2h

### T3.6 — Wave drift validator: EXTEND `verify-ui-structure.py` (D-03/D-12b)
- **Deliverable:** EDIT existing `vgflow-repo/scripts/verify-ui-structure.py`:
  - ADD `--scope owner-wave-id=<id>` flag → filter expected tree to nodes with matching tag
  - Existing MISSING/UNEXPECTED/LAYOUT_SHIFT logic reused verbatim
  - ADD threshold-resolver call (T3.0) → use profile-derived threshold instead of hardcoded `--max-missing/--max-unexpected`
  - Keep existing flags backward-compat
- **Register:** confirm existing entry in `registry.yaml`; update `phases_active` to include `build` (post-wave-commit)
- **Decision:** D-03, D-12b
- **Est:** 2h (extension only — most logic exists)

### T3.7 — Holistic drift validator: WIRE `visual-diff.py` + `verify-ui-structure.py` (D-12e)
- **Deliverable:** new wrapper script `vgflow-repo/scripts/verify-holistic-drift.py` that:
  - Calls existing `visual-diff.py compare` (pixelmatch) for screenshot drift
  - Calls existing `verify-ui-structure.py` (full tree, no `--scope`) for AST drift
  - Aggregates both into single BLOCK decision per profile threshold
- **Register:** id `holistic-drift`, severity `block`, phases_active `[review]`, domain `contract`
- **Decision:** D-12e
- **Est:** 2h (wrapper only)

### T3.8 — `verify-uat-narrative-fields.py` (D-05/06/07)
- **Logic:** parse UAT-NARRATIVE.md → each prompt block has 4 (or 6 for design-ref variant) field markers
- **Register:** id `uat-narrative-fields`, severity `block`, phases_active `[accept]`, domain `artifact`
- **Est:** 1h

### T3.9 — `verify-uat-strings-no-hardcode.py` (D-18)
- **Logic:**
  - **Forward:** regex catch `\{\{(uat_[a-z_]+)\}\}` references in UAT template → assert key exists in narration-strings.yaml + has entry for `narration.locale`
  - **Backward:** regex catch literal `[A-Za-zÀ-ỹ]{2,}` outside `{{...}}` interpolation in UAT template → BLOCK
- **Register:** id `uat-strings-no-hardcode`, severity `block`, phases_active `[accept]`, domain `artifact`
- **Decision:** D-18
- **Est:** 2h

### T3.10 — `verify-filter-test-coverage.py` (D-16)
- **Logic:** count generated test files per declared interactive control → assert ≥ matrix expected (14 filter / 18 pagination)
- **Register:** id `filter-test-coverage`, severity `block`, phases_active `[test]`, domain `test`
- **Depends on:** T6.1
- **Est:** 1h

### T3.11 — `verify-haiku-spawn-fired.py` (D-17)
- **Logic:** events.db query → phase UI profile + 0 `review.haiku_scanner_spawned` event → BLOCK. Profile bypass for cli-tool/library if `spawn_mode: none`
- **Register:** id `haiku-spawn-fired`, severity `block`, phases_active `[review]`, domain `orchestrator`
- **Depends on:** T9.4 (telemetry emit live)
- **Est:** 2h

---

## Wave 4 — UI-MAP tooling REFACTOR (deps: T0.1 + Wave 1) — ~6h (down from 10h)

### T4.1 — REFACTOR `generate-ui-map.mjs` (per user decision #4)
- **Deliverable:** EDIT `vgflow-repo/scripts/generate-ui-map.mjs`:
  - ADD CLI flag `--scope owner-wave-id=<id>` → filter emitted tree to nodes tagged with that wave-id
  - ADD CLI flag `--full-tree` (alias for current default behavior, explicit naming)
  - VERIFY current output schema: if it doesn't emit 5 required fields per D-15, ADD missing fields (likely `props_bound` and explicit `text_content_static`)
  - VERIFY `--format json` output (if exists per `--format tree|json|both`) matches `structural-json.v1.json` schema
- **Decision:** D-12a/b/e, D-15
- **Est:** 4h

### T4.2 — `extract-subtree-haiku.mjs` (D-14 driver)
- **Deliverable:** `vgflow-repo/scripts/extract-subtree-haiku.mjs` — drives Haiku Task agent per UI task; returns ~50-line subtree filtered by `owner-wave-id` + `owner-task-id`
- **Decision:** D-14
- **Est:** 2h

**Note:** No T4.3 — `diff-ui-map.mjs` NOT needed; T3.6 + T3.7 reuse existing diff infrastructure.

---

## Wave 5 — UAT narrative tooling (deps: T0.3, T3.8, T3.9) — ~5h

### T5.1 — UAT narrative generator + template
- **Deliverable:**
  - `vgflow-repo/scripts/build-uat-narrative.py` — generator step 4b
  - `vgflow-repo/commands/vg/_shared/templates/uat-narrative-prompt.md.tmpl` — uses `{{uat_*}}` flat keys + `{{var.*}}` data interpolations only
- **Logic:** sources from D-06 (port-role mapping, accounts seed, TEST-GOALS interactive_controls, CONTEXT D-XX rationale)
- **Decision:** D-05, D-06, D-07, D-10, D-18
- **Est:** 5h

---

## Wave 6 — Filter codegen (deps: T3.10) — ~6h

### T6.1 — Filter+pagination matrix + 10 templates
- **Deliverable:**
  - `vgflow-repo/skills/vg-codegen-interactive/filter-test-matrix.mjs` (matrix per SPECS §D-16)
  - `vgflow-repo/skills/vg-codegen-interactive/templates/filter-{coverage,stress,state-integrity,edge}.test.tmpl` (4 filter)
  - `vgflow-repo/skills/vg-codegen-interactive/templates/pagination-{navigation,url-sync,envelope,display,stress,edge}.test.tmpl` (6 pagination)
- **Decision:** D-16
- **Est:** 6h

---

## Wave 7 — Skill body updates (deps: validators + tooling Waves 3-6) — ~20h (UP from 12h due to skill body sizes)

**Estimate justification:** review.md 4730 lines, build.md 3270 lines, blueprint.md 2904 lines, accept.md 2018 lines. Surgical edits + maintaining surrounding context = 3-4h per skill.

### T7.1 — `scope.md` updates (1129 lines)
- **Changes:** auto-fire telemetry hook into `/vg:design-extract` (already exists as separate skill), require `phase_has_ui_changes` flag in CONTEXT, fire validators T3.1 + T3.4
- **Decision:** D-01 wire, D-12c, D-13
- **Est:** 2h

### T7.2 — `blueprint.md` updates (2904 lines)
- **Changes:** R4 severity MED → CRITICAL (find existing R4 mention), integrate T3.2 + T3.3 calls, require `owner-wave-id` + `owner-task-id` tagging in UI-MAP nodes (extend planner instructions)
- **Decision:** D-02, D-12a/b, D-15
- **Est:** 4h (large file + multiple touch points)

### T7.3 — `build.md` step 8c rewrite (3270 lines)
- **Changes:**
  - Step 8c: spawn Haiku subtree (T4.2) per UI task → inject UI-MAP subtree + design-ref into executor prompt
  - Run T3.5 validator BEFORE executor invocation
  - Post-wave-commit hook: T4.1 (subtree gen) → T3.6 (BLOCK + rollback signal)
- **Decision:** D-03, D-12a/b, D-13, D-14
- **Est:** 4h

### T7.4 — `review.md` updates (4730 lines, biggest)
- **Changes:**
  - Spawn step 2b-2: `_emit_event("review.haiku_scanner_spawned", ...)` IMMEDIATELY before each Task call (per T9.4 fix)
  - Post-fix-loop: T3.7 holistic drift gate
  - Aggregator: read all per-wave drift logs → emit `WAVE-DRIFT-HISTORY.md` (informational)
  - Run-complete: T3.11 validator
  - ADD `VIEW-MAP.md` exhaustive output + `BUG-REPORT-OUTSIDE-GOALS.md` from phase 2c
- **Decision:** D-12d, D-12e, D-13, D-17
- **Depends on:** T9.5 (D-17 root cause fix)
- **Est:** 6h (biggest file, multiple insertion points)

### T7.5 — `accept.md` step 4b insertion (2018 lines)
- **Changes:** insert `4b_build_uat_narrative` step between 4 and 5; step 5 reads UAT-NARRATIVE.md
- **Decision:** D-10, D-13
- **Est:** 2h

### T7.6 — `test.md` step 5d codegen
- **Changes:** invoke filter+pagination matrix per declared control → generate test files → run T3.10 validator
- **Decision:** D-13, D-16
- **Est:** 2h

**Note:** T7.7 from v1 (new design-extract.md command) ELIMINATED — skill already exists; updates folded into T1.5.

---

## Wave 8 — Test fixtures (deps: Wave 3 validators) — ~6h

(unchanged from v1; bundle paths now relative to `vgflow-repo/fixtures/`)

### T8.1 — Blueprint + UI-MAP fixtures (8 files)
- `vgflow-repo/fixtures/blueprint/`: missing-design-ref.plan.md, with-design-ref.plan.md, invalid-slug.plan.md
- `vgflow-repo/fixtures/blueprint/ui-map/`: complete.md, missing-classes.md, missing-text-content.md
- **Validates:** T3.2, T3.3
- **Est:** 1h

### T8.2 — Build fixtures (uimap-injection + wave-drift + i18n, 9 fixture sets)
- `vgflow-repo/fixtures/build/uimap-injection/`: 3 prompt fixtures
- `vgflow-repo/fixtures/build/wave-drift/`: 3 plan/asbuilt pairs
- `vgflow-repo/fixtures/build/i18n/`: 3 i18n drift fixtures
- **Validates:** T3.5, T3.6, plus i18n diff logic in T3.6
- **Est:** 2h

### T8.3 — Threshold + accept + test + review fixtures
- `vgflow-repo/fixtures/threshold/`: 3 context fixtures
- `vgflow-repo/fixtures/accept/`: UAT narrative + strings (6+)
- `vgflow-repo/fixtures/test/filter-coverage/`: 3
- `vgflow-repo/fixtures/review/`: 3 events.db fixtures
- **Validates:** T3.0, T3.8, T3.9, T3.10, T3.11
- **Est:** 3h

---

## Wave 9 — D-17 investigation + fix (PARALLEL with all waves; SHIP early) — ~6h (down from 8h)

**Evidence already gathered (T9.1 partial):**
- 5 review runs phase=7.14.3 last 48h
- Pattern: PASS and ABORT alternating (NOT deterministic) — `c4a375c9` PASS 13min, then `1c50d73c` ABORT 1:13, then `e098bcb8` PASS 02min, then `19013956` ABORT 53s
- → Conditional bug, not config error. Likely state-dependent (events.db state, marker file presence, or session_id-bound).

### T9.1 — Full event log dump per run_id
- **Action:** dump events for run_ids `19013956` (target ABORT 53s) + `c4a375c9` (closest PASS 11:24-11:24:02 same day) → side-by-side compare event sequence
- **Output:** INVESTIGATION-D17.md §1
- **Est:** 1h

### T9.2 — Read review.md + contract gate code
- **Action:** read `vgflow-repo/commands/vg/review.md` step 2b-2 (spawn step) + contract gate validator (likely `verify-command-contract-coverage.py` or `vg-contract-pins.py`) + identify decision tree
- **Output:** INVESTIGATION-D17.md §2
- **Est:** 2h

### T9.3 — Verify hypothesis from event diff
- **Action:** based on T9.1 + T9.2, identify exact branch where ABORT runs diverge from PASS runs
- **Hypotheses:** H1 contract gate stale marker, H2 contract gate state precedence, H3 profile detection race
- **Output:** INVESTIGATION-D17.md §3
- **Est:** 1h

### T9.4 — Telemetry emit position fix
- **Action:** ensure `_emit_event("review.haiku_scanner_spawned", ...)` IMMEDIATELY before each Task tool call in `vgflow-repo/commands/vg/review.md`
- **Decision:** D-17
- **Est:** 1h

### T9.5 — Root cause fix (depends on T9.3)
- **Action:** apply fix per identified cause
- **Files:** TBD
- **Est:** 1h (small surgical edit if hypothesis correct)

### T9.6 — Document INVESTIGATION-D17.md
- **Output:** `dev-phases/15-vg-design-fidelity-v1/INVESTIGATION-D17.md` complete
- **Est:** included in T9.1-9.5

---

## Wave 10 — E2E smoke + acceptance (deps: ALL prior waves) — ~6h

### T10.1 — Synthetic test phase
- **Deliverable:** `vgflow-repo/fixtures/e2e/phase-15-smoke/` with:
  - 1 UI task per format (`.html`, `.structural.png`, `.pen`, `.flow`)
  - PLAN.md with `<design-ref>` for each
  - UI-MAP.md with 5-field-per-node + owner-wave-id tags
  - TEST-GOALS with 2 filters + 1 pagination control
- **Est:** 2h

### T10.2 — Run full pipeline + verify
- **Action:** install vgflow-repo into a sandbox project (or use RTB as dogfood) → `/vg:design-extract` → `/vg:scope` → `/vg:blueprint` → `/vg:build` → `/vg:test` → `/vg:review` → `/vg:accept`
- **Verify:**
  - All 11 validators fire (PASS clean fixture, BLOCK on injected defects)
  - All 26 telemetry events emit (events.db query)
  - All 7 acceptance criteria met (per SPECS §9)
- **Est:** 4h

---

## Cross-wave dependency graph (v2)

```
Wave 0 ──┬──> Wave 1 ──> Wave 2
         ├──> Wave 3 (validators) ──> Wave 7 (skills) ──> Wave 10
         └──> Wave 4 (UI-MAP refactor) ──> Wave 7
Wave 5 ──> Wave 7.5 (accept)
Wave 6 ──> Wave 7.6 (test)
Wave 9 (PARALLEL with everything) ──> Wave 7.4 (review)
Wave 8 (PARALLEL with Wave 7) ──> Wave 10
```

**Critical path:** Wave 0 → 1 → 4 → 7 → 10 (~36-40h sequential, ~7-8 days with normal parallelism).

---

## Effort summary v2

| Wave | Tasks | v2 Est | v1 Est | Notes |
|---|---|---|---|---|
| 0 | 3 | 4h | 6h | Append flat keys, JSON schemas |
| 1 | 5 | 12h | 24h | EXTEND existing extractors, not greenfield |
| 2 | 1 | 4h | 4h | Same |
| 3 | 12 | 14h | 22h | Extend verify-ui-structure + visual-diff |
| 4 | 2 | 6h | 10h | Refactor existing generator only |
| 5 | 1 | 5h | 5h | Same |
| 6 | 1 | 6h | 6h | Same |
| 7 | 6 | 20h | 12h | UP — large skill bodies |
| 8 | 3 | 6h | 6h | Same |
| 9 | 6 | 6h | 8h | Partial T9.1 already done |
| 10 | 2 | 6h | 6h | Same |
| **Total** | **41** | **89h** | **109h** | ~7-8 days @ 12h/day with parallelism |

(Note: 41 tasks now — 1 added net: T7.7 removed, T0.x clarified, fixtures consolidated.)

---

## Atomic commit + sync workflow per wave (corrected)

1. Wave starts on `vgflow-repo/` (source of truth).
2. Tasks within wave commit atomically.
3. After wave completes: optionally `./sync.sh` to deploy to RTB for dogfood test.
4. vgflow-repo commit pattern: `feat(phase-15-wave-N): <wave goal summary>` (or `fix:`/`refactor:` per task type).
5. Smoke-test post-wave: re-run validators on existing fixtures to ensure no regression.

---

## Open implementation tactical questions (defer to execution)

(Same as v1 §11; recommendations stand)
- HTML extractor: Tailwind utility class per-class (rec)
- PNG OCR confidence cutoff 0.6 (rec)
- MCP per-tool timeout 30s (rec)
- UAT-NARRATIVE.md regen + separate `UAT-NARRATIVE-OVERRIDES.md` (rec)
- Filter codegen test_fixtures field in TEST-GOALS (rec)

---

## Acceptance for blueprint v2 lock

- [ ] User confirms source-of-truth correction (vgflow-repo top-level, not `RTB/.claude/`)
- [ ] User confirms 4 decisions applied (legacy + MCP for Pencil/Penboard, structural-marker for PNG OCR, refactor generate-ui-map.mjs)
- [ ] User confirms effort 89h ≈ 7-8 days realistic
- [ ] User confirms parallel-safe assumptions (Wave 9 parallel; Waves 7+8 parallel)
- [ ] User confirms validator registry pattern (entry in `registry.yaml` per existing schema)
- [ ] User confirms reuse strategy (extend `verify-ui-structure.py`, wire `visual-diff.py`)

**On lock:** ready to start Wave 0 + Wave 9 in parallel. First atomic commit: `feat(phase-15-wave-0): foundation schemas + config + uat narration keys`.

---

**END OF BLUEPRINT v2 — awaiting user lock**
