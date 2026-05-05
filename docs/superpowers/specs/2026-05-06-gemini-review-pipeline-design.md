# Gemini-Native /vg:review Pipeline Design (Plan G1)

**Date:** 2026-05-06 (revised post Codex-primitive audit)
**Status:** Approved (operator: sếp Dũng)
**Scope:** Pipeline target = `/vg:review` only. Runtime infrastructure (hooks, spawn contract, TodoWrite adapter, AskUserQuestion fallback, MCP template, env-var branching) is full primitive parity matching Codex precedent — required for /vg:review to actually work end-to-end and reusable for /vg:test, /vg:accept ports later.
**Predecessors:**
- `docs/audits/2026-05-05-gemini-fit-report.md` (Gemini fit analysis)
- Codex runtime mapping audit (in-session 2026-05-06)
- Codex primitive parity audit (in-session 2026-05-06): 6 Claude primitives × Codex coverage table
- Research on gemini-3.1-pro-preview specs + 6-model tier menu

---

## Goal (one sentence)

Port the existing /vg:review pipeline so it can run end-to-end with Gemini family models (3.1-pro / 2.5-flash / 3.1-flash-lite) as a third runtime alongside Claude (default) and Codex, by mirroring the Codex runtime-mapping pattern: parallel skill mirrors, env-var-driven branching, subprocess-CLI spawn contract, parity tests.

## Architecture (3 sentences)

Create `.gemini/skills/`, `.gemini/agents/`, `gemini-skills/` parallel to the Codex/Claude mirrors; never modify Claude paths in shared code beyond the 5 documented branch sites Codex already touches. Spawn happens via new `commands/vg/_shared/lib/gemini-spawn.sh` invoking the `gemini` CLI binary with tier-mapped models, recording evidence at `.vg/runs/<run_id>/gemini-spawns/` mirroring the Codex pattern. Runtime selection via `VG_RUNTIME=gemini` env var (or `vg.config.md.runtime: gemini`); when unset, Claude default flow is unchanged.

## Tech Stack

- Python 3.12+ (helpers, evidence recorder, tier env builder)
- Bash (gemini-spawn.sh, mirror sync script)
- Gemini CLI (`gemini` binary, npm package `@google/gemini-cli`)
- 9router proxy support for `cx/`/`gc/` model prefixes (operator's existing setup)
- pytest (parity + equivalence tests)

---

## Claude Primitive Coverage (Codex precedent → Gemini must-have)

Audit on 2026-05-06 mapped 6 Claude primitives across the 3 runtimes. Gemini must replicate
Codex's coverage at minimum (parity table below) — gaps documented are blockers for
/vg:review to function end-to-end with Gemini.

| Primitive | Claude (default) | Codex (precedent) | Gemini must-have | Implementation |
|---|---|---|---|---|
| **Hook lifecycle** | 6 events native | 5 events implemented (skip SessionStart) | Match Codex 5 events | New `.claude/scripts/gemini-hooks/` mirror + `scripts/gemini-hooks-install.py` |
| **TodoWrite** | Native tool | Compact plan window — orchestrator signs evidence; no native tool needed | Same as Codex pattern | New `gemini` adapter case in `cmd_tasklist_projected` |
| **AskUserQuestion** | Native batched UI | No native tool — fallback to sequential stdin / CLI flags / paste-prompt | Same as Codex fallback (Gemini CLI also lacks batched UI) | Document in spawn contract; pattern reused |
| **Agent spawn** | Native tool | `codex-spawn.sh` + manifest evidence | Native tool unavailable | New `gemini-spawn.sh` + manifest pattern |
| **MCP servers** | 5× Playwright + others session-baked | Operator-managed `templates/codex/config.template.toml`; child spawns no MCP | Same as Codex pattern | New `templates/gemini/config.template.toml` |
| **File edit** | Native Read/Write/Edit/MultiEdit | `apply_patch` only (heavier hook fork) | Gemini CLI HAS native Read/Write/Edit | KEEP existing `vg-pre-tool-use-write.sh` (no apply_patch fork needed) — Gemini wins on this primitive |

**Win:** File edit primitive — Gemini CLI ships native tools, so `vg-pre-tool-use-write.sh`
covers all 3 runtimes uniformly. No `gemini-pre-tool-use-apply-patch.py` needed.

---

## 5 Architectural Patterns (locked from Codex audit)

The Plan G1 implementation MUST follow these 5 rules — all reverse-engineered from the
existing Codex runtime mapping. Deviation = risk of breaking Claude default behavior.

### Rule 1: Parallel skill mirror, no shared-code overwrites

- Create `.gemini/skills/`, `.gemini/agents/`, `gemini-skills/` (top-level source dir).
- Never overwrite `commands/vg/_shared/review/discovery/delegation.md:65-67` (`model="haiku"` hardcoded for Claude path).
- All Gemini-specific behavior lives in `.gemini/...` mirrors + `gemini-skills/...` source.

### Rule 2: Skill generation mirrors Codex pattern

- New script `scripts/generate-gemini-skills.sh` mirrors `scripts/generate-codex-skills.sh:295-315`.
- Output: `gemini-skills/vg-review/SKILL.md` (initially review-only; expand later).
- Adapter block `<gemini_skill_adapter>` documents tool mappings:
  - `Agent(model="haiku") → gemini-spawn.sh --tier scanner --model gemini-2.5-flash`
  - `Agent(model="sonnet") → gemini-spawn.sh --tier executor --model gemini-3.1-pro-preview`
  - `MCP Playwright` → keep (Gemini CLI supports MCP)
  - `TaskCreate / TodoWrite` → main orchestrator handles (Gemini CLI doesn't ship native equivalent)
  - `AskUserQuestion` → inline prompt via Gemini stdin pipe

### Rule 3: Runtime branching only at 5 documented sites

- Same files Codex already branches in:
  1. `scripts/hooks/vg-user-prompt-submit.sh:12`
  2. `scripts/hooks/vg-pre-tool-use-bash.sh:429,531`
  3. `scripts/vg-orchestrator/__main__.py:125`
  4. `commands/vg/_shared/lib/block-resolver.sh:34-48`
  5. `commands/vg/review.md:954,968`
- Pattern: extend `case "${VG_RUNTIME}"` with a new `gemini)` branch. Codex branch unchanged. Default (unset) → Claude default unchanged.

### Rule 4: Spawn via subprocess CLI (no MCP)

- New `commands/vg/_shared/lib/gemini-spawn.sh` mirrors `codex-spawn.sh:1-100`.
- Flags: `--tier {planner|executor|scanner|adversarial}`, `--model <name>`, `--prompt-file`, `--out`, `--sandbox <mode>`.
- Tier env vars (in `scripts/lib/gemini_vg_env.py`):
  ```
  VG_GEMINI_MODEL_PLANNER="gemini-3.1-pro-preview"
  VG_GEMINI_MODEL_EXECUTOR="gemini-3.1-pro-preview"
  VG_GEMINI_MODEL_SCANNER="gemini-2.5-flash"
  VG_GEMINI_MODEL_ADVERSARIAL="gemini-3.1-pro-preview"
  VG_GEMINI_MODEL_PROBE="gemini-3.1-flash-lite-preview"  # optional cheap tier
  VG_GEMINI_MODEL_ADVERSARIAL_FALLBACK="gemini-2.5-pro"  # rate-limit fallback
  ```
- Evidence: `scripts/gemini-spawn-record.py` writes JSON manifest to
  `.vg/runs/<run_id>/gemini-spawns/<spawn_id>.json` + `.gemini-spawn-manifest.jsonl`.

### Rule 5: Parity tests enforce non-interference

- `scripts/tests/test_gemini_spawn_parity.py` clones `test_codex_spawn_parity.py:8-52` —
  asserts review heavy spawn sites have `gemini-spawn.sh` markers in `.gemini/skills/...`.
- `scripts/verify-gemini-mirror-equivalence.py` clones
  `verify-codex-mirror-equivalence.py:25-100` — SHA256 hash compare source body
  vs `.gemini/skills/...` body (strip adapter, normalize whitespace).

---

## Tier-to-Model Map (locked from operator confirm 2026-05-06)

| Tier | Model | Role in /vg:review |
|---|---|---|
| `planner` | `gemini-3.1-pro-preview` | Future use (review-batch orchestrator); not active in single-phase /vg:review |
| `executor` | `gemini-3.1-pro-preview` | Step 3 fix-loop (small/MINOR scope only; MODERATE/MAJOR keep Sonnet) |
| `scanner` | `gemini-2.5-flash` | Step 2a browser navigator + per-view scanners (Haiku replacement) |
| `adversarial` | `gemini-3.1-pro-preview` | Step 5 CrossAI rotation slot |
| `probe` (optional) | `gemini-3.1-flash-lite-preview` | Step 2b lens probes high-volume |

**3 models default cover 90%:** Pro 3.1 (heavy), Flash 2.5 (scanner), Flash-Lite 3.1 (probe optional).

**3 models NOT used:**
- `gemini-3-flash-preview` (outdated by 3.1-flash-lite)
- `gemini-2.5-flash-lite` (too weak for VG)
- `gemini-2.5-pro` (only as adversarial fallback when 3.1-pro rate-limited)

---

## Step-by-Step Mapping (current /vg:review → Gemini-native)

| Step | Current (Claude default) | Gemini-native swap | Risk | Validation |
|---|---|---|---|---|
| 0-1 Preflight + code-scan | Deterministic Python | unchanged | None | — |
| **2a** Browser nav + scanners | `Agent(model="haiku")` ×N | `gemini-spawn.sh --tier scanner --model gemini-2.5-flash` | MED — schema drift | Post-spawn JSON validator (`verify-scanner-output-schema.py`); fallback Haiku on schema fail |
| **2b** Lens probes | Gemini Flash (existing) | Operator pick: Flash 2.5 (current) OR Flash-Lite 3.1 (cheaper) OR Pro 3.1 (deeper) | LOW — internal Gemini upgrade | Configurable via flag |
| 2c-2d Findings collect/concat | Deterministic | unchanged | None | — |
| **3** Fix-loop (MINOR small) | `Agent(model="sonnet")` | `gemini-spawn.sh --tier executor --model gemini-3.1-pro-preview` | MED — code quality | A/B harness on small-scope phase before production swap |
| 3 Fix-loop (MODERATE/MAJOR) | unchanged | KEEP Sonnet (Gemini code quality not validated for complex refactor) | None | — |
| 4 Verdict (Goal compare) | Deterministic | unchanged | None | — |
| **5** CrossAI | Variable (registry-driven) | Add `gemini-3.1-pro-preview` to registry rotation slot | LOW | Existing `crossai_clis` schema |
| 6 Close + reflection | Deterministic + reflector | unchanged (reflector keeps Haiku) | None | — |

**Steps actually changed: 2a, 2b (config-driven), 3 (small scope only), 5 (additive registry entry).**

**Steps unchanged: 0, 1, 2c, 2d, 3 (MODERATE/MAJOR), 4, 6.**

---

## Default Behavior (operator-pick decision)

Per operator confirm (in-session 2026-05-06):

- **Default:** `VG_RUNTIME` unset → Claude flow unchanged (status quo preserved).
- **Opt-in mode A:** `VG_RUNTIME=gemini /vg:review <phase>` per-run override.
- **Opt-in mode B:** Add `runtime: gemini` to project `vg.config.md` for permanent project-level switch.
- **No A/B mode:** Plan G1 ships single-runtime switch; A/B harness is separate validation tool, not pipeline mode.

---

## A/B Validation Harness (Task 11 in plan)

Standalone script `scripts/lab/gemini-ab-harness.py`:

1. Run `/vg:review <phase>` with `VG_RUNTIME` unset → record findings.json + duration + cost (token estimate)
2. Reset phase to pre-review state (git stash + checkout)
3. Run `/vg:review <phase>` with `VG_RUNTIME=gemini` → record findings.json + duration + cost
4. Diff findings: precision, recall, false-positive overlap
5. Output `docs/audits/<DATE>-gemini-ab-<phase>.md` with metrics + side-by-side findings

Operator runs this harness BEFORE flipping default — provides evidence for production swap.

---

## File List (deliverables)

### New (mirrors source repo) — 17 files

**Spawn contract + tier env (4):**
- `commands/vg/_shared/lib/gemini-spawn.sh` (parallel codex-spawn.sh)
- `commands/vg/_shared/gemini-spawn-contract.md` (parallel codex-spawn-contract.md, with AskUserQuestion fallback documented)
- `scripts/lib/gemini_vg_env.py` (tier env builder)
- `scripts/gemini-spawn-record.py` (evidence recorder)

**Hook lifecycle (3) — Codex precedent: 5 events, no SessionStart:**
- `scripts/gemini-hooks-install.py` (parallel codex-hooks-install.py — registers 5 hook events)
- `scripts/lib/vg_gemini_hook_lib.py` (parallel vg_codex_hook_lib.py — adapter translation)
- `.claude/scripts/gemini-hooks/` directory: 5 hook scripts (pre-bash, post-bash, pre-edit, stop, user-prompt-submit). Note: file edit hook is **thin wrapper** delegating to existing `vg-pre-tool-use-write.sh` — Gemini CLI has native Read/Write/Edit (no apply_patch fork needed)

**MCP template (1):**
- `templates/gemini/config.template.toml` (operator-managed MCP servers, parallel templates/codex/)

**Skill mirror generation (3):**
- `gemini-skills/vg-review/SKILL.md` (generated from `commands/vg/review.md` + `<gemini_skill_adapter>`)
- `gemini-skills/_shared/review/*` (review sub-step adapters)
- `scripts/generate-gemini-skills.sh` (parallel codex generator)

**Validators + tests (5):**
- `scripts/verify-gemini-mirror-equivalence.py` (SHA256 body parity)
- `scripts/validators/verify-scanner-output-schema.py` (post-spawn JSON validator — defense for Flash schema drift)
- `scripts/tests/test_gemini_spawn_parity.py`
- `scripts/tests/test_gemini_runtime_branching.py`
- `scripts/tests/test_gemini_tier_env_builder.py`
- `scripts/tests/test_gemini_hook_install.py`
- `scripts/tests/test_gemini_tasklist_adapter.py`

**A/B harness + docs (1):**
- `scripts/lab/gemini-ab-harness.py` (Claude vs Gemini comparison tool)
- `docs/audits/2026-05-?-gemini-review-rollout.md` (rollout note)

### Modified (6 sites — match Codex precedent + 1 TodoWrite adapter)

- `scripts/hooks/vg-user-prompt-submit.sh:12` (add `gemini)` case)
- `scripts/hooks/vg-pre-tool-use-bash.sh:429,531` (add `gemini)` case)
- `scripts/vg-orchestrator/__main__.py:125` (add `is_gemini_runtime` detection)
- `scripts/vg-orchestrator/__main__.py:cmd_tasklist_projected` (add `gemini` adapter case — orchestrator signs evidence directly when adapter=gemini, mirroring codex compact-plan pattern)
- `commands/vg/_shared/lib/block-resolver.sh:34-48` (add `gemini` to `block_resolver_runtime()`)
- `commands/vg/review.md:954,968` (add `gemini)` case in scanner variant selection)

### Generated mirrors (after `generate-gemini-skills.sh` run)

- `.gemini/skills/vg-review/SKILL.md` (+ subskills)
- `.gemini/skills/_shared/review/*`
- `.gemini/agents/` (3 minimal configs: scanner, executor, adversarial — schema TBD per Open Question 1)

### Unchanged (KEY architectural win — Gemini wins on file-edit primitive)

- `scripts/hooks/vg-pre-tool-use-write.sh` — covers all 3 runtimes (Claude / Codex / Gemini) uniformly. Gemini CLI has native Read/Write/Edit, so no apply_patch fork like Codex. Existing protected-path block applies as-is.

---

## Open Questions (defer to implementation)

1. **`.gemini/agents/` schema** — Codex uses TOML, Claude uses Markdown with embedded `Agent(...)`. Gemini CLI doesn't have native subagent contract — likely YAML config + spawn invocation pattern. Defer to Task 4.

2. **MCP Playwright handoff** — Step 2a + 2b need browser. Gemini CLI has MCP support (`~/.gemini/settings.json` mcp config). Verify Playwright MCP server connects from Gemini session same as Claude session. Defer to Task 16 (smoke test).

3. **Stdin piping confirmation** — Research found `gemini -p "..."` works but stdin pipe (`cat brief | gemini -p ...`) not explicitly documented. PV3 vg.config.md uses pipe pattern, suggesting it works — verify in Task 5.

4. **AskUserQuestion fallback UX** — Gemini CLI lacks batched multi-choice tool. Pattern (matches Codex precedent):
   - Interactive mode: sequential stdin reads (1 question at a time)
   - Non-interactive: CLI flags (`--target-env=X --model=Y --mode=Z`) bypass batch
   - Paste-prompt mode: generate `INSTRUCTION.md` for external execution
   Document trade-off in `gemini-spawn-contract.md`. Operator accepts UX regression.

5. **Hook lifecycle adapter translation** — Codex hooks use `vg_codex_hook_lib.py:102-151` to translate Claude format `{"decision":"approve"}` ↔ Codex format `{"continue":true}`. Gemini CLI hook output schema unknown — research needed in Task 8.

6. **Cost cap** — Pro 3.1 at $4/M (>200K input) can spike. Defer cost cap mechanism to Plan G2 (post-G1 hardening).

7. **9router proxy reliability** — operator uses `cx/`/`gc/` prefixes via 9router. SLO/fallback chain when proxy degrades. Defer to operator runbook.

---

## Success Criteria

**Runtime infrastructure:**
- `gemini` runtime branch added to 6 sites without changing Claude default behavior (test: `VG_RUNTIME` unset still routes to Claude path)
- 5 hook events installed for Gemini (PreToolUse-Bash, PreToolUse-FileEdit, PostToolUse-Bash, Stop, UserPromptSubmit) — SessionStart skipped (matches Codex precedent)
- `cmd_tasklist_projected --adapter gemini` signs evidence directly without TodoWrite call (compact-plan pattern)
- `gemini-spawn.sh --tier scanner` produces evidence file at `.vg/runs/<run_id>/gemini-spawns/<id>.json` with valid schema
- `templates/gemini/config.template.toml` documents MCP server setup for Playwright
- AskUserQuestion fallback documented in spawn contract (sequential stdin / CLI flags / paste-prompt)

**Skill mirror:**
- `.gemini/skills/vg-review/SKILL.md` SHA256 body equivalent to `commands/vg/review.md` source body (after strip adapter, normalize whitespace)
- `<gemini_skill_adapter>` block maps Agent → gemini-spawn.sh, MCP → main session, file-edit → native tools

**Test coverage (~20 new tests):**
- `test_gemini_spawn_parity.py` — heavy spawn sites have gemini-spawn.sh markers in `.gemini/skills/`
- `test_gemini_runtime_branching.py` — 6 sites correctly branch on `VG_RUNTIME=gemini`
- `test_gemini_tier_env_builder.py` — `gemini_vg_env.py` produces correct tier env vars
- `test_gemini_hook_install.py` — installer registers 5 events
- `test_gemini_tasklist_adapter.py` — orchestrator signs evidence in gemini-adapter case

**Smoke test on PV3 phase 4.3:**
- `VG_RUNTIME=gemini /vg:review 4.3` completes end-to-end without manual intervention
- Hook events fire (verify in events.db: count(`vg.runtime=gemini`) > 0)
- Browser MCP Playwright connects from Gemini session

**A/B validation (separate harness, post-ship):**
- `scripts/lab/gemini-ab-harness.py` runs Claude vs Gemini on same phase
- Gemini findings recall ≥ 90% of Claude baseline
- False-positive rate ≤ 110%
- Total run cost ≤ 60% of Claude baseline

---

## Spec self-review

- ✅ **Placeholders:** none ("TBD"/"TODO" not present); 7 open questions explicitly labeled as deferred.
- ✅ **Internal consistency:** 5 architectural patterns × 6 primitives × 6 modified sites — all 1:1 mapped to Codex audit findings.
- ✅ **Scope check:** Pipeline target is /vg:review only; runtime infrastructure is full primitive parity (necessary for /vg:review to function — reusable for /vg:test, /vg:accept ports later).
- ✅ **Ambiguity check:** "scanner" tier = report-only contract (Haiku replacement); "executor" tier = code generation (small scope only); "probe" optional cheap tier; "adversarial" tier = CrossAI critic; "planner" tier reserved for future — explicit boundaries.
- ✅ **Primitive coverage:** All 6 Claude primitives (hooks, TodoWrite, AskUserQuestion, Agent spawn, MCP, file edit) explicitly mapped to Gemini implementation strategy.

---

**Status:** Ready for implementation planning via `superpowers:writing-plans` (~20-task split, ~6-8 ngày effort).
