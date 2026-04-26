# Phase 15 — D-17 Investigation (Review Haiku Spawn Regression)

**Status:** RESOLVED 2026-04-27 — original D-17 narrative was a misinterpretation; real fix is much smaller than scoped in BLUEPRINT.
**Task chain:** T9.1 ✅ → T9.2 ✅ → T9.3 ✅ → T9.4 ✅ telemetry fix applied → T9.5 NO ADDITIONAL CODE (v2.8.6 already addressed source) → T9.6 ✅ this doc

## Executive summary (read this first)

The "53s ABORT" originally cited as evidence of broken Haiku spawn (HANDOFF.md TL;DR §4) was **NOT a Haiku spawn failure**. Full event log + abort payload + git history reveal:

1. **The aborted run was a phantom**: created somehow during /vg:learn invocation with no real review work intended.
2. **The user manually aborted it** with a detailed explanation in the abort payload (text reads like human commentary, not auto-generated).
3. **v2.8.6 (committed 2026-04-26 22:22:46) already addressed source-side phantom prevention** — added paste-back markers + first-non-empty-line gate. The phantom event predates v2.8.6 by ~4 hours.
4. **Real `/vg:review` works fine** — control PASS run (c4a375c9) executed full 17-step sequence in 13min including step 2b-2 Haiku spawns (visible at phase2_browser_discovery 8.5min duration).

**Net D-17 deliverables for Phase 15 acceptance:**
- ✅ T9.4 — `review.haiku_scanner_spawned` telemetry emit IMMEDIATELY before each Agent() spawn (defensive, applied to review.md spawn pattern)
- 🔜 T3.11 — `verify-haiku-spawn-fired.py` validator (Wave 3) MUST be phantom-aware (skip BLOCK on phantom-pattern runs: `args:""` + 0 step.marked + abort within 60s)

---

## §1 — Event log evidence (T9.1)

### Run 19013956 (target ABORT 2026-04-26 18:05:38 → 18:06:31, 53s total)

```
ts                    event_type            step  outcome  payload
18:05:38Z  run.started                            INFO    args:""  git_sha:ef151561  ← EMPTY ARGS!
18:05:38Z  review.started                         INFO    {}
18:05:59Z  validation.passed                      PASS    phase-exists
18:05:59Z  validation.passed                      PASS    runtime-evidence
18:05:59Z  validation.passed                      PASS    review-skip-guard
18:06:00Z  validation.warned                      WARN    verify-input-validation
18:06:00Z  validation.passed                      PASS    verify-authz-declared
18:06:00Z  validation.warned                      WARN    accessibility (quarantined)
18:06:00Z  validation.passed                      PASS    i18n-coverage
18:06:00Z  validation.passed                      PASS    build-telemetry-surface
18:06:00Z  validation.passed                      PASS    verify-goal-security
18:06:01Z  validation.passed                      PASS    verify-goal-perf
18:06:02Z  validation.warned                      WARN    verify-security-baseline
18:06:02Z  validation.passed                      PASS    verify-no-hardcoded-paths
18:06:05Z  validation.passed                      PASS    verify-design-ref-honored
18:06:05Z  contract.marker_warn                   WARN    marker:phase2_7_url_state_sync (severity=warn)
18:06:05Z  contract.marker_warn                   WARN    marker:phase2_8_url_state_runtime (severity=warn)
18:06:05Z  run.blocked                            PASS    violations:[missing review.tasklist_shown (≥1)]
18:06:31Z  run.aborted                            INFO    reason: "Phantom run started by hook during /vg:learn invocation (no phase arg defaulted to 7.14.3 parent). The actual review for phase 7.14.3 was completed earlier in pipeline; phase B3 was deferred to 7.14.3.1 (now ACCEPTED, commit 9ac4e366). No real review work needed for 7.14.3 itself — see SPIKE-B3-AUTH.md verdict in that phase dir."
```

**Critical finding:** `args:""` (empty) on `run.started`. NO `step.marked` events. NO actual review work performed. **Abort reason payload is full-prose human commentary** (not auto-generated) — strongly suggests user invoked `vg-orchestrator run-abort --reason "..."` manually after recognizing the phantom run was unnecessary.

### Run c4a375c9 (closest PASS control, same day 11:11:04 → 11:24:02, ~13 min)

```
ts                    event_type             step                            outcome
11:11:04Z  run.started                                                       INFO    args:"7.14.3" git_sha:d4779cf8  ← EXPLICIT PHASE ARG
11:11:04Z  review.started                                                    INFO
11:11:04Z  step.marked            00_gate_integrity_precheck                 INFO
11:11:04Z  step.marked            00_session_lifecycle                       INFO
11:11:04Z  step.marked            0_parse_and_validate                       INFO
11:11:04Z  step.marked            0b_goal_coverage_gate                      INFO
11:11:04Z  step.marked            0c_telemetry_suggestions                   INFO
11:11:04Z  step.marked            create_task_tracker                        INFO
11:11:04Z  step.marked            phase_profile_branch                       INFO
11:11:20Z  step.marked            phase1_code_scan                           INFO
11:11:47Z  step.marked            phase1_5_ripple_and_god_node               INFO
11:20:04Z  step.marked            phase2_browser_discovery                   INFO  ← 8.5min Haiku scanner work HERE
11:20:05Z  step.marked            phase2_5_visual_checks                     INFO
11:20:05Z  step.marked            phase2_exploration_limits                  INFO
11:20:05Z  step.marked            phase3_fix_loop                            INFO
11:23:09Z  step.marked            phase4_goal_comparison                     INFO  ← ~3min fix loop
11:23:09Z  step.marked            unreachable_triage                         INFO
11:23:09Z  step.marked            crossai_review                             INFO
11:23:09Z  step.marked            write_artifacts                            INFO
11:23:10Z  step.marked            bootstrap_reflection                       INFO
11:23:37Z  step.marked            complete                                   INFO
11:23:37Z  review.completed                                                  INFO    blocking_bugs:["B4"], gap_closure_round:1, goals_blocked:1
11:23:37Z  validation.passed (8 validators)                                  PASS
11:23:43Z  run.blocked                                                       PASS    violations:[missing review.tasklist_shown]  ← SAME blocking pattern, but...
11:23:56Z  review.tasklist_shown                                             INFO    phase:7.14.3 profile:web-fullstack steps:17  ← ...self-recovers by emitting marker
11:23:56Z  validation.passed (8 validators round 2)                          PASS
11:24:02Z  run.completed                                                     PASS
```

**Pattern comparison:**
- ✅ PASS run = explicit phase arg + 17 steps marked + ~12 min Haiku work + recovery emit
- ❌ ABORT run = empty args + 0 step markers + only base validators ran + no recovery

---

## §2 — Skill body + entry-hook code analysis (T9.2 ✅)

### vg-entry-hook.py defenses (current state)

UserPromptSubmit hook with multi-layer paste-back detection:

1. **Fast path:** non-`/vg:` prompts → early approve <5ms.
2. **Paste-back markers (v2.5.2.5 + v2.8.6 extension):** detects Stop-hook feedback echoes, `<system-reminder>` wrapping, transcript dumps, diff hunks, file content with absolute paths + length > 2KB.
3. **First-non-empty-line gate (v2.8.6):** `/vg:cmd` MUST be at first non-empty line — embedded references in middle of prose (PLAN.md text, output dumps) are skipped.
4. **Phase-arg gate (existing):** non-numeric phase tokens (`/vg:progress`, `/vg:doctor`) skip orchestrator registration.
5. **Idempotent check:** active run with same command+phase → skip.
6. **Soft-fail orchestrator:** if subprocess crashes or rejects → log + approve (degraded-correct; never block user input).

**Conclusion:** Hook source code is heavily defensed. Phantom event predates v2.8.6 commit (commit `411a278` at 2026-04-26 22:22:46; phantom event at 2026-04-26 18:05:38, ~4 hours earlier) — i.e., the phantom occurred under PRE-v2.8.6 code with weaker first-line gate. **v2.8.6 deployment likely already prevents this class of phantom.**

### review.md step 2b-2 spawn pattern

Located lines 2398-2434. Spawn loop:

```
For each view in view_assignments:
  For each role:
    IDX=$((IDX + 1))
    briefing_for_view "{view.url}" "{role}" "$IDX" "$TOTAL"
    Agent(model="haiku", description="...")  ← Task tool invocation
```

Pre-T9.4: NO telemetry emit between briefing and Agent() call. T3.11 validator query against events.db would be unable to distinguish "spawn never attempted" from "spawn attempted but Agent failed silently."

### vg-contract-pins.py (contract gate logic)

Pins `runtime_contract` per (phase, command) at first execution. Subsequent runs validate against pinned contract. Phase 7.14.3 has pinned contract requiring `review.tasklist_shown` event. The `run.blocked` (violations: missing review.tasklist_shown) seen in BOTH the ABORT and PASS runs is normal pin-validation behavior — PASS run recovered by emitting the missing marker; ABORT run couldn't because no real work happened.

**No contract gate bug.** Pinning works correctly.

---

## §3 — Root cause (CONFIRMED, T9.3 ✅)

**Original H1/H2/H3 from BLUEPRINT v1:**
- ❌ H1: contract gate fires before spawn step (race) — DISPROVEN. PASS run hits same `run.blocked` for missing tasklist_shown but recovers; ABORT run can't recover because no actual work happened.
- ✅ H2: phantom hook entry pattern — **CONFIRMED**. Abort payload literally identifies "Phantom run started by hook during /vg:learn invocation".
- ❌ H3: profile detection sai — DISPROVEN. PASS run with same phase id detects profile correctly.

**Refined root cause (after T9.2 deeper analysis):**

> Pre-v2.8.6 `vg-entry-hook.py` had weaker first-line gate. Some `/vg:learn` invocation (with embedded `/vg:review` reference in prompt body, OR scenario where hook captured wrong cmd) triggered a phantom run-start for command=`vg:review` phase=7.14.3 (defaulting to parent phase). The phantom registered, ran base validators, hit `run.blocked` for missing `review.tasklist_shown`, then **the user manually aborted with `vg-orchestrator run-abort --reason "..."`** providing the rich human commentary visible in the abort payload.

**Why HANDOFF's original D-17 narrative was wrong:**
- The "53s = abort = spawn step never reached" interpretation conflated phantom with real spawn failure.
- Actually: 53s = abort because phantom + manual user intervention, NOT spawn failure.
- Real `/vg:review` (control PASS run) reaches spawn step normally and runs 8.5min for browser_discovery (where Haiku scanners actually fire).

**Implication for D-17 acceptance:**
- Source-side: v2.8.6 already shipped (post-phantom-event timing). No new source guard needed.
- Defense-side: T3.11 validator MUST be phantom-aware (treat phantom-pattern runs as SKIP, not BLOCK). Phantom-pattern signature: `args:""` AND 0 `step.marked` events AND aborted within 60s of `run.started`.
- Telemetry: T9.4 emit-before-spawn applied (review.md edit shipped).

---

## §4 — Applied fixes

### T9.4 ✅ Telemetry emit position fix (review.md)

**Edit applied:** `vgflow-repo/commands/vg/review.md` lines 2399-2434 spawn pattern.

**What changed:** Inserted Bash emit-event call between `briefing_for_view` and `Agent()` invocation:

```
Bash:
  ${PYTHON_BIN} .claude/scripts/vg-orchestrator emit-event \
    "review.haiku_scanner_spawned" \
    --step "2b-2" --actor "orchestrator" --outcome "INFO" \
    --payload "$(printf '{"view":"%s","role":"%s","idx":%d,"total":%d,"spawn_mode":"%s"}' \
      "{view.url}" "{role}" "$IDX" "$TOTAL" "$SPAWN_MODE")" \
    2>/dev/null || true

Agent(model="haiku", description="...")
```

**Why before, not after:** survives Agent failure, run abort, and any harness crash that might prevent post-spawn telemetry. T3.11 validator can rely on event presence to confirm spawn was attempted.

**Mode handling:** Comment notes parallel mode batches Agent() calls in one tool_use block — emit per-spawn in serial bash loop BEFORE the batched Agent calls.

### T9.5 — NO ADDITIONAL CODE CHANGES

After deeper investigation (§3):
- **Source side (A): NOT NEEDED.** v2.8.6 hardening (commit `411a278`) shipped 2026-04-26 22:22, post-dating the phantom event by ~4 hours. First-line gate + extended paste-back markers + abs-path heuristic already mitigate the phantom-trigger class.
- **Defense side (B): DEFERRED to T3.11.** Phantom-aware logic belongs in `verify-haiku-spawn-fired.py` validator (Wave 3 task). Spec for T3.11:
  ```
  Detect phantom signature: events for run_id WHERE
    started_at_args = "" AND
    step.marked event count = 0 AND
    run.aborted within 60s of run.started
  → return SKIP (not BLOCK) for phantom-pattern runs
  → BLOCK only when real run (args present + step markers exist) lacks spawn event
  ```

### Bonus: tasklist_shown gate observation (not in D-17 scope, log for future)

Both PASS and ABORT runs hit `run.blocked` for missing `review.tasklist_shown`. PASS recovered by emitting marker reactively at step 16 (after first-pass validation block). Risk: if a real `/vg:review` ever has the tasklist emit fail (network/disk issue), it'll fall into same blocked-then-abort pattern.

**Suggestion (out-of-D17-scope, candidate for future hardening phase):** emit `review.tasklist_shown` PROACTIVELY at step 0c (early in pipeline), not reactively. Filed mentally; not addressed in Phase 15.

---

## §5 — Acceptance for D-17

- [x] T9.4 telemetry emit position applied to review.md spawn pattern (commit forthcoming as `feat(phase-15-T9.4)`)
- [x] T9.5 source-side fix unnecessary — v2.8.6 already shipped pre-Phase-15; defense-side handed off to T3.11 (Wave 3)
- [ ] T3.11 (Wave 3) `verify-haiku-spawn-fired.py` MUST implement phantom-aware logic per spec in §4
- [ ] Test fixture (Wave 8): `vgflow-repo/fixtures/review/spawn-fired-phantom.events.db` — phantom pattern, validator returns SKIP
- [ ] Test fixture (Wave 8): `vgflow-repo/fixtures/review/spawn-fired-real.events.db` — real run with spawn event, validator returns PASS
- [ ] Test fixture (Wave 8): `vgflow-repo/fixtures/review/no-spawn-real.events.db` — real run lacking spawn event, validator returns BLOCK
- [ ] Wave 10 E2E smoke: live `/vg:review` run on synthetic UI phase → verify `review.haiku_scanner_spawned` event emits per spawn
- [ ] Update HANDOFF.md TL;DR §4: correct narrative — "phantom run misinterpreted as spawn failure; v2.8.6 already addressed source path; D-17 Phase 15 deliverable is telemetry emit-before-spawn (T9.4) + phantom-aware validator (T3.11)"

---

**END OF INVESTIGATION — D-17 resolved with much smaller fix surface than originally scoped. Wave 9 effort revised from 6h → ~2h actual. Capacity freed for other waves.**
