# Phase 15 — Existing Infrastructure Audit

**Created:** 2026-04-27 — pre-execution discovery
**Trigger:** Wave 0 start revealed major existing infra in RTB `.claude/...` not accounted for in SPECS/BLUEPRINT v1.
**Status:** BLOCKING — BLUEPRINT must rebase before any code work.

---

## 1. Schema infrastructure (`/d/Workspace/Messi/Code/RTB/.claude/schemas/`)

**Pattern:** JSON Schema draft-07, namespace `https://vgflow.dev/schemas/`, files `*.v1.json` or `*.json`.

**Existing (13 schemas):**
- `context.v1.json` — phase CONTEXT.md frontmatter
- `specs.v1.json` — phase SPECS.md frontmatter
- `plan.v1.json` — phase PLAN.md frontmatter
- `interactive-controls.v1.json` — TEST-GOALS interactive_controls block
- `runtime-contract.json` — runtime contract definitions
- `uat.v1.json` — UAT artifact schema
- `event.json` — events.db event payload
- `validator-output.json` — validator return shape
- `summary.v1.json` — phase summary
- `test-goals.v1.json` — TEST-GOALS schema
- `evidence-json.json` — evidence manifest
- `override-debt-entry.json` — override debt log entry
- `README.md` — schema docs index

**MISSING (Phase 15 needs):**
- `slug-registry.v1.json`
- `structural-json.v1.json`
- `ui-map.v1.json` (5-field-per-node lock)
- `narration-strings.v1.json` (UAT keys validation)

**SPECS impact:** ❌ T0.1 wrong — proposed YAML schemas. Must rewrite as JSON Schema draft-07 matching existing pattern.

---

## 2. narration-strings.yaml (`/d/Workspace/Messi/Code/RTB/.claude/commands/vg/_shared/narration-strings.yaml`)

**Pattern:** FLAT keys (NOT nested namespace), each `<key>: { vi: ..., en: ... }`.

**Existing categories (sample):**
- Gates: `gate_blocked_intermediate`, `gate_blocked_nottest`, `gate_blocked_commits`, `gate_blocked_design`, `gate_blocked_tests`, `gate_blocked_debt_critical`
- Override/Debt: `override_logged`, `debt_open_warning`, `debt_auto_escalated`
- Goals: `goal_start`, `goal_step`, `goal_end_ready`, `goal_end_blocked`, `goal_end_unreachable`, `goal_end_infra`
- Phases/Views: `phase_header`, `view_scan_start`, `view_scan_done`
- Fix routing: `fix_routed_inline`, `fix_routed_spawn`, `fix_routed_escalated`
- Telemetry: `telemetry_emit_fail`

**Helper:** `t()` function from `narration-i18n.md`

**SPECS impact:** ❌ D-18 wrong format. Proposed nested `uat:` namespace (like `narration.uat.entry_label`). Must use flat keys: `uat_entry_label`, `uat_role_label`, `uat_navigation_label`, etc. Validator regex must match flat pattern.

---

## 3. Design extractor infrastructure (already 80% built)

**Existing files:**
- `.claude/scripts/design-normalize.py` — **503 lines** — universal normalizer entry point
- `.claude/scripts/design-normalize-html.js` — **254 lines** — Playwright HTML render helper

**Existing FORMAT_HANDLERS map (`design-normalize.py:23-33`):**
```python
FORMAT_HANDLERS = {
    '.html': 'playwright_render',
    '.htm':  'playwright_render',
    '.png':  'passthrough',
    '.jpg':  'passthrough',
    '.jpeg': 'passthrough',
    '.webp': 'passthrough',
    '.fig':  'figma_fallback',
    '.pb':   'penboard_render',     # JSON file parse, NOT MCP
    '.xml':  'pencil_xml',           # XML legacy, NOT MCP
}
```

**Existing handlers (skeletons + impls):**
- `handler_passthrough` — copies PNG/JPG/WEBP to `screenshots/{slug}.default.png` (no OCR, no region detection)
- `handler_playwright_render` — delegates to `design-normalize-html.js` → screenshot + cleaned HTML + interactions list (no cheerio AST)
- `handler_penboard_render` — parses `.pb` JSON file directly, extracts pages + node tree (NOT live MCP)
- `handler_pencil_xml` — XML parser for legacy Pencil files (NOT MCP)
- `handler_figma_fallback` — placeholder

**Output structure (existing):**
```
<output>/screenshots/<slug>.<state>.png
<output>/refs/<slug>.structural.<ext>     # .html for playwright, .json for penboard
<output>/refs/<slug>.interactions.md
<output>/refs/<slug>.states.json
<output>/manifest.json
```

**Existing capabilities by format:**
| Format | Existing | Missing per Phase 15 |
|---|---|---|
| HTML | Playwright screenshot + cleaned HTML + interactions | **Cheerio AST → unified node tree** (D-01) |
| PNG | Passthrough copy | **OCR (tesseract.js) + region detection (opencv-wasm)** (D-01) |
| Pencil | XML legacy parser | **`mcp__pencil__*` MCP wrapper** (D-01 Pencil arm) |
| Penboard | `.pb` JSON file parser | **`mcp__penboard__*` MCP wrapper** for live workspace (D-01 Penboard arm) |

**SPECS impact:** ❌ T1.1-T1.4 wrong — proposed CREATE new extractors. Must EXTEND existing handlers + ADD new MCP-based handlers alongside legacy file-based handlers.

**Recommended mapping:**
| Phase 15 task | Action | Files |
|---|---|---|
| T1.1 HTML | EXTEND `design-normalize-html.js` to also emit cheerio AST → `refs/<slug>.structural.json` | existing file |
| T1.2 PNG | REPLACE `handler_passthrough` with OCR+region pipeline (or add `handler_png_structural` and route PNG there for non-photo mockups) | existing + new handler |
| T1.3 Pencil MCP | NEW `handler_pencil_mcp` parallel to `handler_pencil_xml` (legacy retained); router prefers MCP if available, falls back to XML | new handler in design-normalize.py |
| T1.4 Penboard MCP | NEW `handler_penboard_mcp` parallel to `handler_penboard_render` (file parser retained); router auto-detects `.penboard` workspace dir vs `.pb` file | new handler |
| T1.5 router | EXTEND existing FORMAT_HANDLERS — add `.pen` (Pencil MCP), `.penboard` (Penboard MCP workspace), keep `.pb`/`.xml` legacy | existing dispatch |

---

## 4. UI-MAP infrastructure

**Existing files:**
- `.claude/scripts/generate-ui-map.mjs` — **1007 lines** — UI-MAP generation logic
- `.claude/commands/vg/_shared/templates/UI-MAP-template.md` — template for planner

**Action needed:** Read both files fully before extending. Likely need:
- ADD `--scope owner-wave-id=N` mode (D-12b subtree)
- ADD `--full-tree` mode (D-12e holistic)
- ADD `--format json` output for diff consumption
- VERIFY 5-field-per-node schema currently emitted (D-15) — if not, planner template + generator both need update

---

## 5. design-extract command (already exists)

**File:** `.claude/commands/vg/design-extract.md`

**SPECS impact:** ❌ T7.7 partially wrong — proposed CREATE new `vg/design-extract.md`. Must UPDATE existing instead.

---

## 6. events.db schema

**Tables:**
- `runs` — `run_id, command, phase, args, started_at, completed_at, outcome, session_id, git_sha`
- `events` — `id, run_id, ts, event_type, phase, command, step, actor, outcome, payload_json, prev_hash, this_hash` (chained hash for tamper-evidence)

**Indexes:** `run_id, event_type, phase, command`

**Helper:** likely `emit-event` script (need to find — not yet inspected)

**SPECS impact:** ✅ Telemetry events list (SPECS §6) compatible — events.db can ingest `event_type` strings as-is. T9.1 query simply uses SQL on this schema.

---

## 7. Other existing infra worth noting

- `.claude/scripts/verify-ui-structure.py` — possible ancestor of UI-MAP / structural validator. Inspect.
- `.claude/scripts/validators/` — 30+ existing validator scripts. Many follow `verify-*.py` naming, dispatch via `dispatch-manifest.json`. Wave 3 must register new validators in `dispatch-manifest.json` + `registry.yaml`.
- `.claude/scripts/visual-diff.py` — possible ancestor of holistic drift gate. Inspect.
- `.claude/scripts/vg-orchestrator/` — orchestrator code. Step ordering/firing lives here, not in skill body alone.

---

## 8. vg.config.md (56KB existing)

**Confirmed sections** (from header grep):
- Project Identity
- Profile (web-fullstack | web-frontend-only | web-backend-only | cli-tool | library)
- Multi-Surface Project (v1.10.0 R4) — surfaces map (api/web/rtb/workers per surface with type/stack/paths/scanner_mode/design role)

**Observation:** Config is rich, multi-surface aware. Phase 15 additions (`mcp.servers.pencil`, `mcp.servers.penboard`, `design_fidelity`, `design_extractor`) must integrate cleanly with existing structure — likely append as new top-level sections.

**SPECS impact:** ✅ T0.2 directionally correct — append new sections. Just need to confirm no naming collisions with existing 56KB content.

---

## 9. Skill body sizes (planning impact)

- `review.md` — **4730 lines** (huge!)
- `blueprint.md` — 2904 lines
- `accept.md` — 2018 lines
- `build.md` — 3270 lines
- `scope.md` — 1129 lines

**Implication:** Skill updates (Wave 7) are surgical inserts/edits, not rewrites. Each task in Wave 7 may take longer than estimated (2-3h each) due to navigating large files + maintaining surrounding context. Re-estimate Wave 7 from 12h → **18-24h**.

---

## 10. Required BLUEPRINT revisions

### Wave 0 — REWORK
- T0.1: change deliverable to JSON Schema draft-07 (4 files, `*.v1.json`)
- T0.2: keep, just verify no collisions
- T0.3: change to flat-key additions (e.g., `uat_entry_label`, `uat_role_label`, ...)

### Wave 1 — REWORK heavily
- T1.1-T1.4: EXTEND existing `design-normalize.py` + `design-normalize-html.js`, NOT create new files
- ADD new handlers: `handler_pencil_mcp`, `handler_penboard_mcp`, optionally `handler_png_structural`
- T1.5: extend FORMAT_HANDLERS map
- Estimate adjustment: 24h → **18h** (reuse 80% existing scaffolding) — actually could be FASTER

### Wave 4 — REQUIRES READ FIRST
- T4.1: read existing 1007-line `generate-ui-map.mjs` BEFORE estimating extension work
- May discover: 5-field schema already partially enforced; subtree mode may need refactor or addition

### Wave 7 — UPSCALE estimate
- 12h → 18-24h due to skill body sizes (especially review.md @ 4730 lines)
- T7.7: 1 of 2 commands (design-extract.md) already exists → UPDATE not CREATE

### D-18 (UAT strings) — REWORK validator
- Forward check regex pattern: `\{\{(uat_[a-z_]+)\}\}` (flat keys), not `\{\{narration\.uat\.([a-z_]+)\}\}`
- Backward regex unchanged (literal Vietnamese/English text catch)

### Telemetry — VERIFY emit-event helper
- Check existing `emit-event` script API → match SPECS event names + payloads to existing helper signature

---

## 11. Recommended next actions (in order)

1. ✅ Document audit (this file)
2. Read 4 critical files BEFORE blueprint revision:
   - Full `generate-ui-map.mjs` (1007 lines)
   - Existing `design-extract.md` skill
   - `validators/registry.yaml` + `dispatch-manifest.json`
   - `emit-event` helper script (find via grep)
3. Inspect 2 ancestor validators to avoid duplication:
   - `verify-ui-structure.py`
   - `visual-diff.py`
4. Sample query events.db to confirm 7.14.3 abort sequence (T9.1 in parallel)
5. Revise BLUEPRINT v2 with:
   - Corrected file paths (JSON schemas, flat narration keys)
   - EXTEND-not-CREATE language for extractors
   - Updated estimates (Wave 1 ↓, Wave 7 ↑)
   - Delete redundant tasks (T7.7 design-extract creation → consolidate as update)
6. Re-confirm with user before Wave 0 execution

---

## 12. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| `generate-ui-map.mjs` already implements something different from D-15 schema | HIGH | Read fully; if mismatch, decide: refactor existing OR add new generator alongside |
| `design-normalize.py` PenBoard handler logic is different from MCP-based approach (file vs live workspace) — may surface user expectations | MED | Keep both: legacy file + new MCP handlers; let user choose per project |
| Skill body line counts mean larger context loads per edit; risk of mis-edit | MED | Use Edit tool with high-context strings; commit per atomic edit; re-verify after each |
| Validator registry may have schema/naming convention requiring registration step we haven't planned | MED | Read `registry.yaml` + `dispatch-manifest.json` before adding 11 validators |
| `narration-i18n.md` t() helper may have specific key naming convention we'll violate | LOW | Inspect t() helper; align UAT key names |
| `emit-event` helper may not support arbitrary event_type — may require pre-registration | MED | Find + read emit-event source |

---

## 13. Decision points needing user input post-revision

1. **PenBoard handler split:** Keep legacy `.pb` file handler + add MCP handler, OR deprecate legacy?
2. **Pencil handler split:** Keep legacy `.xml` handler + add MCP handler, OR deprecate legacy?
3. **PNG OCR:** Apply OCR+region to ALL PNG (replace passthrough) OR only when `.structural.png` extension or marker file present (keep passthrough as default for photo screenshots)?
4. **UI-MAP generator strategy:** Refactor existing 1007-line `generate-ui-map.mjs` to support subtree+holistic modes, OR add new `diff-ui-map.mjs` while keeping existing as-is?

---

**END OF AUDIT — awaiting user input on §13 + lock for BLUEPRINT v2**
