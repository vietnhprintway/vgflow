# Phase 19 — Design Fidelity 95% — SPECS

**Version:** v1 (draft 2026-04-28)
**Total decisions:** 9 (D-01..D-09)
**Source:** ROADMAP-ENTRY.md (this folder)
**Critical reality check:** v2.13.0 4-layer + L-002 mandate đã đóng các gap blatant. Phase 19 đóng các gap second-order: thượng nguồn không decompose chi tiết view + hạ nguồn không verify AI thực sự đọc PNG.

---

## Existing infra audit (đọc trước khi sửa)

| Component | Hiện trạng | P19 action |
|---|---|---|
| `commands/vg/blueprint.md` step 2b6 (lines 1875-1948) | Spawn Sonnet đọc structural HTML/JSON + interactions + manifest → emit `UI-SPEC.md`. Không đọc `scans/{slug}.scan.json`. Không vision PNG. | EXTEND — D-01 add scan.json input; D-02 insert step 2b6c view-decomposition before 2b6. |
| `commands/vg/blueprint.md` step 4b (lines 705-808) | Validate manifest + design-refs slug exists. R4 grade for FE tasks without `<design-ref>`. | KEEP. |
| `commands/vg/build.md` step 9 | L1 hard-gate (PNG disk) + L2 fingerprint validator + L3 build-visual + ux-gates. | EXTEND — D-05 insert vision-self-verify after L3 (before mark_step). |
| `commands/vg/review.md` phase 2.5 sub-step 6e | L4 SSIM gate. | KEEP. |
| `commands/vg/accept.md` | UAT checklist. Override-debt check exists nhưng không filter kind=design-*. | EXTEND — D-06 add manual diff visual prompt; D-07 extend override-debt filter. |
| `scripts/validators/verify-override-debt-sla.py` | Track override-debt entries; SLA-based blocking. | EXTEND — D-07 add `--kind` filter + `--threshold` flag. |
| `.husky/commit-msg` (or equivalent) | Commit-msg hook. Currently rejects missing CONTEXT.md citation. | EXTEND — D-08 add design citation rule. |
| `commands/vg/_shared/rationalization-guard.md` | Pattern: zero-context Haiku adjudicate gate-skip. | REUSE — D-05 fork to `design-fidelity-guard.md`. |
| `commands/vg/_shared/lib/architect-prompt-template.md` | L2 architect proposes structural changes. v2.13.0 added vision injection rule. | KEEP. |
| `scripts/verify-build-visual.py` | L3 pixel-diff. Auto-SKIP when deps missing. | KEEP. |
| `scripts/validators/verify-layout-fingerprint.py` | L2 fingerprint sections check. | KEEP. |
| `scripts/validators/verify-design-ref-coverage.py` | Planner-side FE task coverage. | KEEP. |
| `scripts/validators/registry.yaml` | Validator catalog. | EXTEND — D-05 register `design-fidelity-guard`; D-07 register `design-override-debt`. |

**Critical implication:** Phase 19 = 1 new step trong blueprint (D-02), 1 new validator script (D-05), 1 new step trong build.md (D-05 wire), 1 new step trong accept.md (D-06+D-07), 1 hook extension (D-08), 1 cross-AI script (D-03), 1 planner extension (D-04), 1 research spike (D-09). Total ~600 LOC across 8-10 commits.

---

## D-01 — Consume `scan.json` vào blueprint UI-SPEC

**Problem:** Layer 2 Haiku design-extract sinh `${DESIGN_OUT}/scans/{slug}.scan.json` với fields `modals_discovered, forms_discovered, tabs_discovered, warnings`. Step 2b6 UI-SPEC generator hiện tại **không đọc** file này → bỏ phí spend đã có và information sẵn về components.

**Decision:** UI-SPEC agent prompt thêm input `scans/{slug}.scan.json` cho mỗi `<design-ref>` slug. Agent rules updated:
- Treat scan.json `modals_discovered` as authoritative — must enumerate trong UI-SPEC.md "Modals" section.
- Treat scan.json `forms_discovered` as authoritative — must enumerate trong UI-SPEC.md "Forms" section.
- Treat scan.json `tabs_discovered` — surface trong "Per-Page Layout" section.

**File changes:**
- `commands/vg/blueprint.md` step 2b6 (lines ~1882-1947): add `scans/{slug}.scan.json` to agent input list; update prompt RULES with scan.json consumption.

**Validation:** existing UI-SPEC checker (no current validator — add lightweight regex check for `## Modals` and `## Forms` sections when scan.json non-empty).

**Effort:** 1-2h. ~30 LOC change in blueprint.md + ~20 LOC new validator stub.

**Risk:** LOW. Add-only input; existing UI-SPEC consumers (executor step 8c) đọc UI-SPEC text — output shape backward-compatible.

---

## D-02 — Vision view-decomposition step 2b6c

**Problem:** Hiện tại blueprint chỉ thấy DOM tree (HTML asset) hoặc box-list (PNG/Pencil/Penboard asset). Không có step nào ép AI **vision-Read PNG** để emit canonical component list per view. Hệ quả: PLAN tasks ở mức "page" không "component"; executor scope quá rộng → drift.

**Decision:** Insert new step `2b6c_view_decomposition` BEFORE step 2b6 UI-SPEC (so UI-SPEC consumes view decomposition output).

**Process:**
1. Foreach `<design-ref>` slug trong PLAN với form A:
   - Spawn `Task(subagent_type="general-purpose", model="claude-opus-4-7")` (vision-capable)
   - Inject Read tool ALLOW + abs path to PNG + abs path to structural.json/html
   - Prompt: "Read the PNG. Read the structural ref. Output JSON listing every distinct visual region/component with schema: `{name, type, parent_region, position_pct (x,y,w,h relative to viewport), child_count, evidence_pixel_region}`. Use semantic names (Sidebar, TopBar, KPICard, NavigationItem) — never `<div>` or `Container`. Minimum 3 components, no maximum."
   - Agent writes to `${PHASE_DIR}/.tmp/view-{slug}.json`
2. Aggregate: orchestrator merge all `view-{slug}.json` → `${PHASE_DIR}/VIEW-COMPONENTS.md` (table format, 1 row/component, columns: slug, name, type, parent, position, children).

**Validation:** new validator `verify-view-decomposition.py`:
- For each slug có file `.tmp/view-{slug}.json`: ≥3 components, no component name in {`div`, `Container`, `Wrapper`, `Section` alone}, every component has non-zero position_pct.
- BLOCK on violation (override `--skip-view-decomposition`).

**Output schema** (`${PHASE_DIR}/VIEW-COMPONENTS.md`):
```markdown
# View Components — Phase 19

## home-dashboard
| Component | Type | Parent | Position (x,y,w,h%) | Children |
|---|---|---|---|---|
| AppShell | layout | (root) | 0,0,100,100 | 3 |
| Sidebar | navigation | AppShell | 0,0,15,100 | 8 |
| TopBar | navigation | AppShell | 15,0,85,5 | 4 |
| MainContent | content | AppShell | 15,5,85,95 | 2 |
| QuickActionsGrid | grid | MainContent | 17,8,81,30 | 4 |
| GettingStartedPanel | card | MainContent | 17,40,81,40 | 1 |
```

**File changes:**
- `commands/vg/blueprint.md`: insert new `<step name="2b6c_view_decomposition">` block between `2b6_ui_spec` and `2b7`; ~80 LOC.
- `scripts/validators/verify-view-decomposition.py` new ~120 LOC.
- `scripts/validators/registry.yaml`: register validator entry severity=block, domain=artifact.

**Effort:** 4-6h. Includes prompt design + smoke test trên 2-3 PNG fixtures.

**Risk:** MEDIUM. Vision-spawn cost (Opus tokens per slug, ~$0.05-0.10/slug). Mitigation: gate behind config `design_assets.view_decomposition.enabled` (default false trong Wave B; flip true sau dogfood).

---

## D-03 — Cross-AI gap-hunt cho VIEW-COMPONENTS

**Problem:** D-02 vision agent có thể miss component (background overlay, sticky FAB, footer divider). Cùng-model self-review echo chamber — đã proven critical (rationalization-guard finding).

**Decision:** Spawn second pass với **different model** (Codex, Gemini, hoặc Haiku tùy `vg.config.crossai_clis`):
- Input: `view-{slug}.json` từ D-02 + same PNG.
- Prompt: "List of components AI A claimed. Read the PNG. Find components AI A missed OR mis-categorized. Output: `{missed: [{name, position}], misnamed: [{old_name, new_name, reason}]}`."
- If gap-hunter `missed` non-empty → re-spawn D-02 với gap reminder; max 2 iterations.

**File changes:**
- `commands/vg/blueprint.md` step 2b6c: add gap-hunt sub-step.
- Reuse `commands/vg/_shared/crossai-invoke.md` for cross-AI invocation.
- New skill stub `.claude/skills/vg-view-decomp-gap-hunter/SKILL.md` mirroring `vg-design-gap-hunter`.

**Effort:** 1-2h.

**Risk:** LOW. Pattern proven trong design-extract Layer 3.

---

## D-04 — Re-emit fine-grained PLAN từ VIEW-COMPONENTS

**Problem:** Có VIEW-COMPONENTS.md rồi nhưng PLAN vẫn 1 task = 1 page. Executor scope rộng = drift. Cần planner emit task per component (hoặc cluster components nhỏ).

**Decision:** Planner step (sau view-decomposition) re-evaluate task list:
- For each VIEW-COMPONENTS row với `child_count >= 3` OR `position area >= 20% viewport`: emit dedicated task with scope = component subtree.
- Wave grouping by parent dependency: AppShell → Sidebar+TopBar (parallel) → MainContent → cards/sections.
- New task schema field `<component-scope>{ComponentName}</component-scope>` for scope precision.

**File changes:**
- `commands/vg/_shared/vg-planner-rules.md`: extend Rule 4 (LOC budget) and add Rule 9 (component-scope).
- `commands/vg/blueprint.md`: planner agent prompt updated with VIEW-COMPONENTS as authoritative input.
- `commands/vg/_shared/vg-executor-rules.md`: executor scope check now reads `<component-scope>` and refuses to touch siblings outside scope.

**Effort:** 4-6h.

**Risk:** HIGH. Changes planner output shape — existing PLAN fixtures + downstream test specs may break. Mitigation: feature flag `planner.fine_grained_components: false` (default) trong v2.14.0; turn on for opt-in projects.

---

## D-05 — Vision-self-verify (Lớp 5) post-task

**Problem:** L1-L4 enforce structure (file exists, fingerprint sections present, pixel diff threshold). Không có gate kiểm **AI có hiểu PNG không** ở semantic level. AI có thể bịa fingerprint, ship pixel-close-enough code mà miss component composition.

**Decision:** New validator `design-fidelity-guard` chạy post-executor-commit, pre-wave-end. Pattern: spawn fresh **Haiku** subagent zero-context với:
- Diff của task (commit show)
- PNG baseline đính kèm dạng image (Read tool)
- VIEW-COMPONENTS.md row cho slug (ground truth components)

**Prompt** (single line, structured output):
```
Compare commit diff vs PNG. Are all components in VIEW-COMPONENTS expected for this slug present in code (by JSX tag, className, or ARIA role)? Output single-line JSON: {"verdict":"PASS"|"FLAG"|"BLOCK","missing_components":[],"reasoning":"<= 200 chars"}.
PASS = all expected components present.
FLAG = 1-2 minor missing (acceptable but logged).
BLOCK = ≥3 missing or core component (Sidebar/TopBar/MainContent) missing.
```

Validator interprets:
- BLOCK → fail wave gate (override `--allow-vision-self-verify-fail`).
- FLAG → log to override-debt kind=design-fidelity-flag, continue.
- PASS → continue.

**File changes:**
- `scripts/validators/verify-vision-self-verify.py` new ~150 LOC. Reuses `crossai-invoke.sh` for spawn.
- `commands/vg/_shared/design-fidelity-guard.md` new ~80 LOC (mirror rationalization-guard structure).
- `commands/vg/build.md` step 9: insert validator call after L3, before mark_step. ~20 LOC.
- `scripts/validators/registry.yaml`: register entry severity=block, domain=behavior.

**Effort:** 3-4h.

**Risk:** MEDIUM. Haiku spawn cost ~$0.001/task; reasonable. Risk: false positives if VIEW-COMPONENTS quá detail (D-02 phải ổn trước). Mitigation: gate behind config `visual_checks.vision_self_verify.enabled`.

---

## D-06 — Manual UAT visual check ở `/vg:accept`

**Problem:** L1-L5 are AI-driven. Final layer cần human-in-loop để catch semantic miss mà no AI gate detects.

**Decision:** `/vg:accept` UAT checklist thêm step interactive:
- For each slug có file `${PHASE_DIR}/visual-fidelity/{slug}.diff.png` (sinh by L4 hoặc L3):
  - Print path tới {current.png, baseline.png, diff.png} (3 file side-by-side cho user mở).
  - `AskUserQuestion`: "Open the 3 files. Is this drift acceptable? [y/N]"
  - N → reject phase, return to /vg:build with override-debt entry kind=human-rejected-design.
  - y → continue.
- Skip if no diff PNG produced (L4 didn't run or all PASS).

**File changes:**
- `commands/vg/accept.md`: insert sub-step "design-uat" trước final mark_step.

**Effort:** 1h.

**Risk:** LOW. Pure interactive prompt; AI cannot bypass. Concern: tiresome for many slugs — mitigate by only prompting slugs có drift > 1% (skip near-perfect matches).

---

## D-07 — Override-debt threshold gate ở `/vg:accept`

**Problem:** v2.13.0 4-layer gates có override flags log to override-debt nhưng không block /vg:accept. AI có thể stack 5 overrides + accept silently.

**Decision:** Extend existing `verify-override-debt-sla.py` với `--kind` filter và `--threshold` flag. Add `/vg:accept` step calling:
```bash
verify-override-debt-sla.py \
  --phase-dir "$PHASE_DIR" \
  --kind 'design-*' \
  --threshold 2 \
  --status unresolved
```
Exit 1 nếu ≥2 unresolved kind=design-* entries → BLOCK accept với guidance "Run /vg:override-resolve trước".

**File changes:**
- `scripts/validators/verify-override-debt-sla.py`: add `--kind` glob filter + `--threshold` arg. ~30 LOC.
- `commands/vg/accept.md`: add validator call. ~15 LOC.
- `scripts/validators/registry.yaml`: severity=block, domain=process.

**Effort:** 1-2h.

**Risk:** LOW. Add-only filter; existing callers don't pass `--kind` → backward compatible.

---

## D-08 — Pre-commit hook bắt citation

**Problem:** PR #15 mandate `Per design/{slug}.png` citation trong commit body cho UI files; reality: chỉ là convention, không hard-enforce.

**Decision:** Native git `commit-msg` hook (extend existing if any, else create):
- For each file in `git diff --cached --name-only` matching FE pattern (apps/{admin,merchant,vendor,web}/.{tsx,jsx,vue,svelte} | packages/ui/src/{components,theme}/.{tsx,jsx,vue,svelte}):
  - Commit message body MUST contain `Per design/{slug}.png` (where {slug} matches `[a-z0-9][a-z0-9_-]+`) OR `Design: no-asset \([^)]+\)`.
  - Else exit 1 với message: "FE file {path} requires design citation in commit body."

**Implementation:** `commands/vg/_shared/lib/commit-msg-design-citation.sh` — 60 LOC bash. Wired into install.sh hook installer.

**File changes:**
- New `commands/vg/_shared/lib/commit-msg-design-citation.sh`.
- `install.sh`: append source line to project's `.husky/commit-msg` or `.git/hooks/commit-msg`.

**Effort:** 2h.

**Risk:** LOW-MED. False positives possible for refactor commits không touch design (rename only). Mitigation: skip if diff is pure rename (`git diff --cached --diff-filter=R`) hoặc allow `Design: refactor-only` opt-out.

---

## D-09 — Read-tool transcript verification (research)

**Problem:** Strongest possible proof = capture executor agent transcript, parse JSON xem có `tool_use Read(PNG_PATH)` thực sự diễn ra không. Hiện chưa khả thi without Claude Code runtime hooks.

**Decision:** Research spike. Output: `RESEARCH.md` documenting:
- What runtime hooks Claude Code expose (SubagentStop hook? Transcript stream API?).
- Feasibility of parsing structured tool_use events from subagent.
- If feasible: prototype `verify-read-tool-transcript.py` — read transcript, regex `Read.*{slug}\\.png`, BLOCK if missing.
- If infeasible: document "best we can do" alternatives (e.g., require executor commit a sentinel `.read-evidence/{task}.json` after Read call).

**File changes:**
- `dev-phases/19-design-fidelity-95-pct-v1/RESEARCH.md` new doc.
- Stub `scripts/validators/verify-read-tool-transcript.py` if prototype works.

**Effort:** 3-5h research + prototype.

**Risk:** HIGH. May land "infeasible — recommend alternative" outcome. That's still valuable (closes question).

---

## Acceptance criteria (rolled up từ ROADMAP-ENTRY)

Smoke test fixtures cần có trong `dev-phases/19-design-fidelity-95-pct-v1/fixtures/`:

1. **PNG complex 5+ components** — fixture phase với 1 design PNG có Sidebar+TopBar+3 cards. Run blueprint → expect ≥5 component tasks emit (D-04 active).
2. **Deliberately-wrong UI** — pre-commit fixture: ship `<main className="flex">` với HomeDashboard.png as design-ref. D-05 vision-self-verify must BLOCK.
3. **3 unresolved design overrides** — phase với 3 override-debt entries kind=design-skip-pixel-gate. D-07 must BLOCK accept.
4. **UI commit no citation** — git commit `apps/admin/src/Page.tsx` với message thiếu `Per design/...png`. D-08 hook must reject.
5. **Manual UAT reject** — D-06 prompt user; mock user input "N" → accept blocked với override-debt logged.

End-to-end: dogfood 2 phases trước/sau Phase 19, đo design-drift incidents (manual count). Target: <5%.

## Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| D-02 Opus vision spawn cost balloons | MED | MED | Config gate default OFF; per-slug budget cap; cache view-{slug}.json by PNG hash. |
| D-04 fine-grained planner breaks existing fixtures | HIGH | HIGH | Feature flag default OFF; opt-in via vg.config; ship as v2.14.0 minor bump. |
| D-05 false positives BLOCK valid builds | MED | HIGH | Override flag + override-debt log; tune VIEW-COMPONENTS schema first (D-02). |
| D-09 Claude Code runtime không expose transcript | HIGH | LOW | Document infeasibility + sentinel-file fallback. |
| Combined cost (Opus + Haiku spawns) per phase | MED | MED | All vision steps gated behind config; default conservative; user opt-in. |

## Open questions

1. Threshold cho D-05 vision-self-verify "BLOCK if ≥3 missing" — calibrate trên fixtures Wave A trước commit.
2. D-06 manual UAT — prompt timing: per-slug (loop) hay batch summary table? Lean batch để giảm fatigue.
3. D-04 component scope — task LOC budget khi component nhỏ (Button = 50 LOC). Cần new lower-bound, không chỉ upper.
4. Should D-08 hook also enforce on `<file-path>` matches từ PLAN, or chỉ git diff filename? File-path match safer (catches typo paths).
