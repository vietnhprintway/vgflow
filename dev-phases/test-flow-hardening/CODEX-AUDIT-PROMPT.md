# Codex Audit — B65/B66/B67 Test Flow Hardening Plan

You are adversarial reviewer auditing implementation plan BEFORE coding. Find blind spots, schema risks, scope creep, false-positive validators, prompt drift, missing edge cases. Be ruthless.

## Context — 3 prior audit reports

User asked: "check flow test xem đã tuân thủ đúng kiến trúc, chạy đầy đủ những gì cần thiết của 1 tester pro khi đã được cung cấp đầy đủ tài liệu từ test-specs chưa, fix-loop thực sự đã ổn chưa".

3 parallel Explore agents found:

**Audit A — /vg:test entry**
- Architecture ✓ (codegen properly separated to /vg:test-spec)
- 7 pro-tester gaps: no parallel execution, no flaky retry, no visual regression, no axe-core at runtime, no resume-from-failure, no cross-artifact consistency check, no pre-execution fixture audit

**Audit B — codegen depth**
- Structurally deep (11-stage FEATURE_CHAIN_STAGES + 8-stage READONLY_STAGES + 4-layer mutation verify)
- CRITICAL GAPS:
  1. `commands/vg/_shared/test/codegen/delegation.md` does NOT mention `chain_steps[]` — B62 added field but codegen uses static 11-stage formula, doesn't iterate per chain_step
  2. `cross_view_propagation_observations[]` NOT in delegation.md inputs — B63 emits data but codegen blind to it
  3. No min-line/min-assertion per spec contract

**Audit C — fix-loop**
- NOT SOLID — 7 red flags:
  1. No pre-fix flaky detection
  2. Fixer prompt lacks goal intent context (TEST-GOALS goal text)
  3. No cross-phase regression detection (ripple = current phase only)
  4. Convergence "stability" vague (2-iter no-new-errors)
  5. Ripple depends on optional graphify, fallback git diff misses indirect
  6. Root-cause classification prose-only (no code-backed classifier)
  7. No `--retry-only` mode

## Proposed plan — B65 + B66 + B67

### B65 — Codegen consumes B62/B63 outputs (HIGH priority)

**Modify:**
- `commands/vg/_shared/test/codegen/delegation.md`:
  - Add `@${PHASE_DIR}/EDGE-CASES/VARIANTS.json` chain_steps field references
  - Add `@${PHASE_DIR}/scan-*.json cross_view_propagation_observations` to inputs
  - New `<feature_chain_emission>` section: when goal_class=feature_chain, emit one `test()` per chain_step (NOT just one for entire chain). Each test() asserts target_view_class transitions + downstream_effects per step.
  - New `<cross_view_assertion>` section: for each observed cross_view propagation, emit specific assertion `await navigate(target_view); expect(entity_id).toBeVisible()`.

- `scripts/validators/verify-deep-test-specs.py`:
  - Add min_assertions per feature_chain spec = chain_steps.length × 2
  - Add cross_view assertion presence check when scan has observations
  - Add `--strict-feature-chain` flag

- `scripts/generate-deep-test-specs.py`:
  - For feature_chain goals: expand chain_steps[] into per-step test() entries in PLAYWRIGHT-SPEC-PLAN.md

**Tests:** `tests/test_batch65_codegen_chain_consumption.py` (~12 tests)
- Delegation prompt has chain_steps emission instruction
- Delegation has cross_view_assertion instruction
- generate-deep-test-specs expands chain_steps per goal
- Validator min_assertions formula
- Mirror parity

### B66 — Fix-loop hardening (HIGH priority)

**Modify:**
- `commands/vg/_shared/test/fix-loop-and-verdict.md`:
  - Add STEP 0_flaky_pre_check (BEFORE iter 1): auto-retry failing tests 3x. If 1+ pass → mark flaky, quarantine to `KNOWN-FLAKY.json`, skip fix-loop for that spec
  - Enrich fixer prompt (line ~228-258) with TEST-GOALS goal text (read goal_id from finding → vg-load goal slice → append to fix prompt as `<goal_intent>` block)
  - Add cross-phase regression scan: after each iteration's fix commit, grep dependent phases (P{N+1}, P{N+2}) for references to changed files; if found, run their test gate with --dry-run
  - Tighten convergence: 3 consecutive iterations no-new-errors (not 2)
  - Add `--retry-only` mode flag: skip classify+fix, just retry once + report

**New scripts:**
- `scripts/classify-test-failure.py`: code-backed classifier reading test output + stack trace + console + network → emits {class: CODE_BUG|INFRA_ISSUE|SPEC_GAP|PRE_EXISTING|FLAKY, confidence: 0-1.0}
- `scripts/validators/verify-fix-targets-goal.py`: meta-check that fix commit message references finding_id AND diff touches files in finding evidence (overlap with vg-review-qa-checker but at fix-time, not post)

**Tests:** `tests/test_batch66_fix_loop_hardening.py` (~15 tests)
- Flaky pre-check skips fix when retry passes
- Fixer prompt includes goal intent
- Classifier output schema valid
- Cross-phase grep + dry-run
- --retry-only mode works

### B67 — Pre-execution fixture audit + cross-artifact consistency (MEDIUM)

**Modify:**
- `commands/vg/_shared/test/preflight.md`:
  - Add cross-artifact consistency gate (every goal_id has: variant in VARIANTS.json, recipe in SEED-RECIPE.md, case in helper stub, spec in CODEGEN-MANIFEST). BLOCK on shortfall.
  - Add runtime fixture audit: dev-server health + seed data presence (probe API endpoints from API-CONTRACTS) + Playwright browser readiness
  - Emit telemetry `test.preflight_blocked` per gate

**New script:**
- `scripts/validators/verify-test-artifact-consistency.py`: cross-check goal_id presence across 4 artifacts

**Tests:** `tests/test_batch67_preflight_consistency.py` (~10 tests)
- Cross-artifact validator pass/fail
- Preflight blocks on inconsistency
- Dev-server probe pass/fail
- Seed-data probe pass/fail

## Audit instructions

Read critical files first:
- `commands/vg/_shared/test/codegen/delegation.md` (current codegen contract)
- `commands/vg/_shared/test/fix-loop-and-verdict.md` (current fix-loop)
- `commands/vg/_shared/test/preflight.md` (current preflight)
- `scripts/generate-deep-test-specs.py` (codegen plan generator)
- `scripts/generate-lifecycle-specs.py` lines 67-104 (FEATURE_CHAIN_STAGES + dispatch)
- `commands/vg/_shared/templates/TEST-GOAL-enriched-template.md` lines 154+ (chain_steps schema)

Then identify:

1. **Schema collisions**: chain_steps emit vs existing test.each(variants) — same goal would have 2 layers of variants?
2. **Cost explosion**: feature_chain goal with 8 chain_steps × 4 negative_specs variants = 32 test() per goal. Acceptable?
3. **AI prompt overload**: delegation.md already huge. Adding chain_steps + cross_view sections may dilute existing rules.
4. **Validator over-strictness**: min_assertions = chain_steps × 2 — could BLOCK legitimate phases where some steps are pure navigation.
5. **Flaky detection in CI**: auto-retry 3x adds 3× cost. Worth it? Or only on suspected-flaky tags?
6. **Cross-phase ripple**: grep for references in P{N+1} — false positives high (variable name collisions). Need exact symbol match?
7. **Classifier accuracy**: heuristic-based classifier may misclassify INFRA_ISSUE as CODE_BUG. False-positive cost vs benefit?
8. **B67 dev-server probe**: probing every API-CONTRACTS endpoint at preflight = slow. Smoke subset only?
9. **Pre-existing batches affected**: B62 + B63 + B64 may need backfill if codegen contract changes shape
10. **Migration path for legacy specs**: pre-B65 generated specs lack chain_step coverage. Re-gen or skip?

## Output

Write `dev-phases/test-flow-hardening/CODEX-AUDIT.md`:

```
# Codex Audit — B65/B66/B67 Test Flow Hardening

**Verdict:** PASS | PASS-WITH-NOTES | BLOCK

## BLOCKER findings (must fix before B65 starts)

## MAJOR concerns (fix before merge)

## MINOR concerns (note + proceed)

## Recommended adjustments

## Checklist
| Concern | Status |
|---|---|
| Schema collision (test.each + chain_steps) | OK/RISK/BLOCK |
| Cost explosion (32 test/goal) | ... |
| Prompt overload | ... |
| Validator over-strict | ... |
| Flaky detection CI cost | ... |
| Cross-phase ripple FP rate | ... |
| Classifier accuracy | ... |
| Preflight probe speed | ... |
| Legacy phase migration | ... |
```

Be specific. File paths + line numbers. Quote actual fragments. No hedging. ≤ 1500 words.
