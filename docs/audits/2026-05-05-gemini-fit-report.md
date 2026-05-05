# Gemini Fit Report — VG Workflow Cost Optimization

**Date:** 2026-05-05
**Author:** HOTFIX session 2 follow-up
**Trigger:** Sếp Dũng asked for Gemini's strengths to identify optimal placement
**Constraint:** Operator notes — "Gemini code khá kém. Mạnh về giao diện và tổng hợp"

---

## Executive Summary

Gemini fits VG workflow at **6 specific touchpoints** where its native strengths
(1M context, multimodal, long-document synthesis, visual reasoning) outperform
Claude on cost-quality tradeoff. **Code generation tasks stay Claude/Codex** —
Gemini's weakness in subtle TS types, async patterns, and refactoring under
context-pressure makes it unsafe for build executors.

Estimated cost reduction across milestone: **~50-60%** when applied at all 6
touchpoints with dynamic runtime selection.

---

## Gemini's Hard Advantages

| Capability | Gemini 3 Pro | Claude Sonnet 4.6 | Claude Haiku 4.5 |
|---|---|---|---|
| Context window | **1M tokens (default)** | 200K (1M = premium) | 200K |
| Multimodal | **Native vision/audio/video** | Vision via separate tier | Vision via separate tier |
| Pricing (input) | ~$1.25/M | ~$3/M | ~$0.80/M |
| Pricing (output) | ~$10/M | ~$15/M | ~$4/M |
| Latency (Flash) | **Sub-second** | 2-5s | 1-2s |
| Visual reasoning | **Top-tier** for UI/design | Strong but text-priority | Decent |

| Capability | Gemini 2.5 Flash / 3.1 Flash-Lite |
|---|---|
| Pricing (input) | ~$0.075-0.30/M (cheaper than Haiku) |
| Latency | **Sub-500ms** |
| Multimodal | **Native** |

## Gemini's Hard Weaknesses (per operator)

- Code generation: misses subtle TS types, async patterns, edge cases in
  Express/NestJS/Next.js conventions
- Refactoring with deep call-graph context
- Build executor tasks (better stay with Sonnet/Codex)
- Strict format compliance (sometimes drifts from required output schemas)

---

## 6 Touchpoints — Where Gemini Fits

### Touchpoint 1: Long-context aggregation (HIGH ROI)

**Skills/commands:** `/vg:scope-review`, `/vg:milestone-summary`, `write-test-spec`,
`/vg:audit-milestone`

**Why Gemini:**
- These commands load 5-15 phase artifacts simultaneously (PLAN+CONTRACTS+GOALS+CONTEXT per phase)
- Total payload often >300K tokens → Sonnet 200K must chunk
- Gemini Pro 1M context = 1-shot read, no chunk artifacts

**Recommended model:** `cx/gemini-3.1-pro-preview` (sếp's 9router proxy)

**Cost saving:** ~50% (no chunk overhead, no redundant Sonnet calls)

**Risk:** Low — synthesis task, Gemini's strength

---

### Touchpoint 2: Visual / multimodal pipeline (HIGH ROI)

**Skills/commands:** `vg-design-scanner` (Layer 2 deep-scan), `vg-design-gap-hunter`
(Layer 3 adversarial), `design-fidelity-guard`, `visual-regression`,
`/vg:design-extract`, `/vg:design-reverse`

**Why Gemini:**
- Native multimodal (PNG/Figma/HTML render side-by-side) without tier escalation
- Visual reasoning beats Haiku for design fidelity diffing
- Pixel-diff + semantic understanding combined

**Recommended model:**
- Heavy: `gc/gemini-3-pro-preview` (full Pro for adversarial gap-hunter)
- Cheap fast-path: `gc/gemini-3.1-flash-lite-preview` (per-asset normalize)

**Cost saving:** ~62% vs Haiku, ~30% vs Sonnet vision tier
**Quality gain:** measurably better UI semantic understanding

**Risk:** Low-Med — Gemini sometimes over-describes; clamp output schema strictly

---

### Touchpoint 3: CrossAI build verification — adversarial reviewer slot

**Skills/commands:** `vg-build-crossai-loop.py` (currently Codex+Gemini parallel)

**Why Gemini already in rotation:**
- vg.config.md crossai_clis: Codex+Gemini+Claude — 3-way consensus
- Gemini's role: **catch decision-violation patterns** (D-XX in CONTEXT not
  honored by code) where its long-context strength helps trace decision →
  implementation path

**Recommended model:** `cx/gemini-3.1-pro-preview` for primary, fallback to
`gc/gemini-3-pro-preview` if proxy down

**Cost saving:** Replace Codex primary → ~60% (Codex $3/M → Gemini Pro $1.25/M)

**Risk:** Med — Gemini code-quality findings sometimes shallow. Keep Codex/Claude
in rotation for deep code review.

---

### Touchpoint 4: Test phase — spec-to-test alignment & replay verification

**Skills/commands:** `vg-test-goal-verifier` (replay loop + console baseline check),
`flow-runner` (Playwright E2E), `test-review`, `flow-spec` generation

**Why Gemini:**
- Test specs cite many sources (TEST-GOALS+API-CONTRACTS+UI-MAP+SPECS) — 1M context fits
- Replay assertion: read screenshot + DOM snapshot + network logs → semantic verdict (multimodal)
- E2E flow analysis: visual storyboarding from screenshot sequence

**Recommended model:**
- Replay verifier (multimodal): `gc/gemini-3-pro-preview`
- Spec review (text-heavy): `cx/gemini-3.1-pro-preview`

**Cost saving:** ~40-50% (current Sonnet 4.6 verifier)

**Risk:** Low — verification task, no code generation

---

### Touchpoint 5: High-volume scanners (review phase)

**Skills/commands:** `vg-haiku-scanner` (10-20 spawn/run), lens-prompts dispatch
(14 lenses × per-phase), `vg-reflector` (every step end), code-scan static
analysis pre-pass

**Why Gemini Flash:**
- Volume × cost = biggest absolute saving
- Flash latency sub-500ms unlocks parallel scanner spawns
- Scanner reports observations (no judgment) — Gemini Flash sufficient

**Recommended model:** `gc/gemini-3.1-flash-lite-preview` (cheapest tier)

**Cost saving:** ~75% vs Haiku ($0.80 → $0.075-0.30/M input)

**Risk:** Med — must verify Flash holds output schema. Add strict JSON schema
validator post-output.

---

### Touchpoint 6: Reflector + bootstrap candidate drafting

**Skills/commands:** `vg-reflector` (end-of-step Haiku), `vg-lesson` capture,
bootstrap-critic, `gsd-research-synthesizer`

**Why Gemini Flash:**
- Synthesis task (read events + artifacts + user msgs → max 3 candidates)
- Low-latency for inline blocking spawn UX
- Output is YAML candidate list — schema-strict

**Recommended model:** `gc/gemini-3.1-flash-lite-preview` or `2.5 Flash`

**Cost saving:** ~62%

**Risk:** Low — output schema enforced via vg-orchestrator validator post-spawn

---

## Anti-fit (KEEP Claude/Codex)

| Skill | Why NOT Gemini |
|---|---|
| `vg-build-task-executor` | Code generation — Gemini weak |
| `vg-blueprint-planner` | Subtle TS type planning — Sonnet strong |
| `vg-blueprint-contracts` | API contract authoring — Codex/Sonnet best |
| `vg-build-post-executor` | Post-wave validation + L4a gates — Sonnet |
| `superpowers:test-driven-development` (TDD execution) | Implementation Sonnet/Opus |
| `vg-codegen-interactive` (Playwright .spec.ts gen) | Codegen Sonnet |
| `flow-codegen` (Playwright test files) | Codegen Sonnet |
| `gsd-debugger` | Code-aware debugging — Sonnet |

---

## Dynamic Runtime Selection (Operator Preference)

Per sếp's note (2026-05-05): no hard-coded model. Pattern:

1. Slim entry reaches CrossAI/visual/long-context step
2. Orchestrator calls `AskUserQuestion` 2-question batch:
   - **Q1: model** — list từ vg.config.md.crossai_clis + custom paths
   - **Q2: runtime** — codex CLI / gemini CLI / 9router proxy / claude subagent
3. Selection persists `.vg/runs/<run_id>/crossai-runtime.json`
4. Subsequent iterations same run reuse selection
5. Fallback: `VG_CODEX_MODEL_ADVERSARIAL` env var if AskUserQuestion unavailable

Implementation: ~2h modify `vg-build-crossai-loop.py` + slim entry gate.

---

## Suggested Rollout Order

| Step | Touchpoint | Effort | Risk |
|---|---|---|---|
| 1 | T3 — CrossAI build-loop (env var swap, Gemini already in rotation) | 30 min | Low |
| 2 | T1 — Long-context aggregator commands | 2h | Low |
| 3 | T6 — Reflector swap to Gemini Flash | 1h | Low |
| 4 | T2 — Design pipeline multimodal swap | 3h | Med |
| 5 | T5 — Haiku scanners → Flash (verify schema first) | 4h | Med |
| 6 | T4 — Test phase replay verifier | 4h | Med |
| 7 | Dynamic AskUserQuestion runtime gate | 2h | Low |

**Total effort:** ~16h spread across milestones
**Cumulative saving:** ~50-60% milestone cost

---

## Open Questions (defer to operator)

1. **Cap on visible cost reduction in CrossAI** — replacing Codex primary with
   Gemini reduces 60% but may shift adversarial diversity. Keep at least 1
   Claude + 1 Codex slot in 3-way rotation?

2. **Output schema enforcement for Flash** — Gemini Flash drifts more on JSON
   output. Add post-spawn JSON schema validator (already have `vg-validators`
   registry — add `verify-gemini-output-schema.py`)?

3. **9router proxy reliability** — `cx/` and `gc/` prefixes route through
   external proxy. SLO/fallback chain when proxy degraded?

4. **Codex CLI keep or sunset?** — if Gemini covers CrossAI + long-context +
   visual, Codex's role narrows to "Claude-different perspective". Worth
   keeping as 1/3 vs full sunset?

5. **Test phase replay multimodal sweet-spot** — Pro vs Flash for screenshot
   verdict accuracy. Need calibration run on phase 4.x to measure.
