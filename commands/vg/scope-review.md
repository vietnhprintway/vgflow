---
name: vg:scope-review
description: Cross-phase scope validation — detect conflicts, overlaps, and gaps across all scoped phases
argument-hint: "[--skip-crossai] [--phases=7.6,7.8,7.10] [--full]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
mutates_repo: true
runtime_contract:
  must_emit_telemetry:
    - event_type: "scope_review.started"
    - event_type: "scope_review.completed"
---

<rules>
1. **VG-native** — no GSD delegation. This command is self-contained.
2. **Config-driven** — read .claude/vg.config.md for project paths, profile, models.
3. **Run AFTER scoping, BEFORE blueprint** — this is a cross-phase gate between scope and blueprint.
4. **Automated checks first** — 5 deterministic checks run before any AI review.
5. **DISCUSSION-LOG.md is APPEND-ONLY** — never overwrite, never delete existing content.
6. **Resolution is interactive** — conflicts and gaps require user decision, not AI auto-fix.
7. **Minimum 2 phases** — warn (not block) if only 1 phase scoped.
8. **Incremental by default (tăng cường theo delta)** — scope is narrowed to changed + new + dependent phases via `${PLANNING_DIR}/.scope-review-baseline.json`. Use `--full` for complete rescan (mốc gốc — full baseline rebuild).
</rules>

<objective>
Cross-phase scope validation gate. Run after scoping all (or multiple) phases, before starting blueprint on any of them.
Detects decision conflicts, module overlaps, endpoint collisions, dependency gaps, and scope creep across phases.

Output: ${PLANNING_DIR}/SCOPE-REVIEW.md (report with gate verdict)

Pipeline position: specs -> scope -> **scope-review** -> blueprint -> build -> review -> test -> accept
</objective>

<process>

**Config:** Read .claude/commands/vg/_shared/config-loader.md first. Use config variables ($PLANNING_DIR, $PHASES_DIR).

### Preflight section (extracted v2.74.0 T1)

Read `_shared/scope-review/preflight.md` and follow it exactly.
Includes 2 steps: 0_parse_and_collect, incremental_check.

Step coverage: 0_parse_and_collect, incremental_check.


### Cross-ref + review + write (extracted v2.74.0 T2)

Read `_shared/scope-review/cross-ref-review-write.md` and follow it exactly.
Includes 3 steps: 1_cross_reference, 2_crossai_review, 3_write_report.

Step coverage: 1_cross_reference, 2_crossai_review, 3_write_report.


<step name="4_resolution">
## Step 4: RESOLUTION (if BLOCK)

If gate status is BLOCK, for each blocking issue:

```
AskUserQuestion:
  header: "Resolve: {issue_id} — {short description}"
  question: |
    **Issue:** {full description}
    **Phase A:** {phase} — {decision}
    **Phase B:** {phase} — {decision}
    **Recommendation:** {AI recommendation}

    How to resolve?
  options:
    - "Update Phase A scope — will need /vg:scope {phase_a} to re-discuss"
    - "Update Phase B scope — will need /vg:scope {phase_b} to re-discuss"
    - "Add dependency — update ROADMAP.md with ordering constraint"
    - "Accept as-is — mark as acknowledged risk"
```

Track resolutions:
- "Update Phase X" -> note which phases need re-scoping, suggest commands at end
- "Add dependency" -> append dependency note to ROADMAP.md (if exists)
- "Accept as-is" -> mark issue as "acknowledged" in SCOPE-REVIEW.md, downgrade from BLOCK

**After all resolutions:**
Re-evaluate gate. If all blocking issues resolved (updated scope or acknowledged):
- Update SCOPE-REVIEW.md gate status to PASS (with "acknowledged" notes)
- If any phases need re-scoping, do NOT auto-pass — list them:
  ```
  Gate conditionally PASS. Phases requiring re-scope:
    - /vg:scope {phase_a} (conflict C-01)
    - /vg:scope {phase_b} (gap DG-02)

  After re-scoping, run /vg:scope-review again to verify.
  ```
</step>

<step name="4.5_baseline_write_and_telemetry">
## Step 4.5: WRITE BASELINE + TELEMETRY (baseline = mốc gốc)

After gate verdict settles (PASS, conditional PASS, or even BLOCK — baseline always reflects current disk state so next incremental run has accurate delta), write the updated baseline:

```bash
# Count conflicts detected (sum across checks A..E)
CONFLICTS_FOUND=$(( ${CHECK_A_COUNT:-0} + ${CHECK_C_COUNT:-0} + ${CHECK_D_COUNT:-0} ))

# Write baseline atomically (via .tmp + mv)
BASELINE_PATH="${PLANNING_DIR}/.scope-review-baseline.json"
BASELINE_TMP="${BASELINE_PATH}.tmp"

${PYTHON_BIN:-python3} - "$PHASES_DIR" "$BASELINE_TMP" <<'PY'
import json, hashlib, sys, re, datetime
from pathlib import Path

phases_dir = Path(sys.argv[1])
out_path = Path(sys.argv[2])

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def phase_id(name):
    m = re.match(r'^0*([0-9]+(?:\.[0-9]+)*)', name)
    return m.group(1) if m else name

phases = {}
for d in sorted(phases_dir.iterdir()):
    if not d.is_dir(): continue
    ctx = d / "CONTEXT.md"
    if not ctx.exists(): continue
    pid = phase_id(d.name)
    phases[pid] = {
        "context_sha256": sha(ctx),
        "spec_sha256": sha(d / "SPECS.md"),
    }

baseline = {
    "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "phases": phases,
}
out_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"✓ Baseline staged: {len(phases)} phases")
PY

mv "$BASELINE_TMP" "$BASELINE_PATH"
echo "✓ Baseline (mốc gốc) written: ${BASELINE_PATH}"

# Emit telemetry for incremental gate hit
# Reference: .claude/commands/vg/_shared/telemetry.md (emit_telemetry_v2)
if type emit_telemetry_v2 >/dev/null 2>&1; then
  emit_telemetry_v2 "gate_hit" "" "scope-review.incremental" \
    "scope-review-incremental" "PASS" \
    "{\"changed_count\":${CHANGED_COUNT:-0},\"new_count\":${NEW_COUNT:-0},\"removed_count\":${REMOVED_COUNT:-0},\"incremental\":${INCREMENTAL},\"conflicts_found\":${CONFLICTS_FOUND}}"
fi
```

**Rules:**
- Baseline write is NON-FATAL — if it fails, warn but do not block the gate decision.
- Baseline is always refreshed (even on BLOCK) so user's next re-run with fixes gets accurate delta.
- `.scope-review-baseline.json` should be committed alongside `SCOPE-REVIEW.md` in Step 5.
</step>

<step name="5_commit_and_next">
## Step 5: Commit + suggest next

```bash
git add "${PLANNING_DIR}/SCOPE-REVIEW.md" "${PLANNING_DIR}/.scope-review-baseline.json"
git commit -m "scope-review: ${#SCOPED_PHASES[@]} phases — ${GATE_VERDICT}"
```

**Display:**
```
Scope Review Complete.
  Phases: {N} reviewed
  Conflicts: {N} | Collisions: {N} | Overlaps: {N} | Gaps: {N} | Creep: {N}
  CrossAI: {verdict | skipped}
  Gate: {PASS | BLOCK}
```

**If PASS:**
```
  Ready for blueprint. Start with:
    /vg:blueprint {first-unblueprinted-phase}
```

**If BLOCK (still unresolved):**
```
  Resolve blocking issues before proceeding to blueprint.
  Re-run: /vg:scope-review after fixes.
```

**If conditional PASS (acknowledged risks):**
```
  Proceeding with acknowledged risks.
  {N} issues marked as accepted. See SCOPE-REVIEW.md for details.
  
  Next: /vg:blueprint {first-unblueprinted-phase}
```
</step>

</process>

<success_criteria>
- All phases with CONTEXT.md collected and parsed (or scoped down via incremental delta)
- Incremental mode active by default: baseline read, delta computed, SCAN_SET narrowed to changed + new + dependents
- `--full` flag forces rescan of every scoped phase, bypassing baseline
- 5 automated cross-reference checks executed (A through E) against SCAN_SET
- CrossAI review ran (or skipped if flagged/no CLIs/single phase)
- SCOPE-REVIEW.md written with structured report + delta summary header + gate verdict
- Baseline (`.scope-review-baseline.json`) written atomically after every run (even on BLOCK)
- Telemetry event `scope-review-incremental` emitted with changed/new/conflicts counts
- All blocking issues presented to user with resolution options
- Gate resolves to PASS (clean, conditional, or all-acknowledged) before suggesting blueprint
- Report + baseline committed to git
- Next step guidance shows /vg:blueprint for first unblueprinted phase
</success_criteria>
