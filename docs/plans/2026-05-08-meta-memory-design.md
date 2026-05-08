# Meta-Memory Design — Deploy + Test + Accept Coverage

**Date:** 2026-05-08
**Author:** Claude (brainstorming session) + caveman-investigator + codex review
**Scope:** Extend VG bootstrap system to give `/vg:deploy`, `/vg:test`, `/vg:accept` a producer-consumer learning loop, plus a Dreams-style consolidation pass.

---

## 1. Motivation

User-reported gap: AI phải dò lại pattern deploy mỗi lần thay vì học từ deploy thành công trước đó. After 2-AI investigation (Claude Sonnet investigator + OpenAI Codex CLI):

| Gap | Evidence |
|---|---|
| `/vg:deploy` không inject bootstrap rules | `deploy.md:401-405,441-470` — no `bootstrap-inject.sh` call |
| Schema `target_step` không có `deploy` | `vg-reflector/SKILL.md:296`, `vg-lesson/SKILL.md:207` |
| Reflector không chạy post-deploy/test/accept | `_shared/reflection-trigger.md:4,131` |
| Build orchestrator không nạp meta-memory ở preflight | `_shared/build/preflight.md` — chỉ load context, không load rules |
| Consolidation pass (cross-session pattern detection) chưa có | No `--consolidate` mode in `/vg:learn` |

**Industry baseline (2026-04 Anthropic Dreams):** scheduled reflection over up to 100 past sessions, distill into procedural memory, side-by-side refinement (no overwrite). Rakuten reported 97% fewer first-pass errors.

**3-tier memory taxonomy (LangChain/Mem0/Redis 2026 consensus):**
- Episodic: events.db + DEPLOY-STATE.json (have)
- Semantic: FOUNDATION.md + vg.config.md (have)
- **Procedural: NONE — this design adds it**

---

## 2. Architecture

### 2.1 Producer-consumer loop

```
                    ┌────────────────────────────────┐
                    │  reflector (Haiku subagent)    │
                    │  3 NEW triggers:               │
                    │   - phase.deploy_completed     │
                    │   - phase.test_completed       │
                    │   - phase.accept_uat_completed │
                    └───────────────┬────────────────┘
                                    │ drafts
                                    ▼
              ┌─────────────────────────────────────────┐
              │  .vg/bootstrap/CANDIDATES.md            │
              │  (target_step ∈ {deploy,test,accept})   │
              └──────────────────┬──────────────────────┘
                                 │ /vg:learn promote
                                 ▼
              ┌─────────────────────────────────────────┐
              │  .vg/bootstrap/rules/{slug}.md          │
              │  + overlay.yml                          │
              │  type: declarative | procedural (NEW)   │
              └──────────────────┬──────────────────────┘
                                 │ bootstrap-inject.sh
                                 ▼
   ┌────────────────────┬────────────────────┬────────────────────┐
   │  /vg:build STEP 0.5│  /vg:deploy STEP 0 │  /vg:accept STEP 1 │
   │  (NEW preflight)   │  (NEW pre-spawn)   │  (NEW preflight)   │
   └────────────────────┴────────────────────┴────────────────────┘
```

### 2.2 Dreams-style consolidation pass

`/vg:learn --consolidate` (manual trigger first 2 weeks, optional cron later):
- Query events.db window 30 days
- Group by rule fingerprint
- Detect: recurrence (≥3 PASS) → auto-promote, contradiction (≥3 FAIL after PASS) → propose retract, drift (no fire 30d) → propose archive
- Output side-by-side `CONSOLIDATION-{date}.md` (Anthropic Dreams pattern: never overwrite)

---

## 3. Schema changes

### 3.1 Rule frontmatter

```yaml
---
slug: deploy-fly-io-prebuild-required
title: "fly.io deploy yêu cầu prebuild trước flyctl deploy"
type: procedural          # NEW. Default declarative for backwards compat.
target_step: deploy       # NEW value. Schema: scope|blueprint|build|review|test|accept|deploy|global
priority: high
tier: B

# Procedural-only fields:
preconditions:
  - env: fly.io
  - has_dockerfile: true
sequence:
  - "npm run build"
  - "flyctl deploy --remote-only"
  - "flyctl status --json | jq .Health"
success_signals:
  - "phase.deploy_completed.outcome == PASS"
  - "health_retry_count <= 2"
applies_when_all_match: true
---

# Body: context evidence + 1-shot example
```

### 3.2 Validation gates (`validators/verify-rule-schema.py`)

- `procedural` rules MUST have `sequence` + `success_signals`
- `declarative` rules MUST NOT have `sequence`
- `target_step` ∈ enum (scope, blueprint, build, review, test, accept, deploy, global)
- Existing rules without `type` field → loader defaults `declarative` (no migration needed)

### 3.3 New event types (`schemas/event.json`)

```json
"phase.deploy_completed_observed",
"phase.test_completed_observed",
"phase.accept_uat_observed",
"bootstrap.rule_skipped_preconditions",
"bootstrap.consolidation_run",
"bootstrap.consolidation_proposed",
"bootstrap.contradiction_detected",
"bootstrap.preflight_timeout"
```

---

## 4. Reflector triggers

### 4.1 3 NEW hooks (`_shared/reflection-trigger.md`)

```bash
# A. Post-deploy
on_event: phase.deploy_completed
spawn: vg-reflector
inputs:
  - events.db query: deploy.{started,completed,failed}
  - DEPLOY-STATE.json deployed.{env}
  - .deploy-log.{env}.txt per env
  - vg.config.md (env list, deploy commands)
candidate_target: target_step=deploy, type=procedural
fingerprint: hash(env + deploy_commands + dockerfile_hash)

# B. Post-test
on_event: phase.test_completed
spawn: vg-reflector
inputs:
  - events.db query: test.* + codegen.*
  - TEST-GOALS.md per-goal verdicts
  - fix-loop iteration count
candidate_target: target_step=test, type=declarative|procedural
fingerprint: hash(framework + selector_strategy)

# C. Post-accept
on_event: phase.accept_uat_completed
spawn: vg-reflector
inputs:
  - UAT-CHECKLIST.md verdicts
  - events.db: gate.fired
  - user message log filtered (NO transcript)
candidate_target: target_step=accept, type=declarative
fingerprint: hash(phase_type + gate_pattern)
```

### 4.2 Reflector skill expansion (`vg-reflector/SKILL.md`)

- Type detection heuristic:
  - Repeated action sequence + outcome PASS → procedural
  - "do/don't" pattern in user msgs / artifacts → declarative
- Procedural candidate validates `preconditions + success_signals` before append
- Echo-chamber guard preserved: NEVER read AI transcript

### 4.3 Consolidation pass (`/vg:learn --consolidate`)

Implementation outline:

```bash
# 1. Query
EVENTS=$(vg-orchestrator query-events \
  --since "30 days ago" \
  --event-types "bootstrap.rule_fired,bootstrap.outcome_recorded,phase.deploy_*,phase.test_*")

# 2. Group + detect
python .claude/scripts/bootstrap-consolidate.py \
  --events <(echo "$EVENTS") \
  --output .vg/bootstrap/CONSOLIDATION-$(date +%F).md

# 3. Detection rules:
#    - Recurrence: same fingerprint, outcome PASS ≥ 3 → tier A propose
#    - Contradiction: PASS ≥ 3 then FAIL ≥ 3 → propose retract (user gate)
#    - Drift: never fired in 30 days → propose archive

# 4. NEVER overwrite rules/*.md or overlay.yml
# 5. User reviews via /vg:learn --review-consolidation
```

---

## 5. Inject sites

### 5.1 Site 1: `/vg:build` STEP 0.5 preflight (CHANGE A)

File: `_shared/build/preflight.md`

```bash
# Load procedural memory across deploy + build context
RULES_BLOCK=$(.claude/scripts/bootstrap-loader.py \
  --target-step build \
  --target-step deploy \
  --include-procedural \
  --filter-preconditions "$(cat $PHASE_DIR/.phase-context.json)")

echo "$RULES_BLOCK" >> $PHASE_DIR/.build-context.md
```

Effect: orchestrator chính có procedural context trước khi planner chia wave. Wave order aware về deploy gating.

### 5.2 Site 2: `/vg:deploy` STEP 0 pre-spawn (NEW)

File: `deploy.md` (insert before line 401 spawn block)

```bash
# Load deploy-specific procedural rules
BOOTSTRAP_RULES_BLOCK=$(.claude/scripts/bootstrap-loader.py \
  --target-step deploy \
  --include-procedural \
  --filter-preconditions "{\"env\": \"$ENV\", \"has_dockerfile\": $HAS_DOCKERFILE}")

# Pass into vg-deploy-executor capsule
export BOOTSTRAP_RULES_BLOCK
```

Effect: deploy executor receives sequence hints from past successful deploys with matching context fingerprint.

### 5.3 Site 3: `/vg:accept` STEP 1 preflight (NEW)

File: `_shared/accept/preflight.md`

```bash
RULES_BLOCK=$(.claude/scripts/bootstrap-loader.py \
  --target-step accept \
  --filter-preconditions "{\"phase_type\": \"$PHASE_TYPE\"}")
```

Effect: UAT checklist builder biased toward gate patterns historically prone to miss.

### 5.4 Site 4: existing scope/blueprint/build-wave/review/test (EXTEND)

`bootstrap-inject.sh` filter expansion:
- Existing: `target_step == step_name` only
- New: `target_step == step_name` OR (`type == procedural` AND `preconditions match phase context`)
- Render differently:
  - Declarative block: `MUST do X` / `MUST NOT do Y`
  - Procedural block: `Recipe đã work với context Z: [step1, step2, ...]. Success signals: [...]`

---

## 6. Data flow (1 phase, 1 cycle)

```
[Phase N — first deploy]
  /vg:deploy → executor → fly.io sequence X → PASS
  emit phase.deploy_completed (sha=abc, env=fly.io, time=12s, retries=1)
  ↓
  reflector (NEW post-deploy hook)
  query events.db → see sequence X + PASS
  draft candidate type=procedural, target_step=deploy
  append .vg/bootstrap/CANDIDATES.md
  emit reflection.proposed
  ↓
  /vg:learn --review (user gate Tier B) → promote → rules/{slug}.md
  emit bootstrap.candidate_promoted
  ↓
[Phase N+1 — same env fingerprint]
  /vg:build STEP 0.5 (Site 1) → loader match preconditions
  inject .build-context.md
  planner aware: phase deploys to fly.io → wave order
  ↓
  /vg:deploy STEP 0 (Site 2) → executor capsule has rule
  executor follows recipe, no aimless probing
  emit bootstrap.rule_fired
  ↓
  outcome → bootstrap.outcome_recorded (PASS|FAIL)
  ↓
[After 30 days, 5 phases used same rule, all PASS]
  /vg:learn --consolidate
  detect: rule fired 5×, outcome PASS 5× → tier A confirmed
  CONSOLIDATION-{date}.md proposes: keep + raise priority
  user reviews → overlay.yml updated
```

---

## 7. Error handling

| Failure mode | Behavior |
|---|---|
| Procedural rule preconditions không match | Skip silently. Emit `bootstrap.rule_skipped_preconditions`. |
| Procedural sequence partial fail (step 2/4) | `bootstrap.outcome_recorded` outcome=PARTIAL_FAIL. Reflector next run propose retract or edit. |
| 2 procedural rules conflict (cùng match) | Tier-then-priority sort. Tie → user prompt `/vg:learn --resolve-conflict`. NO silent pick. |
| events.db corrupt | Reflector exit 2 (degraded). Inject site falls back to `target_step` filter only. Pipeline continues. |
| Consolidation contradiction (PASS+FAIL same rule) | NO auto-retract. Append warning section. Emit `bootstrap.contradiction_detected`. User-gated. |
| Loader can't find overlay.yml | Empty block (existing behavior). |
| Schema invalid at promote | `verify-rule-schema.py` blocks promote. Existing rules never validate retroactively. |
| Build preflight loader > 5s | Skip inject. Emit `bootstrap.preflight_timeout`. |
| Procedural rule with binary command not installed | Executor exit non-zero → outcome=ENV_MISSING. Reflector marks `applies_when_all_match=false`. |

---

## 8. Testing plan

### Layer 1 — Unit (validators)

- `tests/validators/test_rule_schema_procedural.py`
- `tests/validators/test_consolidation_idempotent.py`

### Layer 2 — Integration (per-step)

- `tests/integration/test_build_preflight_inject.py`
- `tests/integration/test_deploy_pre_spawn_inject.py`
- `tests/integration/test_post_deploy_reflector.py`

### Layer 3 — E2E (full cycle)

- `tests/e2e/test_meta_memory_loop.py` — 2-phase cycle, assert rule fire + outcome record
- `tests/e2e/test_contradiction_detection.py` — 3× PASS then 3× FAIL, assert user-gate

### Layer 4 — Cross-platform smoke

- `tests/smoke/test_windows_powershell_inject.py` — git-bash on Windows, no codex file-open dialog regression

---

## 9. Rollout (atomic commits)

1. Schema migration: add `type` field, default `declarative`. Validator update. No retroactive break.
2. Reflector triggers (3 hooks). Behind flag `vg.config.md: meta_memory_enabled=false`.
3. Inject sites build/deploy/accept. Same flag gate.
4. Consolidation pass. User-trigger only first 2 weeks.
5. Flip `meta_memory_enabled=true` default after dogfood 1 phase end-to-end.

---

## 10. Out of scope (future)

- mem0 MCP cross-project memory (planned in v2.40 docs but not wired)
- Cross-project memory store at `~/.vg/global-bootstrap/`
- Auto-cron consolidation (requires scheduler infra)
- Test/accept procedural type expansion beyond declarative

---

## 11. References

- [Memory tool — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [Anthropic adds persistent memory to Claude Managed Agents](https://www.edtechinnovationhub.com/news/anthropic-brings-persistent-memory-to-claude-managed-agents-in-public-beta)
- [Self-Improving Agents via Scheduled Reflection: Anthropic's Dreaming Architecture](https://discuss.huggingface.co/t/self-improving-agents-via-scheduled-reflection-anthropics-dreaming-architecture/175837)
- [Beyond Short-term Memory: 3 Types of Long-term Memory](https://machinelearningmastery.com/beyond-short-term-memory-the-3-types-of-long-term-memory-ai-agents-need/)
- [Architecture and Orchestration of Memory Systems in AI Agents](https://www.analyticsvidhya.com/blog/2026/04/memory-systems-in-ai-agents/)
- [Claude Code Dreams: Anthropic's New Memory Feature](https://claudefa.st/blog/guide/mechanics/auto-dream)

---

## 12. Open questions for verification round

- Anthropic Dreams: exact session window (100 sessions per docs vs our 30-day window — equivalent?)
- Side-by-side `CONSOLIDATION-{date}.md` pattern — Anthropic uses what naming?
- Procedural memory format consensus: `sequence + preconditions + success_signals` — does this match Mem0 / LangChain procedural format?
- Echo-chamber guard: any way Anthropic Dreams reads transcripts and avoids drift?
- Tier auto-promotion threshold: industry uses ≥3 occurrences — too low? Too high?
