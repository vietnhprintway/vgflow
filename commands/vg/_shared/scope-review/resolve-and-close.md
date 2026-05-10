<!-- v2.74.0 T1-T3 extraction — verbatim step blocks from commands/vg/scope-review.md -->
<!-- Group: resolve-and-close | Steps: 4_resolution, 4.5_baseline_write_and_telemetry, 5_commit_and_next -->

<process>

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
