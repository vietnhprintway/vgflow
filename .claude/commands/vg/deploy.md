---
name: vg:deploy
description: Standalone deploy skill — multi-env (sandbox/staging/prod), writes deployed.{env} block to DEPLOY-STATE.json. Optional step between /vg:build and /vg:review/test/roam. Suggestion-only consumers downstream — this skill produces the data; runtime gates use it to recommend env via enrich-env-question.py.
argument-hint: "<phase> [--envs=sandbox,staging,prod] [--all-envs] [--dry-run] [--non-interactive] [--prod-confirm-token=DEPLOY-PROD-{phase}] [--allow-build-incomplete] [--pre-test]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
  - TodoWrite
runtime_contract:
  must_write:
    - "${PHASE_DIR}/DEPLOY-STATE.json"
  must_touch_markers:
    - "0_parse_and_validate"
    - "0a_env_select_and_confirm"
    - "1_deploy_per_env"
    - "2_persist_summary"
    - "complete"
  must_emit_telemetry:
    - event_type: "phase.deploy_started"
      phase: "${PHASE_NUMBER}"
    - event_type: "phase.deploy_completed"
      phase: "${PHASE_NUMBER}"
    # Task 44b — tasklist projection enforcement (Bug L)
    - event_type: "deploy.tasklist_shown"
      phase: "${PHASE_NUMBER}"
    - event_type: "deploy.native_tasklist_projected"
      phase: "${PHASE_NUMBER}"
    - event_type: "deploy.tasklist_projection_skipped"
      phase: "${PHASE_NUMBER}"
      severity: "warn"
    - event_type: "deploy.tasklist_evidence_run_mismatch"
      phase: "${PHASE_NUMBER}"
      severity: "warn"
    - event_type: "deploy.tasklist_depth_invalid"
      phase: "${PHASE_NUMBER}"
      severity: "warn"
    - event_type: "deploy.tasklist_block_handled_unresolved"
      phase: "${PHASE_NUMBER}"
      severity: "warn"
  forbidden_without_override:
    - "--allow-build-incomplete"
---

<HARD-GATE>
You MUST follow STEP 0 through `complete` in exact order. Each step is gated
by hooks. Skipping ANY step will be blocked by PreToolUse + Stop hooks.

You MUST call TodoWrite IMMEDIATELY after STEP 0 (`0_parse_and_validate`)
runs `emit-tasklist.py` — DO NOT continue without it. The PreToolUse Bash
hook will block all subsequent step-active calls until signed evidence
exists at `.vg/runs/<run_id>/.tasklist-projected.evidence.json`. The
PostToolUse TodoWrite hook auto-writes that signed evidence.

TodoWrite MUST include sub-items (`↳` prefix) for each group header;
flat projection (group-headers only) is rejected by the PostToolUse
depth check (Task 44b Rule V2 — `depth_valid=false` evidence triggers
the PreToolUse depth gate).
</HARD-GATE>

<rules>
1. **Build must be complete** — PIPELINE-STATE.steps.build.status ∈ {accepted, tested, reviewed, built-with-debt, built-complete}. Otherwise BLOCK (override: `--allow-build-incomplete` logs override-debt).
2. **Multi-env supported, sequential execution** — each env runs after the previous completes. Parallel would risk infrastructure contention (shared SSH connection, same DB seed, etc).
3. **Prod requires explicit confirmation** — separate AskUserQuestion 3-option danger gate (PROCEED / NON-PROD-ONLY / ABORT). For non-interactive runs, `--prod-confirm-token=DEPLOY-PROD-{phase}` must match exactly.
4. **Per-env failure handling** — DOES NOT auto-abort remaining envs. Ask user continue/skip-failed/abort-all. Failed env writes `health: "failed"` + error log.
5. **DEPLOY-STATE.json merges** — preserves `preferred_env_for` (set by /vg:scope step 1b), `preferred_env_for_skipped` flag, and any unrelated future keys. Only `deployed.{env}` block is rewritten per run.
6. **Rollback hint** — capture `previous_sha` from existing `deployed.{env}.sha` BEFORE overwriting. Future `/vg:rollback` consumer reads this.
7. **--dry-run** prints commands but doesn't execute. Useful for verifying config + flags before real deploy.
</rules>

<objective>
Standalone optional skill bridging /vg:build → /vg:review/test/roam. User
runs `/vg:deploy <phase>` after build, picks one or more envs, this skill
runs the canonical deploy sequence per env (build → restart → health) on
that target, captures SHA + timestamp + health into
`${PHASE_DIR}/DEPLOY-STATE.json` `deployed.{env}` block.

Downstream env gates (review/test/roam step 0a) read this state via
`enrich-env-question.py` (B1) and surface "deployed Nmin ago, sha XXXX"
evidence in the AskUserQuestion options. The pipeline becomes:

```
specs → scope → blueprint → build → [DEPLOY] → review → test → [roam] → accept
                                       ↑                  ↑      ↑       ↑
                                   writes              all read DEPLOY-STATE
                                   DEPLOY-STATE        for env recommendation
```

This skill never auto-picks env at runtime gates — those still fire
AskUserQuestion. /vg:deploy just feeds the suggestion data layer.
</objective>

<process>

### Preflight section (extracted v2.73.0 T1)

Read `_shared/deploy/preflight.md` and follow it exactly.
Includes 2 steps: 0_parse_and_validate, 0a_env_select_and_confirm.

### Execute per-env (extracted v2.73.0 T2)

Read `_shared/deploy/execute.md` and follow it exactly.
Includes 1 step: 1_deploy_per_env.

<step name="2_persist_summary">
## Step 2 — Merge results into DEPLOY-STATE.json + summary

Merge per-env results into `${PHASE_DIR}/DEPLOY-STATE.json` `deployed.{env}`
block. Preserves `preferred_env_for` / `preferred_env_for_skipped` and any
unrelated future keys. Print summary table + emit telemetry. Merge logic
lives in `scripts/vg-deploy-merge-summary.py` (extracted from this slim
entry per shared-build pattern).

```bash
MERGE_OUT=$(${PYTHON_BIN:-python3} .claude/scripts/vg-deploy-merge-summary.py \
  --phase "${PHASE_NUMBER}" --phase-dir "${PHASE_DIR}" \
  --results-json "${DEPLOY_RESULTS_JSON}")
echo "$MERGE_OUT" | grep -v '^RESULT_PAYLOAD='
RESULT_PAYLOAD=$(echo "$MERGE_OUT" | grep '^RESULT_PAYLOAD=' | head -1 | sed 's/^RESULT_PAYLOAD=//')

if echo "$RESULT_PAYLOAD" | grep -q '"failed_envs": \[\]'; then
  EVENT_TYPE="phase.deploy_completed"; OUTCOME="PASS"
else
  EVENT_TYPE="phase.deploy_failed"; OUTCOME="WARN"
fi

${PYTHON_BIN:-python3} .claude/scripts/vg-orchestrator emit-event \
  "$EVENT_TYPE" --actor "orchestrator" --outcome "$OUTCOME" \
  --payload "$RESULT_PAYLOAD" 2>/dev/null || true
[ "$EVENT_TYPE" != "phase.deploy_completed" ] && ${PYTHON_BIN:-python3} .claude/scripts/vg-orchestrator emit-event \
  "phase.deploy_completed" --actor "orchestrator" --outcome "INFO" \
  --payload "$RESULT_PAYLOAD" 2>/dev/null || true

(type -t mark_step >/dev/null 2>&1 && mark_step "${PHASE_NUMBER}" "2_persist_summary" "${PHASE_DIR}") || touch "${PHASE_DIR}/.step-markers/2_persist_summary.done"
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step deploy 2_persist_summary 2>/dev/null || true
```
</step>

### Post-deploy reflector trigger (Section 13.5 / meta-memory v1.1)

After `phase.deploy_completed` emits, spawn vg-reflector subagent IF
`meta_memory_mode != "disabled"`:

```bash
# Check rollout flag
META_MEMORY_MODE=$(grep -E "^meta_memory_mode:" vg.config.md 2>/dev/null | awk '{print $2}' || echo "disabled")

if [ "$META_MEMORY_MODE" != "disabled" ] && [ "$EVENT_TYPE" = "phase.deploy_completed" ]; then
  # Narrate spawn (orchestrator UX baseline R2)
  bash scripts/vg-narrate-spawn.sh vg-reflector spawning "post-deploy candidate draft"

  # Emit telemetry that reflector trigger was requested
  ${PYTHON_BIN:-python3} .claude/scripts/vg-orchestrator emit-event \
    "reflection.trigger_requested" --actor "deploy" --outcome "INFO" \
    --metadata "{\"step\":\"deploy\",\"phase\":\"${PHASE_NUMBER}\",\"trigger\":\"post-deploy\"}"

  # Note: actual subagent spawn is performed by the agent that owns this run.
  # This snippet only marks the event; orchestrator/skill flow handles dispatch.
fi
```

**Inputs to reflector:**
- `events.db` query: `deploy.{started,completed,failed}` for current phase
- `${PHASE_DIR}/DEPLOY-STATE.json` `deployed.{env}` block
- `${PHASE_DIR}/.deploy-log.{env}.txt` per env stdout
- `vg.config.md` env list, deploy commands, package manager

**Candidate target:** `target_step=deploy`, `type=procedural`.

**Fingerprint:** `hash(repo_id + deploy_target + health_cmd + env + commands + dockerfile_hash + package_manager)`.

<step name="complete">
## Final — mark + run-complete

Before `run-complete`, close the native tasklist:
- Claude Code: mark every deploy checklist item completed via `TodoWrite`,
  then clear the list if supported; otherwise replace it with one completed
  sentinel: `vg:deploy phase ${PHASE_NUMBER} complete`.
- Codex CLI: update the compact plan to completed/sentinel so no previous
  workflow list remains visible.

```bash
(type -t mark_step >/dev/null 2>&1 && mark_step "${PHASE_NUMBER}" "complete" "${PHASE_DIR}") || touch "${PHASE_DIR}/.step-markers/complete.done"
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step deploy complete 2>/dev/null || true
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator run-complete 2>&1 | tail -1 || true
```
</step>

</process>

<success_criteria>
- Build prereq ok (or debt), selected envs exist, prod confirmed by AskUserQuestion or token.
- Env commands run sequentially; health retries 30s; failed env does not auto-abort siblings.
- DEPLOY-STATE.json merges `deployed.{env}`, preserves `preferred_env_for`, captures `previous_sha`.
- `phase.deploy_completed` telemetry emits; `${PHASE_DIR}/.deploy-log.{env}.txt` exists per env.
</success_criteria>
