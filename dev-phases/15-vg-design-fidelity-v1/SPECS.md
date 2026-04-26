# Phase 15 — VG Design Fidelity + UAT Narrative + Filter Test Rigor — SPECS

**Status:** DRAFT 2026-04-27 — awaiting user review & lock
**Source:** Synthesized from `DECISIONS.md` (D-01..D-18, all locked 2026-04-27)
**Implementation target:** RTB `.claude/...` (source of truth) → sync to vgflow-repo distribute mirror
**Spec owner:** vgflow-repo dev-phases (this folder)

---

## 1. Overview

### 1.1 Phase goal

Close 4 weak spots phơi bày bởi Phase 7.14.3 RTB:
1. Visual fidelity gate (4-format extractor + per-wave drift + holistic gate)
2. UAT narrative (4-field auto-fire + strict strings)
3. Filter + Pagination test rigor (4-layer codegen)
4. Review wide-see Haiku spawn regression fix

### 1.2 Scope summary

**Phase A ships (locked, full):**
- 4 design source extractors: HTML, PNG, Pencil MCP, Penboard MCP
- Extractor router + slug registry
- Design-ref hard-required enforcement (R4 MED → CRITICAL)
- UI-MAP 5-field schema lock + executor inject + per-wave scoped diff + holistic phase-end diff
- UAT 4-field narrative auto-fire + strict `narration-strings.yaml` reuse
- Filter + Pagination Test Rigor Pack (codegen extension)
- Review Haiku spawn validator + telemetry + investigation

**Phase B defers:**
- Threshold tune from battle-test data
- Edge case MCP integration (deadlock/timeout/MCP down)
- Cross-format diff (`.pen` + `.penboard` cùng phase merge)

### 1.3 Constraints (inherit from HANDOFF)

- Skill body — English; chat reply — Vietnamese
- Pronoun "tôi - bạn"
- Auto-detectable rule → BLOCK, không warn-only
- Không hardcode RTB-specific paths; reference qua `vg.config.md`

---

## 2. Architecture

### 2.1 Design extractor pipeline

```
.planning/design-source/
   ├── *.html              ──→ html-extractor.mjs (cheerio AST)
   ├── *.png               ──→ png-extractor.mjs (opencv-wasm + tesseract.js)
   ├── *.pen               ──→ pencil-extractor.mjs (mcp__pencil__*)
   └── *.penboard / *.flow ──→ penboard-extractor.mjs (mcp__penboard__*)
                                       │
                                       ▼
              extract-router.mjs (file-ext detect → route)
                                       │
                                       ▼
              .planning/design-normalized/
                 ├── refs/{slug}.structural.json   (DOM-AST or box-list tree)
                 ├── refs/{slug}.interactions.md   (handler map)
                 ├── screenshots/{slug}.{state}.png
                 └── slug-registry.json            (canonical slug → source path)
```

### 2.2 UI-MAP integration (5-part fix per D-12)

```
/vg:scope     ─→ phase_has_ui_changes flag (D-12c)
/vg:blueprint ─→ planner writes UI-MAP.md (5-field schema, owner-wave-id tags)
                 + verify-uimap-schema.py (D-15) BLOCK invalid nodes
/vg:build     ─→ step 8c: Haiku sub-agent extract subtree (D-14)
                 + inject UI-MAP subtree + design-ref to executor (D-12a)
                 + verify-uimap-injection.py BLOCK if missing
              ─→ post-wave-commit: scoped drift diff (D-12b/D-03)
                 + verify-wave-drift.py BLOCK if exceed threshold
/vg:review    ─→ aggregate WAVE-DRIFT-HISTORY.md (D-12d, informational)
                 + holistic full-tree drift gate (D-12e)
                 + verify-holistic-drift.py BLOCK if exceed threshold per profile (D-08)
```

### 2.3 Validator pipeline (BLOCK gates)

| Gate | Validator | Step | Decision |
|---|---|---|---|
| design-ref hard-required | `verify-design-ref-required.py` | blueprint | D-02 |
| UI-MAP schema | `verify-uimap-schema.py` | blueprint | D-15 |
| UI-MAP injection | `verify-uimap-injection.py` | build step 8c | D-12a |
| Wave-scoped drift | `verify-wave-drift.py` | build post-wave-commit | D-03/D-12b |
| Holistic drift | `verify-holistic-drift.py` | review post-fix | D-12e |
| UAT 4-field present | `verify-uat-narrative-fields.py` | accept step 4b | D-05 |
| UAT strings strict | `verify-uat-strings-no-hardcode.py` | accept step 4b | D-18 |
| Filter test coverage | `verify-filter-test-coverage.py` | test step 5d | D-16 |
| Haiku spawn fired | `verify-haiku-spawn-fired.py` | review run-complete | D-17 |
| Phase UI flag explicit | `verify-phase-ui-flag.py` | scope finalize | D-12c |
| Design-source extracted | `verify-design-extractor-output.py` | scope post-extract | D-01 |

### 2.4 Telemetry events (events.db)

```
scope.design_extractor.started      | scope.design_extractor.completed       | scope.design_extractor.failed
scope.slug_registry.emitted
blueprint.design_ref_required.passed| blueprint.design_ref_required.blocked
blueprint.uimap_schema.passed       | blueprint.uimap_schema.blocked
build.uimap_injected                | build.uimap_injection.blocked
build.wave_drift.measured           | build.wave_drift.blocked              | build.wave_drift.passed
build.haiku_subtree.spawned
review.haiku_scanner_spawned        | review.holistic_drift.measured
review.holistic_drift.blocked       | review.holistic_drift.passed
accept.uat_narrative.generated      | accept.uat_strings.blocked
test.filter_coverage.blocked        | test.filter_coverage.passed
```

### 2.5 Configuration additions (`vg.config.md`)

```yaml
mcp:
  servers:
    pencil:
      command: <mcp launcher per harness>
      tools_namespace: mcp__pencil__
    penboard:
      command: node D:/Workspace/Messi/Code/PenBoard/dist/mcp-server.cjs
      tools_namespace: mcp__penboard__

design_fidelity:
  thresholds:
    prototype: 0.7
    default: 0.85
    production: 0.95
  # Phase scope khai báo profile; missing → fallback default + warning
  default_profile: default
  threshold_override_allowed: true   # phase scope có thể override inline

design_extractor:
  source_dir: .planning/design-source
  output_dir: .planning/design-normalized
  router:
    .html: html-extractor
    .htm:  html-extractor
    .png:  png-extractor
    .pen:  pencil-extractor
    .penboard: penboard-extractor
    .flow: penboard-extractor
  png:
    ocr_engine: tesseract
    region_detector: opencv-wasm

narration:
  strings_file: .vg/narration-strings.yaml
  locale: vi   # default; phase scope can override
```

---

## 3. File manifest

### 3.1 New files (created)

**Extractors** (`.claude/scripts/design-extractors/`):
- `extract-router.mjs` — entry point, ext detect & dispatch
- `html-extractor.mjs` — cheerio AST → structural.json
- `png-extractor.mjs` — opencv-wasm + tesseract.js → box-list + OCR text
- `pencil-extractor.mjs` — wraps `mcp__pencil__*` tools → structural.json
- `penboard-extractor.mjs` — wraps `mcp__penboard__*` tools → structural.json
- `screenshot-pinner.mjs` — drives state-based screenshot capture
- `interaction-mapper.mjs` — extracts click/hover/keyboard handler map → interactions.md
- `slug-registry-builder.mjs` — emits `slug-registry.json` with canonical slug ↔ source path

**Validators** (`.claude/scripts/validators/`):
- `verify-design-extractor-output.py` (D-01)
- `verify-design-ref-required.py` (D-02)
- `verify-wave-drift.py` (D-03/D-12b)
- `verify-uimap-injection.py` (D-12a)
- `verify-phase-ui-flag.py` (D-12c)
- `verify-holistic-drift.py` (D-12e)
- `verify-uimap-schema.py` (D-15)
- `verify-uat-narrative-fields.py` (D-05)
- `verify-uat-strings-no-hardcode.py` (D-18)
- `verify-filter-test-coverage.py` (D-16)
- `verify-haiku-spawn-fired.py` (D-17)

**Codegen extensions** (`.claude/skills/vg-codegen-interactive/`):
- `templates/filter-coverage.test.tmpl` (D-16)
- `templates/filter-stress.test.tmpl` (D-16)
- `templates/filter-state-integrity.test.tmpl` (D-16)
- `templates/filter-edge.test.tmpl` (D-16)
- `templates/pagination-navigation.test.tmpl` (D-16)
- `templates/pagination-url-sync.test.tmpl` (D-16)
- `templates/pagination-envelope.test.tmpl` (D-16)
- `templates/pagination-display.test.tmpl` (D-16)
- `templates/pagination-stress.test.tmpl` (D-16)
- `templates/pagination-edge.test.tmpl` (D-16)
- `filter-test-matrix.mjs` — expected count matrix per filter type

**UAT narrative** (`.claude/skills/vg-uat-narrative/`):
- `build-uat-narrative.mjs` — generator step 4b
- `templates/uat-prompt.md.tmpl` — template using `{{narration.uat.*}}` keys only
- `narration-strings.uat.yaml.fragment` — UAT namespace addition to `narration-strings.yaml`

**UI-MAP tooling** (`.claude/scripts/ui-map/`):
- `generate-ui-map.mjs` — code-as-built UI-MAP generator (already partially exists; extend for scoped subtree mode)
- `diff-ui-map.mjs` — structural diff (subtree-scoped + holistic modes)
- `extract-subtree-haiku.mjs` — Haiku sub-agent driver per UI task (D-14)

**Skills (new commands or substantial new sections):**
- `.claude/commands/vg/uat-narrative-build.md` — manual entry (auto-fired by accept step 4b)
- `.claude/commands/vg/design-extract.md` — manual entry (auto-fired by scope)

### 3.2 Modified files

**Skill bodies** (`.claude/commands/vg/`):
- `scope.md` — add design-extractor auto-fire step + slug registry emission + `phase_has_ui_changes` requirement
- `blueprint.md` — R4 elevated to CRITICAL, schema-checker integration, owner-wave-id tagging requirement
- `build.md` — step 8c rewrite: Haiku subtree spawn + UI-MAP injection + post-wave drift gate
- `review.md` — Haiku spawn telemetry emit before Task call + holistic drift gate + WAVE-DRIFT-HISTORY aggregator + investigation hook for D-17 abort
- `accept.md` — insert step `4b_build_uat_narrative` between current 4 and 5
- `test.md` — codegen step 5d invokes filter/pagination matrix + verifier

**Config** (`vg.config.md`):
- add `mcp.servers.pencil.*` block
- add `mcp.servers.penboard.*` block
- add `design_fidelity.*` block
- add `design_extractor.*` block
- add `narration.*` block (if not already present — confirm)

**Schemas** (`.claude/schemas/`):
- `ui-map.schema.yaml` — 5-field-per-node lock (D-15)
- `structural-json.schema.yaml` — extractor output contract
- `narration-strings.schema.yaml` — uat namespace addition
- `slug-registry.schema.yaml` — slug ↔ source path mapping

**Existing narration-strings.yaml:**
- Add `uat:` namespace with 4-field labels + prompt strings (per D-18 fragment file)

---

## 4. Per-decision implementation specs

### D-01: 4-format extractor

**Goal:** Per slug emit `structural.json` + `screenshots/{state}.png` + `interactions.md`.

**Implementation:**
- **HTML:** `html-extractor.mjs` uses `cheerio` package. Parse → walk DOM → emit AST nodes `{tag, classes[], role, text, children_order, props}`. Detect `data-*` attributes as props.
- **PNG:** `png-extractor.mjs` uses `opencv.js` (region detection — bounding boxes by edge detection) + `tesseract.js` (OCR text per region). Emit box-list `{x, y, w, h, text, region_type}`.
- **Pencil:** `pencil-extractor.mjs` wraps `mcp__pencil__open_document(path)` → `mcp__pencil__get_editor_state` → `mcp__pencil__batch_get` để dump full node tree → `mcp__pencil__export_nodes` cho element box-list. Convert Pencil's node format → unified box-list schema.
- **Penboard:** `penboard-extractor.mjs` wraps `mcp__penboard__list_flows` → `mcp__penboard__read_flow(name)` per flow → `mcp__penboard__read_doc` cho doc nodes → `mcp__penboard__manage_entities({operation: 'list'})` cho entity bindings. Combine to flow-tree schema.

**Router:** `extract-router.mjs` reads `vg.config.md` `design_extractor.router` map → dispatch per ext. Unknown ext → emit warning + skip (not BLOCK).

**Output structure per slug:**
```
.planning/design-normalized/
├── refs/
│   ├── campaigns.structural.json
│   ├── campaigns.interactions.md
│   └── ...
├── screenshots/
│   ├── campaigns.default.png
│   ├── campaigns.hover.png
│   └── ...
└── slug-registry.json
```

**slug-registry.json schema:**
```json
{
  "slugs": {
    "campaigns": {
      "source_path": ".planning/design-source/campaigns.html",
      "format": "html",
      "extracted_at": "2026-04-27T10:00:00Z",
      "structural_json": ".planning/design-normalized/refs/campaigns.structural.json",
      "screenshots": [
        ".planning/design-normalized/screenshots/campaigns.default.png"
      ],
      "interactions_md": ".planning/design-normalized/refs/campaigns.interactions.md"
    }
  }
}
```

**Validator:** `verify-design-extractor-output.py` — for every file in `.planning/design-source/`, assert corresponding entry in `slug-registry.json` AND output files exist AND `structural.json` parses. BLOCK if mismatch.

**Telemetry:** `scope.design_extractor.started`, `.completed` (with count + duration), `.failed` (with file + error), `scope.slug_registry.emitted`.

**Test fixtures:**
- `tests/fixtures/extractor/html-basic.html` → expected `html-basic.structural.json`
- `tests/fixtures/extractor/png-mockup.png` → expected box-list snapshot
- `tests/fixtures/extractor/pencil-sample.pen` → expected node tree (recorded fixture)
- `tests/fixtures/extractor/penboard-sample.flow` → expected flow tree

**Acceptance:**
- Run `extract-router.mjs` on `tests/fixtures/extractor/` → 4 outputs match snapshot
- Validator passes when registry complete; BLOCK when 1 source missing extraction

---

### D-02: design-ref hard-required (R4 MED → CRITICAL)

**Goal:** UI task without `<design-ref slug>` → blueprint reject.

**Implementation:**
- `blueprint.md` rule R4: change severity `MED` → `CRITICAL`. Update plan-checker phase to call `verify-design-ref-required.py`.
- Validator: walk PLAN.md task tree → for each task with `<file-path>` matching `*.{tsx,vue,jsx,svelte}`, assert presence of `<design-ref slug="...">` child element.
- BLOCK with structured error: `{task_id, file_path, missing: 'design-ref', remediation: 'add <design-ref slug=\"<slug>\"/> referencing slug from .planning/design-source/'}`.
- Slug must exist in `slug-registry.json` (cross-check) — invalid slug → BLOCK.

**Telemetry:** `blueprint.design_ref_required.passed` / `.blocked` (with task_id + reason).

**Test fixtures:**
- `tests/fixtures/blueprint/missing-design-ref.plan.md` → expect BLOCK
- `tests/fixtures/blueprint/with-design-ref.plan.md` → expect PASS
- `tests/fixtures/blueprint/invalid-slug.plan.md` → expect BLOCK (slug not in registry)

**Acceptance:** Validator BLOCKs all 3 invalid fixtures; PASSes valid fixture.

---

### D-03 + D-12b: Per-wave scoped structural diff

**Goal:** After wave commit, diff scoped subtree (per wave's `owner-wave-id`) — drift > threshold → hard-block + rollback wave.

**Implementation:**
- `build.md` post-wave-commit hook: invoke `generate-ui-map.mjs --src <wave-touched-files> --format json` → write to temp `wave-N-uimap.json`.
- `diff-ui-map.mjs --as-built wave-N-uimap.json --as-planned UI-MAP.md --scope owner-wave-id=N --threshold <profile-derived>` → emit drift JSON report.
- Validator `verify-wave-drift.py` reads drift report → BLOCK if any node drift score > threshold.
- BLOCK action: emit rollback signal — git revert wave commit + emit `build.wave_drift.blocked` + halt build run.
- Threshold derived from `design_fidelity.profile` per phase scope (D-08).

**Drift score definition:**
- Per-node: weighted average of (tag match 30%, classes match 20%, children count 15%, props match 20%, text match 15%) — each component 0..1
- Subtree drift = mean of node drift scores
- Threshold check: drift > threshold (note: threshold is "fidelity" not "drift" — invert: 1 - drift > threshold)

**Telemetry:** `build.wave_drift.measured` (with score), `.blocked` / `.passed`.

**Test fixtures:**
- `tests/fixtures/build/wave-drift/clean.{plan-uimap.md, asbuilt-uimap.json}` → fidelity 0.95 → PASS at all profiles
- `tests/fixtures/build/wave-drift/moderate-drift.{...}` → fidelity 0.78 → PASS prototype, BLOCK default+production
- `tests/fixtures/build/wave-drift/heavy-drift.{...}` → fidelity 0.5 → BLOCK all profiles

**Acceptance:** All 3 fixtures produce expected verdict per profile.

---

### D-04 + D-09: i18n option B (lock mẫu strings, AI dịch ngoài mẫu)

**Goal:** Text-node level diff — text in mẫu must match; text without mẫu twin is free.

**Implementation:**
- `diff-ui-map.mjs` text-node comparison logic:
  - For each text node in as-built: find structural twin in as-planned (path-based: same ancestor chain).
  - If twin exists AND twin has text: assert exact match (case-sensitive). Mismatch → drift contribution.
  - If twin exists but twin has empty/no text: skip diff (AI-translated string, free).
  - If no twin: emit warning (orphan text node — possibly AI added) but don't fail.

**Test fixtures:**
- `tests/fixtures/build/i18n/translated-locked-string.{...}` — mẫu has "Campaigns", as-built has "Chiến dịch" → BLOCK
- `tests/fixtures/build/i18n/translated-toast.{...}` — toast not in mẫu, as-built has Vietnamese toast → PASS
- `tests/fixtures/build/i18n/orphan-text.{...}` — as-built has text not in mẫu structure → PASS with warning

**Acceptance:** Diff engine produces expected verdicts.

---

### D-05/D-06/D-07: UAT 4-field template

**Goal:** Each UAT prompt has 4 hard-required fields: entry, navigation, precondition, expected_behavior.

**Implementation:**
- Template `templates/uat-prompt.md.tmpl`:
```
{{narration.uat.entry_label}}: {{var.entry_url}} ({{narration.uat.role_label}}: {{var.role}}, {{narration.uat.account_label}}: {{var.account_email}} / {{var.account_password}})

{{narration.uat.navigation_label}}: {{var.navigation_steps}}

{{narration.uat.precondition_label}}: {{var.precondition}}

{{narration.uat.expected_label}}: {{var.expected_behavior}}

{{narration.uat.prompt_pfs}}
```
- Generator `build-uat-narrative.mjs` per D-XX/G-XX/design-ref:
  - **entry:** lookup `config.environments.local.dev_command` for port-role mapping (RTB convention: 5173 admin, 5174 publisher, 5175 advertiser, 5176 demand_admin) + read `apps/api/seed/accounts.json` (or configured seed path) → fill `entry_url`, `role`, `account_email`, `account_password`.
  - **navigation:** read TEST-GOALS `interactive_controls.entry_path` (per memory `project_vg_test_goals_enrichment`); fallback: routes file inspect.
  - **precondition:** read TEST-GOALS `precondition` field; fallback: phase seed state (default empty + warning).
  - **expected_behavior:** combine TEST-GOALS goal title + acceptance_criteria + CONTEXT D-XX rationale (truncate to 1-2 sentences).

**Design-ref UAT (D-07) extension:** template adds `{{narration.uat.region_label}}: {{var.region}}` line + `{{narration.uat.screenshot_compare}}: {{var.screenshot_path}}`.

**Validator:** `verify-uat-narrative-fields.py` — parse `UAT-NARRATIVE.md` → for each prompt block, assert presence of 4 (or 6 for design-ref) field markers. BLOCK if any missing.

**Telemetry:** `accept.uat_narrative.generated` (count of prompts).

**Test fixtures:**
- `tests/fixtures/accept/test-goals-with-controls.json` → expected `UAT-NARRATIVE.md` snapshot
- `tests/fixtures/accept/test-goals-missing-precondition.json` → expected fallback behavior + warning emit

---

### D-08: Threshold per profile (default 0.85)

**Goal:** Profile-aware threshold — `prototype: 0.7`, `default: 0.85`, `production: 0.95`.

**Implementation:**
- Phase scope CONTEXT.md frontmatter:
```yaml
design_fidelity:
  profile: prototype | default | production
  threshold_override: 0.88  # optional, takes precedence over profile
```
- Validators reading thresholds: `verify-wave-drift.py`, `verify-holistic-drift.py` — both call helper `lib/threshold-resolver.mjs` → returns effective threshold.
- Resolver order: `threshold_override` (if set) → `profile`-mapped threshold → `default_profile` (config) → hard fallback 0.85 + warning.

**Test fixtures:**
- `tests/fixtures/threshold/prototype-profile.context.md` → resolved 0.7
- `tests/fixtures/threshold/missing-profile.context.md` → resolved 0.85 + warning
- `tests/fixtures/threshold/with-override.context.md` → resolved override value

---

### D-10: `/vg:uat-narrative-build` auto-fire (step 4b)

**Goal:** Auto-fire between current accept steps 4 and 5; no manual command.

**Implementation:**
- `accept.md` step list update:
```
4_build_uat_checklist
4b_build_uat_narrative   ← NEW, auto-fire
5_interactive_uat
```
- Step 4b body: invoke `build-uat-narrative.mjs` → emit `${PHASE_DIR}/UAT-NARRATIVE.md`.
- Step 5 reads UAT-NARRATIVE.md prompts (instead of generating its own 1-line prompts).
- Manual entry `vg/uat-narrative-build.md` exposed for re-run scenarios but not required in normal flow.

**Telemetry:** `accept.uat_narrative.generated`.

**Acceptance:** Run accept on test phase → step 4b fires automatically, UAT-NARRATIVE.md emitted, step 5 uses it.

---

### D-11: Phase A FULL scope (no split B for extractors)

**Goal:** Ship all 4 extractors + all D-02..D-18 in Phase A.

**Implementation:** No code-level decision; this is scope policy. Reflected in:
- ROADMAP RTB entry (reverted; tracking moved to vgflow-repo dev-phases per HANDOFF status)
- `vg.config.md` `design_extractor.router` covers all 4 ext upfront
- Validator suite installs all 11 validators in single phase

**Acceptance:** Phase A complete check — all files in §3.1 manifest exist; all validators registered.

---

### D-12 (5-part UI-MAP fix): see D-12a/b/c/d/e below

#### D-12a: Executor inject UI-MAP subtree + design-ref

**Goal:** Build step 8c grep UI-MAP per `owner-wave-id` → extract subtree → inject into executor Sonnet prompt with design-ref structural+screenshot.

**Implementation:**
- `build.md` step 8c rewrite:
  1. Load wave manifest → identify wave's `owner-wave-id` (e.g., `wave-1`).
  2. Spawn Haiku sub-agent (D-14) with prompt: "Extract subtree of UI-MAP.md tagged `owner-wave-id=wave-1`. Return as markdown block."
  3. Receive subtree (~50 lines).
  4. Combine with design-ref (`structural.json` + `screenshots/{slug}.default.png` path + `interactions.md`).
  5. Inject combined block into executor task prompt under header `## UI-MAP-SUBTREE-FOR-THIS-WAVE` + `## DESIGN-REF`.
- Validator `verify-uimap-injection.py` runs immediately after step 8c, BEFORE executor invocation:
  - Inspect prepared executor prompt → assert presence of both injection headers + non-empty content.
  - BLOCK if missing for any UI task.

**Telemetry:** `build.uimap_injected` (per task), `.blocked`.

**Test fixtures:**
- `tests/fixtures/build/uimap-injection/with-injection.prompt` → PASS
- `tests/fixtures/build/uimap-injection/missing-uimap-block.prompt` → BLOCK
- `tests/fixtures/build/uimap-injection/missing-design-ref.prompt` → BLOCK

#### D-12b: Per-wave drift scoped — see D-03 above (consolidated implementation)

#### D-12c: phase_has_ui_changes explicit flag

**Goal:** Scope phase declares `phase_has_ui_changes: true|false` in CONTEXT.md frontmatter.

**Implementation:**
- `scope.md` finalize step: prompt user (or AI assistant) to determine flag based on phase goals.
- Validator `verify-phase-ui-flag.py`:
  - Parse CONTEXT.md frontmatter → assert `phase_has_ui_changes` key present.
  - If true: assert UI-MAP.md will be required (downstream blueprint check).
  - If false: assert no UI files in PLAN.md `<file-path>` (forward consistency check).
  - BLOCK if missing key or contradiction.

**Telemetry:** `scope.phase_ui_flag.set` (true/false).

#### D-12d: WAVE-DRIFT-HISTORY aggregator (informational)

**Goal:** Review reads all wave drift logs → emit `WAVE-DRIFT-HISTORY.md` table.

**Implementation:**
- `review.md` adds aggregator step (informational, NOT a gate):
  - Glob `${PHASE_DIR}/.wave-drift/*.json` (per-wave drift reports)
  - Render markdown table: `| wave-id | scope subtree | drift % | status | timestamp |`
  - Write `${PHASE_DIR}/WAVE-DRIFT-HISTORY.md`
  - Display in review report summary section.

**Telemetry:** none (informational).

#### D-12e: Holistic phase-end drift hard gate

**Goal:** After review fix-loop, run `generate-ui-map.mjs` on full dist build → diff vs full UI-MAP tree → BLOCK if exceeds profile threshold.

**Implementation:**
- `review.md` post-fix-loop hook:
  - `generate-ui-map.mjs --src <dist build dir> --format json --full-tree` → `holistic-asbuilt.json`
  - `diff-ui-map.mjs --as-built holistic-asbuilt.json --as-planned UI-MAP.md --mode full --threshold <profile-derived>`
  - Validator `verify-holistic-drift.py` reads diff result → BLOCK if exceeds.
- Catches container drift + cross-subtree integration drift wave-scoped misses.

**Telemetry:** `review.holistic_drift.measured`, `.blocked` / `.passed`.

---

### D-13: Auto-wire pipeline (no manual gate flip)

**Goal:** Default-on wiring; user does not flip config flags.

**Implementation:** Per skill body updates listed in §3.2 — every step fires its gate without explicit enable. Configuration only allows DISABLE via `design_fidelity.disabled: true` (escape hatch with loud warning at scope step).

**Telemetry:** `scope.design_pipeline.enabled` / `.disabled`.

---

### D-14: Haiku subtree extraction sub-agent

**Goal:** Spawn Haiku sub-agent per UI task to extract subtree (cost optimization).

**Implementation:**
- `extract-subtree-haiku.mjs` driver:
  - Inputs: `UI-MAP.md` path, target `owner-wave-id`, target `<file-path>`
  - Spawns Haiku Task tool agent with focused prompt: "Read UI-MAP.md. Find all nodes with `owner-wave-id=<X>` AND `owner-task-id` matching `<file-path>`. Return as compact markdown block."
  - Returns subtree (~50 lines vs full ~200-500).
- Used by D-12a inject step.

**Telemetry:** `build.haiku_subtree.spawned` (per task).

**Cost note:** Haiku is ~10× cheaper than Sonnet — net positive even with multiple spawns per wave.

---

### D-15: UI-MAP 5-field-per-node schema lock

**Goal:** Each UI-MAP node must have 5 fields: tag, classes, children_count_order, props_bound, text_content_static.

**Implementation:**
- `ui-map.schema.yaml`:
```yaml
node:
  required:
    - tag                      # string, e.g., "div", "Button", "Sidebar"
    - classes                  # array of strings, e.g., ["bg-white", "px-4"]
    - children_count_order     # object: {count: N, order: ["child1-id", "child2-id"]}
    - props_bound              # object: {data_prop_name: "campaigns", ...}
    - text_content_static      # string or null (null if dynamic)
  optional:
    - owner_wave_id            # added by planner (D-12a/b)
    - owner_task_id            # added by planner (D-14)
```
- Validator `verify-uimap-schema.py`:
  - Parse UI-MAP.md (assume YAML-fenced or structured markdown — define exact format)
  - For each node, assert all 5 required fields present AND types correct
  - BLOCK with per-node error list

**Telemetry:** `blueprint.uimap_schema.passed` / `.blocked`.

**Test fixtures:**
- `tests/fixtures/blueprint/ui-map/complete.md` → PASS
- `tests/fixtures/blueprint/ui-map/missing-classes.md` → BLOCK
- `tests/fixtures/blueprint/ui-map/missing-text-content.md` → BLOCK

---

### D-16: Filter + Pagination Test Rigor Pack

**Goal:** Codegen 14 filter cases + 18 pagination cases per declared interactive control.

**Implementation:**

**Filter matrix (`filter-test-matrix.mjs`):**
```js
const FILTER_MATRIX = {
  coverage: ['cardinality_enum', 'pairwise_combinatorial', 'boundary_values', 'empty_state'],
  stress: ['toggle_storm', 'spam_click_debounce', 'in_flight_cancellation'],
  state_integrity: ['filter_sort_pagination', 'url_sync', 'cross_route_persistence'],
  edge: ['xss_sanitize', 'empty_result', 'error_500_handling'],
};
// total: 14
```

**Pagination matrix:**
```js
const PAGINATION_MATRIX = {
  navigation: ['next', 'prev', 'first', 'last', 'jump_to_page', 'page_size_dropdown'],
  url_sync: ['paste_query_reload', 'filter_change_resets_page'],
  envelope_contract: ['meta_total_present', 'meta_page_present', 'meta_limit_present', 'meta_has_next_present'],
  display: ['x_y_of_z_label', 'empty_single_page', 'last_partial_page'],
  stress: ['spam_next', 'in_flight_cancel'],
  edge: ['out_of_range_zero', 'out_of_range_negative', 'cursor_based_integrity'],
};
// total: 18
```

**Codegen step:**
- `test.md` step 5d invokes per filter/pagination control declared in TEST-GOALS:
  - Loop matrix → render template per case → emit `tests/<feature>/<filter-name>.<case-name>.spec.ts`.
- Validator `verify-filter-test-coverage.py`:
  - Count generated test files per declared control.
  - Assert count ≥ matrix expected.
  - BLOCK if shortfall.

**Envelope contract template (B6 fix) example:**
```typescript
test('pagination envelope contract', async ({ page, request }) => {
  const response = await request.get('/api/<resource>?page=1&limit=10');
  const body = await response.json();
  expect(body.meta).toBeDefined();
  expect(body.meta.total).toEqual(expect.any(Number));
  expect(body.meta.page).toEqual(expect.any(Number));
  expect(body.meta.limit).toEqual(expect.any(Number));
  expect(body.meta.has_next).toEqual(expect.any(Boolean));
  // Drift detection: if TEST-GOALS declared shape doesn't match → fail
});
```

**Telemetry:** `test.filter_coverage.passed` / `.blocked`.

**Test fixtures:**
- `tests/fixtures/test/filter-coverage/test-goals-with-2-filters.json` → expect 28 generated files (2 × 14)
- `tests/fixtures/test/filter-coverage/test-goals-with-pagination.json` → expect 18 generated files
- `tests/fixtures/test/filter-coverage/missing-coverage.test-output/` → BLOCK

---

### D-17: Review Haiku spawn validator + investigation

**Goal:** Validator BLOCK if phase UI profile + 0 Haiku spawn event. Investigate /vg:review 7.14.3 abort.

**Implementation:**
- Telemetry: `review.md` Haiku spawn step (`2b-2`) — emit `review.haiku_scanner_spawned` event IMMEDIATELY before each `Task` tool call (currently spawns multiple Haiku per phase — emit per spawn).
- Validator `verify-haiku-spawn-fired.py` runs at review run-complete:
  - Query events.db: `SELECT COUNT(*) FROM events WHERE event_type='review.haiku_scanner_spawned' AND run_id=<current>`
  - If phase profile in `[web-fullstack, web-frontend-only, mobile-*]` AND count = 0 → BLOCK with explanation: "Review profile expected ≥1 Haiku scanner spawn. Investigate why step 2b-2 never executed (check abort sequence in this run's events log)."
  - Profile bypass: if phase scope declares `spawn_mode: none` AND profile in `[cli-tool, library]` → skip validator.
  - Profile UI but `spawn_mode: none` → blueprint reject upstream; here just BLOCK as defense-in-depth.

**Output additions:**
- `VIEW-MAP.md` — exhaustive elements/routes/modals/states (separate from `RUNTIME-MAP.json` which is goals-scoped).
- `BUG-REPORT-OUTSIDE-GOALS.md` — phase 2c bug detector reads VIEW-MAP → flag console errors, network 4xx/5xx, missing required button (compare design-ref), broken images, stuck loading states.

**Investigation task (parallel work item):**
- Examine events.db for run with `vg:review` phase=7.14.3:
  - 18:05:38Z run.started
  - 18:06:00-05Z validation events
  - 18:06:05Z run.blocked + contract.marker_warn x2
  - 18:06:31Z run.aborted (53s total)
- Hypothesis: contract gate fired before spawn step had chance to mark — markers expected post-spawn.
- Action: review contract gate decision tree; identify if marker check can be deferred until after spawn step OR if marker emission can be moved earlier in the spawn step.
- Document root cause + fix in dedicated investigation note → `dev-phases/15-vg-design-fidelity-v1/INVESTIGATION-D17.md`.

**Telemetry:** `review.haiku_scanner_spawned`, `review.run_aborted` (with phase + step reached).

**Test fixtures:**
- `tests/fixtures/review/spawn-fired.events.db` → PASS
- `tests/fixtures/review/no-spawn-ui-profile.events.db` → BLOCK
- `tests/fixtures/review/no-spawn-cli-profile.events.db` → PASS (bypass)

---

### D-18: UAT strings strict reuse `narration-strings.yaml`

**Goal:** UAT template forbids hardcoded literal strings; all strings reference `{{narration.uat.<key>}}`.

**Implementation:**

**`narration-strings.uat.yaml.fragment`** (merged into existing `narration-strings.yaml`):
```yaml
uat:
  entry_label:
    vi: "Truy cập"
    en: "Open"
  role_label:
    vi: "vai trò"
    en: "role"
  account_label:
    vi: "tài khoản"
    en: "account"
  navigation_label:
    vi: "Điều hướng"
    en: "Navigation"
  precondition_label:
    vi: "Tiền điều kiện dữ liệu"
    en: "Data precondition"
  expected_label:
    vi: "Hành vi mong đợi"
    en: "Expected behavior"
  region_label:
    vi: "Vùng tập trung"
    en: "Focus region"
  screenshot_compare:
    vi: "So sánh với screenshot"
    en: "Compare against screenshot"
  prompt_pfs:
    vi: "Đã thực hiện đúng chưa? [p=pass / f=fail / s=skip]"
    en: "Was this implemented correctly? [p=pass / f=fail / s=skip]"
```

**Validator `verify-uat-strings-no-hardcode.py`:**
- **Forward check:** parse UAT-NARRATIVE.md → extract every `{{narration.uat.<key>}}` reference → assert `<key>` exists in yaml AND has entry for current `narration.locale`. BLOCK if missing.
- **Backward check:** parse template `templates/uat-prompt.md.tmpl` → tokenize → for any token outside `{{...}}` interpolation AND markdown structural chars (`#`, `-`, `:`, whitespace) AND data-var (`{{var.*}}`), flag as literal string. Specifically:
  - Regex catch: `[A-Za-zÀ-ỹ]{2,}` (2+ word characters from Latin or Vietnamese) outside template tags.
  - BLOCK with line + offending text.
- **Render-time check** (defense-in-depth): after rendering UAT-NARRATIVE.md, re-scan output for literal text in same positions where template used `{{narration.uat.*}}` — assert no fallback to default text occurred (would indicate yaml lookup failed).

**Edge case exemptions:**
- `{{var.*}}` interpolations (DATA from extracted sources) — exempt
- Decision title/excerpt extracted from CONTEXT.md — exempt (treated as DATA)
- Markdown structural symbols, code-fence backticks — exempt

**Telemetry:** `accept.uat_strings.blocked` (with offending file + line).

**Test fixtures:**
- `tests/fixtures/accept/uat-strings/clean-template.md.tmpl` → PASS
- `tests/fixtures/accept/uat-strings/hardcoded-vietnamese.md.tmpl` → BLOCK
- `tests/fixtures/accept/uat-strings/missing-yaml-key.md.tmpl` → BLOCK
- `tests/fixtures/accept/uat-strings/yaml-missing-locale.yaml` → BLOCK at render

---

## 5. Validator inventory

| File | Decision | Step | Severity |
|---|---|---|---|
| `verify-design-extractor-output.py` | D-01 | scope post-extract | BLOCK |
| `verify-design-ref-required.py` | D-02 | blueprint | BLOCK (was MED) |
| `verify-uimap-schema.py` | D-15 | blueprint | BLOCK |
| `verify-phase-ui-flag.py` | D-12c | scope finalize | BLOCK |
| `verify-uimap-injection.py` | D-12a | build step 8c pre-executor | BLOCK |
| `verify-wave-drift.py` | D-03/D-12b | build post-wave-commit | BLOCK + rollback |
| `verify-holistic-drift.py` | D-12e | review post-fix-loop | BLOCK |
| `verify-uat-narrative-fields.py` | D-05/D-06/D-07 | accept step 4b | BLOCK |
| `verify-uat-strings-no-hardcode.py` | D-18 | accept step 4b | BLOCK |
| `verify-filter-test-coverage.py` | D-16 | test step 5d | BLOCK |
| `verify-haiku-spawn-fired.py` | D-17 | review run-complete | BLOCK |

Total: **11 validators**, all BLOCK (no warn-only per CLAUDE.md feedback rule).

---

## 6. Telemetry events inventory

| Event | Emitted by | Payload |
|---|---|---|
| `scope.design_extractor.started` | scope step | `{source_dir, file_count}` |
| `scope.design_extractor.completed` | scope step | `{slug_count, duration_ms}` |
| `scope.design_extractor.failed` | scope step | `{file_path, error}` |
| `scope.slug_registry.emitted` | scope step | `{registry_path, slug_count}` |
| `scope.phase_ui_flag.set` | scope step | `{value: true\|false}` |
| `scope.design_pipeline.enabled` | scope step | `{}` |
| `scope.design_pipeline.disabled` | scope step | `{reason}` |
| `blueprint.design_ref_required.passed` | validator | `{task_count}` |
| `blueprint.design_ref_required.blocked` | validator | `{task_id, file_path}` |
| `blueprint.uimap_schema.passed` | validator | `{node_count}` |
| `blueprint.uimap_schema.blocked` | validator | `{node_id, missing_fields}` |
| `build.haiku_subtree.spawned` | build step 8c | `{task_id, owner_wave_id}` |
| `build.uimap_injected` | build step 8c | `{task_id}` |
| `build.uimap_injection.blocked` | validator | `{task_id, missing_block}` |
| `build.wave_drift.measured` | drift gate | `{wave_id, fidelity_score}` |
| `build.wave_drift.blocked` | drift gate | `{wave_id, fidelity_score, threshold}` |
| `build.wave_drift.passed` | drift gate | `{wave_id, fidelity_score}` |
| `review.haiku_scanner_spawned` | review step 2b-2 | `{scanner_id, scope}` |
| `review.run_aborted` | review run | `{phase, step_reached, duration_ms}` |
| `review.holistic_drift.measured` | holistic gate | `{fidelity_score}` |
| `review.holistic_drift.blocked` | holistic gate | `{fidelity_score, threshold}` |
| `review.holistic_drift.passed` | holistic gate | `{fidelity_score}` |
| `accept.uat_narrative.generated` | accept step 4b | `{prompt_count}` |
| `accept.uat_strings.blocked` | validator | `{file, line, offending_text}` |
| `test.filter_coverage.passed` | validator | `{control_name, test_count}` |
| `test.filter_coverage.blocked` | validator | `{control_name, expected, actual}` |

Total: **26 telemetry event types**.

---

## 7. Schema definitions

### 7.1 `slug-registry.schema.yaml`

```yaml
type: object
required: [slugs]
properties:
  slugs:
    type: object
    additionalProperties:
      type: object
      required: [source_path, format, extracted_at, structural_json]
      properties:
        source_path: {type: string}
        format: {enum: [html, png, pencil, penboard]}
        extracted_at: {type: string, format: date-time}
        structural_json: {type: string}
        screenshots: {type: array, items: {type: string}}
        interactions_md: {type: string}
```

### 7.2 `structural-json.schema.yaml`

```yaml
type: object
required: [format_version, source_format, root]
properties:
  format_version: {const: "1.0"}
  source_format: {enum: [html, png, pencil, penboard]}
  root:
    $ref: "#/definitions/node"
definitions:
  node:
    type: object
    required: [tag, classes, children, text]
    properties:
      tag: {type: string}
      classes: {type: array, items: {type: string}}
      role: {type: string}
      text: {type: [string, "null"]}
      bbox: {type: object, properties: {x, y, w, h}}  # populated for png/pencil/penboard
      props: {type: object}
      children: {type: array, items: {$ref: "#/definitions/node"}}
```

### 7.3 `ui-map.schema.yaml`

(See D-15 spec above — 5-field-per-node lock.)

### 7.4 `narration-strings.schema.yaml`

```yaml
type: object
properties:
  uat:
    type: object
    required:
      - entry_label
      - role_label
      - account_label
      - navigation_label
      - precondition_label
      - expected_label
      - prompt_pfs
    additionalProperties:
      type: object
      required: [vi, en]
      properties:
        vi: {type: string}
        en: {type: string}
```

---

## 8. Test fixtures inventory

```
tests/fixtures/
├── extractor/
│   ├── html-basic.html + .expected.structural.json
│   ├── png-mockup.png + .expected.boxlist.json
│   ├── pencil-sample.pen + .expected.tree.json
│   └── penboard-sample.flow + .expected.tree.json
├── blueprint/
│   ├── missing-design-ref.plan.md
│   ├── with-design-ref.plan.md
│   ├── invalid-slug.plan.md
│   └── ui-map/
│       ├── complete.md
│       ├── missing-classes.md
│       └── missing-text-content.md
├── build/
│   ├── uimap-injection/
│   │   ├── with-injection.prompt
│   │   ├── missing-uimap-block.prompt
│   │   └── missing-design-ref.prompt
│   ├── wave-drift/
│   │   ├── clean.{plan-uimap.md, asbuilt-uimap.json}
│   │   ├── moderate-drift.{...}
│   │   └── heavy-drift.{...}
│   └── i18n/
│       ├── translated-locked-string.{...}
│       ├── translated-toast.{...}
│       └── orphan-text.{...}
├── threshold/
│   ├── prototype-profile.context.md
│   ├── missing-profile.context.md
│   └── with-override.context.md
├── accept/
│   ├── test-goals-with-controls.json
│   ├── test-goals-missing-precondition.json
│   └── uat-strings/
│       ├── clean-template.md.tmpl
│       ├── hardcoded-vietnamese.md.tmpl
│       ├── missing-yaml-key.md.tmpl
│       └── yaml-missing-locale.yaml
├── test/
│   └── filter-coverage/
│       ├── test-goals-with-2-filters.json
│       ├── test-goals-with-pagination.json
│       └── missing-coverage.test-output/
└── review/
    ├── spawn-fired.events.db
    ├── no-spawn-ui-profile.events.db
    └── no-spawn-cli-profile.events.db
```

---

## 9. Acceptance criteria (Phase A done = ship)

Mirror ROADMAP entry's 6 criteria + 1 added per D-18:

1. ✅ Visual fidelity ≥ profile threshold (per-wave + holistic gates)
2. ✅ 0 silent skip cho UI task thiếu `<design-ref>` (D-02 BLOCK)
3. ✅ UAT prompt 100% có 4 (or 6 for design-ref) field (D-05 BLOCK)
4. ✅ UAT prompt 0 hardcoded literal strings (D-18 BLOCK) — **added 2026-04-27**
5. ✅ Filter + Pagination test coverage ≥ matrix expected (D-16 BLOCK)
6. ✅ Review phase UI profile spawn ≥1 Haiku scanner (D-17 BLOCK)
7. ✅ Phase 7.14.3 bugs B1-B6 root cause prevented qua workflow gates — regression test trên next FE phase

**Per-decision acceptance** (each D-XX must have):
- 1+ validator script (exists in §5)
- 1+ telemetry event (exists in §6)
- 1+ test fixture demonstrating BLOCK trigger (in §8)
- 1+ test fixture demonstrating PASS path (in §8)
- Documentation update in skill body (in §3.2)

**E2E acceptance:** Run full vg pipeline (scope → blueprint → build → test → review → accept) on a synthetic test phase containing ≥1 UI task with HTML + PNG + Pencil + Penboard mẫu (4 format coverage smoke test). Pipeline produces all expected artifacts; all validators fire; all telemetry events emit; fixtures all pass.

---

## 10. Out-of-scope (Phase B)

- Threshold tune from production data (≥2 phase battle-test required)
- MCP integration edge cases: deadlock, server-down handling, retry policy
- Cross-format diff (phase với cả `.pen` AND `.penboard` — merge tree algorithm)
- PenBoard MCP tool subset filtering (currently using all 43 tools — Phase B may filter to extractor-relevant subset for security/audit)
- Pencil MCP write-back loop (Phase A read-only; Phase B may explore "AI suggests design correction → Pencil edit → re-extract" loop)

---

## 11. Open implementation questions (surface during blueprint)

These are NOT phase-scope open questions (those are resolved in HANDOFF). These are tactical decisions to make during blueprint creation:

- HTML extractor: support Tailwind utility class extraction → does diff engine treat utility classes as one bucket OR per-class? (recommendation: per-class, as utility = semantic)
- PNG extractor OCR confidence threshold: at what confidence drop does extractor emit `text: null` vs the OCR'd string? (recommendation: 0.6 confidence cutoff)
- Pencil/Penboard MCP timeout: `mcp__pencil__batch_get` on large `.pen` may take seconds — should extractor have per-tool timeout config? (recommendation: 30s per tool, configurable)
- UAT-NARRATIVE.md regeneration: if accept re-runs, should existing UAT-NARRATIVE.md be overwritten or merged with manual edits? (recommendation: regenerate fresh; track manual edits via separate `UAT-NARRATIVE-OVERRIDES.md`)
- Filter codegen: where to declare per-control test data fixtures? (recommendation: TEST-GOALS adds `interactive_controls.<name>.test_fixtures` field)

---

**END OF SPECS — awaiting user lock**
