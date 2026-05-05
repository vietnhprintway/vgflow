# CrossAI Multi-Stage Multi-Primary Design

**Date:** 2026-05-06
**Status:** Approved (operator: sếp Dũng)
**Brainstorm session:** 26 decisions across architecture, gating, runtime selection, consensus protocol, rollout
**Predecessor:** `docs/audits/2026-05-05-gemini-fit-report.md`

---

## Goal (one sentence)

Extend CrossAI semantic review to scope + blueprint stages (currently build-only), upgrade build CrossAI to dual-primary consensus (Gemini Pro 1M + Codex GPT-5.5 in parallel, Claude Sonnet adjudicates), with operator-controlled gating policy that exempts trivially-small phases.

## Architecture (3 sentences)

`crossai_clis` registry in `vg.config.md` declares CLI invokers (model + command + role). `crossai_stages` map binds each stage (scope/blueprint/build) to primary CLIs (parallel) + verifier CLI (sequential). Library `scripts/lib/crossai_loop.py` runs the orchestration; per-stage thin wrappers (`vg-{scope,blueprint,build}-crossai-loop.py`) define brief packers; slim entries dispatch via env var; per-run `--crossai-primary=...` / `--crossai-verifier=...` flags allow ad-hoc override.

## Tech Stack

- Python 3.12+ (orchestrator + wrappers + library)
- Bash (slim entry hook glue)
- YAML-ish parsing for `vg.config.md` (shared with existing `crossai_skip_validation.py`)
- SQLite events.db (telemetry)
- Subprocess invocation for Gemini/Codex/Claude CLIs

---

## 26 Decisions Reference (verbose)

### Block 1 — Sequence + scope

- **Q1 = E** — Implementation order: M1 infrastructure → M2 gating policy → M3 multi-primary CrossAI

### Block 2 — Gating policy

- **Q2 = F + profile-aware** — `vg.config.md` `crossai.policy: strict|auto|off` with profile-mapped defaults (scaffold/migration → off, library/cli-tool → auto, web-* → strict)
- **Q3 = A** — `auto` mode heuristic detect (≤3 endpoints + ≤2 critical goals + ≤5 plan tasks) → block-then-prompt AskUserQuestion (skip / run anyway)
- **Q4 = C** — `auto` mode 2 exemptions (phase nhỏ HOẶC CLI vắng); `strict` mode 1 exemption (CLI vắng)
- **Q23 = D** — Thresholds configurable in `vg.config.md`, default 3/2/5 (AND logic)

### Block 3 — Runtime selection

- **Q5 = D** — Project-level default + per-run flag override + AskUserQuestion only on missing/invalid
- **Q6 = C** — Extend `crossai_clis` registry with `role` field; reference by name
- **Q7 = D** — `crossai_stages` map stage → primary_clis + verifier_cli (operator-pick per stage)
- **Q17 = D** — Slim entry `--crossai-cli=...` flag + `VG_CROSSAI_OVERRIDE_CLI` env fallback
- **Q18 = C** — Per-role flags `--crossai-primary=A,B --crossai-verifier=Z`; alias `--crossai-cli=X` = primary

### Block 4 — Multi-CLI consensus pattern

- **Q9-modified** — Cả Gemini và Codex làm primary tổng hợp song song (cho 3 stages: scope/blueprint/build); Sonnet làm verifier critic
- **Q10 = B** — Sonnet adjudicate disagreements với targeted file read; 2v1 consensus; tie → escalate operator (AskUserQuestion)

### Block 5 — Brief inject

- **Q8 = B** — Full brief 1M-context inject (Gemini Pro fits unbounded; Codex capped 150K)
- **Q13 = C** — Codex split brief 2-pass khi >150K tokens combined (chunk 1 + chunk 2 ~100K each)
- **Q14 = C** — Sonnet adjudicate merges 2-pass + dedupes findings + cross-validates Gemini findings

### Block 6 — Iteration + evidence

- **Q11 = A** — Max 5 iterations; sau iter 5 BLOCK → AskUserQuestion (continue/defer/skip+debt)
- **Q12 = A** — Inline `findings.json` schema extension: add `verifier_verdict` + `verifier_evidence` per finding (backwards-compatible additive)

### Block 7 — Code structure

- **Q15 = C** — Library `scripts/lib/crossai_loop.py` + thin wrappers per stage; refactor existing `vg-build-crossai-loop.py`
- **Q16 = A** — Rename `crossai_skip_validation.py` → `crossai_config.py`; extend with `resolve_stage_config()`

### Block 8 — UX + telemetry

- **Q19 = B** — TodoWrite parent + 3 fixed subtasks per iteration (2 primary + 1 verifier); rebuild children when iter advances
- **Q20 = D** — Per-stage namespace events (`scope.crossai_*`, `blueprint.crossai_*`, `build.crossai_*`) + `crossai.disagreement_detected` event

### Block 9 — Project init + migration

- **Q21 = D** — `/vg:project --init` auto-detect (which X check + profile scan) + sensible defaults + opt-out via edit
- **Q22 = D** — Lazy migrate at first CrossAI invocation; emit `crossai.config_migrated` telemetry event

### Block 10 — Rollout + monitoring

- **Q24 = B** — Phased rollout 3 milestones (M1 infra, M2 gating, M3 multi-primary)
- **Q25 = A** — Additive event payload fields, no event name version bump
- **Q26 = C** — Extend `/vg:health` with CrossAI section (single source of truth)

---

## Components (per milestone)

### M1 — Infrastructure (no behavior change)

**Goal:** schema, registry, library, init wizard, lazy migrate. Existing build CrossAI behavior unchanged.

**Files:**

| File | Type | Purpose |
|---|---|---|
| `scripts/lib/crossai_config.py` | RENAME from `crossai_skip_validation.py` + EXTEND | Add `resolve_stage_config(stage, repo_root) -> StageConfig`; keep existing `validate_skip_legitimate()`. Schema: `StageConfig(primary_clis: list[CLISpec], verifier_cli: CLISpec, ...)`. |
| `scripts/lib/crossai_loop.py` | NEW | Common loop orchestration: `run_loop(phase, iteration, brief_packer, stage_config) -> int`. Invokes parallel primaries, sequential verifier, writes findings.json. |
| `scripts/vg-build-crossai-loop.py` | REFACTOR | Thin wrapper. Define `pack_review_brief()` for build stage. Import `crossai_loop.run_loop()`. Existing CLI signature preserved (test compat). |
| `scripts/vg-scope-crossai-loop.py` | NEW | Thin wrapper for scope stage. `pack_review_brief()` injects SPECS+CONTEXT (Q8=B full body). |
| `scripts/vg-blueprint-crossai-loop.py` | NEW | Thin wrapper for blueprint stage. `pack_review_brief()` injects PLAN+CONTRACTS+TEST-GOALS+CONTEXT+CRUD-SURFACES+UI-MAP+WORKFLOW-SPECS+VIEW-COMPONENTS+BLOCK 5 FE-contracts (full body). |
| `scripts/vg-orchestrator/__main__.py` | EXTEND | Add `cmd_init_crossai_config(args)` for `/vg:project --init` integration: detect CLIs (`shutil.which()`), profile (read PROFILE.md), generate `vg.config.md` block. Add `cmd_migrate_crossai_config(args)` for lazy migration. |
| `vg.config.md` (template) | EXTEND | Add `crossai.policy`, `crossai.heuristic_thresholds`, `crossai_clis[].role`, `crossai_stages.{scope,blueprint,build}` blocks. |

**Tests:**
- `scripts/tests/test_crossai_config_resolve.py` — `resolve_stage_config()` reads + validates
- `scripts/tests/test_crossai_loop_library.py` — library `run_loop()` orchestration mock
- `scripts/tests/test_crossai_init_wizard.py` — `/vg:project --init` generates valid config
- `scripts/tests/test_crossai_lazy_migrate.py` — first invocation auto-migrates legacy config

**Acceptance:**
- Existing `vg-build-crossai-loop.py` tests pass unchanged (signature compat)
- New library importable, public API stable
- Project without `crossai.policy` runs build CrossAI as before (silent default)

---

### M2 — Gating policy (behavior change: `auto` mode active)

**Goal:** `crossai.policy` modes (strict/auto/off) + heuristic thresholds + AskUserQuestion gate.

**Files:**

| File | Type | Purpose |
|---|---|---|
| `scripts/lib/crossai_gating.py` | NEW | `evaluate_phase(phase, policy, thresholds) -> Decision` returns `RUN | SUGGEST_SKIP | EXEMPT_NO_CLI | EXEMPT_POLICY_OFF`. Heuristic: count endpoints/goals/tasks. |
| `scripts/validators/build-crossai-required.py` | EXTEND | Read `crossai.policy`. If `off` → silent PASS. If `auto` + heuristic-skip + operator-confirmed → PASS with `auto_skipped` event. If `strict` + override → fact-check (Q4=C). |
| `scripts/validators/scope-crossai-required.py` | NEW (clone build template) | Same gating logic for scope stage. |
| `scripts/validators/blueprint-crossai-required.py` | NEW (clone build template) | Same gating logic for blueprint stage. |
| `commands/vg/_shared/{scope,blueprint,build}/crossai-loop.md` | EXTEND | Add gating step before invocation: read policy → if `auto` + below threshold → AskUserQuestion 2 options (skip / run anyway). Store decision in `.vg/runs/<run_id>/crossai-gate-decision.json`. |
| `scripts/vg-orchestrator/__main__.py` | EXTEND | `cmd_override` for `skip-*-crossai*` flag — keep existing fact-check (Q4=C strict mode); add `auto_skip_recorded` event for auto-mode skip-confirmed path. |

**Tests:**
- `scripts/tests/test_crossai_gating_policy.py` — strict/auto/off mode behavior
- `scripts/tests/test_crossai_heuristic_thresholds.py` — boundary cases (3/2/5)
- `scripts/tests/test_crossai_auto_skip_blocks_validator.py` — auto-skip confirmed → validator passes silently

**Acceptance:**
- Setting `crossai.policy: off` in `vg.config.md` → CrossAI never runs (validator silent PASS)
- Setting `crossai.policy: auto` + phase below threshold → AskUserQuestion fires, operator confirms skip, validator passes
- Setting `crossai.policy: strict` (default for `feature` profile) → existing behavior + anti-rationalization gate

---

### M3 — Multi-primary CrossAI (consensus pattern, applies to scope/blueprint/build)

**Goal:** Gemini Pro 1M + Codex GPT-5.5 parallel primary; Claude Sonnet adjudicates disagreements; 2v1 consensus.

**Files:**

| File | Type | Purpose |
|---|---|---|
| `scripts/lib/crossai_loop.py` | EXTEND | Implement parallel primary invocation, Sonnet verifier sequential. Handle Codex 2-pass split (Q13=C) when input >150K. Sonnet merges + adjudicates (Q14=C). |
| `scripts/vg-{scope,blueprint,build}-crossai-loop.py` | EXTEND | `pack_review_brief()` returns full body for Gemini Pro; library handles Codex split if needed. |
| `commands/vg/_shared/{scope,blueprint,build}/crossai-loop.md` | EXTEND | TodoWrite pattern: parent "CrossAI iter N" + 3 children (Gemini-primary, Codex-primary, Sonnet-verifier). Rebuild children per iteration. |
| `schemas/findings.v2.schema.json` | NEW | Extend findings schema: per-finding `source` (gemini\|codex_p1\|codex_p2), `verifier_verdict` (agree\|reject\|inconclusive), `verifier_evidence`. |
| `scripts/validators/{scope,blueprint,build}-crossai-required.py` | EXTEND | Accept v2 findings schema; validate consensus rules (2v0 PASS, 1v1 + Sonnet rejected = downgrade, tie = escalate). |
| `scripts/lib/crossai_health.py` | NEW | Aggregate metrics for `/vg:health` integration: disagreement rate, CLI fail rate, iter distribution, cost estimate. |
| `commands/vg/health.md` | EXTEND | Add CrossAI section consuming `crossai_health` lib. |

**Tests:**
- `scripts/tests/test_crossai_multi_primary_parallel.py` — Gemini + Codex parallel invocation
- `scripts/tests/test_crossai_codex_split_2pass.py` — input >150K triggers 2-pass
- `scripts/tests/test_crossai_sonnet_adjudicate.py` — disagreement → Sonnet vote → 2v1 consensus
- `scripts/tests/test_crossai_findings_v2_schema.py` — schema validation
- `scripts/tests/test_crossai_health_section.py` — `/vg:health` output includes CrossAI metrics

**Acceptance:**
- Run `/vg:blueprint 4.x` on PV3 → blueprint CrossAI runs (Gemini + Codex parallel) → findings.json v2 produced
- Disagreement scenario → Sonnet adjudicate → consensus output traceable in `verifier_verdict` field
- `/vg:health` shows CrossAI section with last-run metrics
- Telemetry events: `{stage}.crossai_iteration_started` + `crossai.disagreement_detected` queryable via `vg-orchestrator query-events`

---

## Data Flow (M3 multi-primary)

```
1. Slim entry: /vg:blueprint 4.x → emit-tasklist → TodoWrite project tasklist
2. Slim entry reaches step "2d_crossai_review" (blueprint) or "11_crossai_build_verify_loop" (build)
3. Read crossai.policy + heuristic_thresholds from vg.config.md
4. Gating decision (M2):
   - off → emit auto_exempt event, skip
   - auto + below threshold → AskUserQuestion → if skip → emit auto_skipped event, skip
   - auto + above threshold OR strict → proceed
5. Resolve stage_config from vg.config.md crossai_stages.<stage>:
   - primary_clis: ["Gemini-Pro-1M", "Codex-GPT-5.5"]
   - verifier_cli: "Claude-Sonnet-4.6"
   Apply per-run override if --crossai-primary/--crossai-verifier flags set.
6. TodoWrite update: parent "CrossAI iter 1" + 3 children pending
7. Pack brief (per-stage brief_packer):
   - blueprint: full body PLAN + CONTRACTS + TEST-GOALS + CONTEXT + CRUD-SURFACES + UI-MAP + WORKFLOW-SPECS + VIEW-COMPONENTS + BLOCK 5
   - scope: SPECS + CONTEXT full
   - build: 4-artifact full body (PLAN + CONTRACTS + TEST-GOALS + CONTEXT) + new artifacts
8. Iteration loop (max 5):
   a. TodoWrite update: child "Gemini-primary" → in_progress
   b. Parallel invoke (concurrent.futures):
      - Gemini Pro 1M → findings_gemini.json
      - Codex GPT-5.5 → if input <150K: 1-pass → findings_codex.json
                       if >150K: 2-pass → findings_codex_p1.json + findings_codex_p2.json
   c. TodoWrite update: both primary children → completed; verifier child → in_progress
   d. Sonnet verifier:
      - Inputs: all primary findings JSONs + brief metadata
      - Outputs: unified findings-iter${N}.json (v2 schema with verifier_verdict per finding)
      - For each disagreement: Read offending file → verdict (agree/reject/inconclusive)
   e. TodoWrite update: verifier child → completed
   f. Emit telemetry: {stage}.crossai_iteration_started, crossai.disagreement_detected (per disagree)
   g. Consensus rules:
      - All findings verifier_verdict=agree AND severity!=BLOCK → loop_complete (0 BLOCK)
      - At least 1 BLOCK → spawn fix subagent → next iteration
      - Sonnet inconclusive on critical finding → escalate operator (AskUserQuestion)
9. After loop:
   - Clean exit (iter <=5, 0 BLOCK) → emit {stage}.crossai_loop_complete
   - Iter 5 with BLOCKs → AskUserQuestion (continue 5 / defer / skip+debt) → emit terminal event
   - Operator skip+debt → cmd_override fact-check (Q4=C) → emit override.used + {stage}.crossai_loop_user_override
10. Validator at run-complete:
    - Read findings.v2.json + events
    - Verify: terminal event present + iter_count >= 1 (or auto_exempt path) + consensus rules satisfied
    - PASS or BLOCK with detailed evidence
```

---

## Error Handling

| Error | Layer | Response |
|---|---|---|
| Configured CLI not installed | `crossai_config.resolve_stage_config()` | Validate at config-load; if any primary CLI missing → fall back to single-primary mode + emit `crossai.cli_unavailable` warning |
| All primary CLIs unavailable | gating | Treat as `EXEMPT_NO_CLI` (Q4 mechanism); emit `auto_exempt` event |
| Gemini Pro API rate limit | wrapper | Retry 1× with exponential backoff; if still fails → fall back to single-primary (Codex only); emit `crossai.cli_degraded` |
| Codex split 2-pass: pass 1 OK, pass 2 fail | library merge | Sonnet adjudicates with available pass + Gemini findings; emit `crossai.partial_codex_input` |
| Sonnet verifier OOM (input too large) | library | Truncate findings JSON to top-K most severe; re-invoke; emit `crossai.verifier_truncated` |
| Operator AskUserQuestion timeout | slim entry | Default to "skip+debt" path with fact-check; emit `crossai.user_decision_timeout` |
| Findings.json corrupt | validator | BLOCK with explicit "re-run loop" hint; do NOT silently pass |

---

## Testing Strategy

**Unit tests** — per-file logic (60+ tests across all 3 milestones):
- M1: ~15 tests (config parser, registry validation, library API, init wizard)
- M2: ~12 tests (policy modes, heuristic thresholds, AskUserQuestion gate, fact-check integration)
- M3: ~25 tests (parallel invocation, Codex 2-pass, Sonnet adjudicate, consensus rules, schema v2, /vg:health integration)

**Integration tests** — full loop (`scripts/tests/integration/test_crossai_full_loop.py`):
- M1: existing build CrossAI loop unchanged (regression baseline)
- M2: setting `crossai.policy: off` → loop never runs (event check)
- M3: 2 fake CLIs (mock subprocess) → consensus reached → findings.v2.json validates

**E2E tests** — PV3 dogfood:
- M1: re-run existing build phase → no regression
- M2: set `policy: auto`, run small phase → AskUserQuestion fires, skip path works
- M3: run blueprint 4.3 + build 4.4 → multi-primary actually invokes Gemini + Codex CLIs (verify via shell history); findings.v2.json schema valid

**Anti-rationalization regression** — existing tests for `crossai_skip_validation` keep passing (Q4=C ensures `strict` mode still fact-checks).

---

## Migration Plan (existing PV3 project)

1. **M1 deploys** — PV3 sync gets new library + wrappers. `vg.config.md` not modified yet. Build CrossAI behaves identically.
2. **First `/vg:scope|blueprint|build` post-M2 run** → Lazy migrate (Q22=D):
   - Detect missing `crossai.policy` field → append default (`policy: auto`, profile-aware)
   - Detect missing `crossai_stages` → append default (Gemini+Codex primary, Sonnet verifier)
   - Detect missing `role` field on CLIs → annotate ("Gemini" → primary, "Claude" → verifier, etc.)
   - Emit `crossai.config_migrated` telemetry
   - Operator sees diff in next git status, can commit/revert
3. **M3 deploys** — first run after M3 invokes parallel primaries with Sonnet verifier. Operator sees TodoWrite UI with 3 subtasks per iter.
4. **Operator validates** — `/vg:health` shows CrossAI section with metrics. Disagreement rate <30% = healthy.

---

## Cost Estimate (PV3 milestone, 15 phases)

**Before (current):**
- Build CrossAI only: ~$3 max/phase × 15 phase = $45 max
- Scope/blueprint: $0 (no CrossAI)
- Total: ~$45

**After M3 (3-stage multi-primary):**
- Per stage per phase: 1× Gemini Pro full + 1× Codex full + 1× Sonnet findings ≈ $0.60
- 5 iter max → $3/stage worst case
- 3 stages × 15 phase × $1.50 avg/stage = $67.50 typical, $135 worst case

**Diff:** +$22-90 per milestone (50-200% increase)

**Justification:** scope + blueprint CrossAI catches errors earlier (cheaper than build-phase rework cost which is multi-task commits + fix loop). Net negative cost in long run.

---

## Open Questions (defer to operator)

These came up during brainstorm but were not decided; operator can address in implementation or defer:

1. **Cost cap mechanism** — should `vg.config.md` have `crossai.cost_cap_per_phase: $X`? Library aborts loop if accumulated CLI calls exceed cap. Useful for budget-constrained projects.

2. **Multi-primary timeout coordination** — when 1 primary times out (5 min) but other completes, do we wait for laggard or proceed with single-primary? Defaults to "wait" but configurable.

3. **`/vg:crossai-replay` command** — re-run CrossAI on past phase using new config (without rebuilding) to check if upgraded mode catches new findings. Useful for regression testing config changes.

4. **Stage-stage carryover** — should blueprint CrossAI findings be passed to build CrossAI as context? "Already-validated decisions" = save tokens. Defer until M3 stable.

5. **Cross-phase consensus** — running `/vg:scope-review` (cross-phase) with multi-primary? Currently scope CrossAI is per-phase. Cross-phase aggregator separate path.

---

## Success Criteria (per milestone)

**M1 success:**
- All existing build CrossAI tests pass
- New library API documented + tested
- `/vg:project --init` on fresh project generates valid `vg.config.md` with crossai sections
- Lazy migration on PV3 produces clean diff (no false changes)

**M2 success:**
- Setting `policy: off` on PV3 → all 3 stages silent; `/vg:health` shows "CrossAI: disabled"
- Setting `policy: auto` + small phase → AskUserQuestion fires once
- `strict` mode anti-rationalization gate (existing) keeps blocking false-claim overrides

**M3 success:**
- Run scope/blueprint/build CrossAI on PV3 phase 4.4 → 3 stages all invoke Gemini + Codex + Sonnet
- `findings.v2.json` produced with `source` + `verifier_verdict` fields
- Disagreement scenario triggered (manually craft) → Sonnet adjudicates → consensus output traceable
- `/vg:health` CrossAI section shows last-run metrics
- 0 regressions on existing build CrossAI behavior (additive payload)

---

## Spec self-review

- ✅ **Placeholders:** none ("TBD", "TODO" not present in spec body — open questions explicitly labeled as deferred)
- ✅ **Internal consistency:** decisions reference each other coherently (Q5/Q7/Q17/Q18 all on runtime selection; Q9-mod/Q10/Q14 all on consensus protocol)
- ✅ **Scope check:** decomposed into 3 milestones (M1 infra, M2 gating, M3 consensus); each ships independently
- ✅ **Ambiguity check:** explicit "primary_clis" vs "verifier_cli" terminology; explicit "agree/reject/inconclusive" verdict enum; explicit cost numbers

---

**Spec status:** Ready for implementation planning.

Next step: `/superpowers:writing-plans` per milestone (M1 first).
