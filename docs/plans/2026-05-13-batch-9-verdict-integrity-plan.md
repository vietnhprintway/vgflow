# Batch 9 — Verdict + Marker Integrity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 3 CRITICAL pipeline correctness gaps (C4, C5, C9) where `/vg:test` can report PASSED when reality is broken. Source: `docs/plans/2026-05-13-pipeline-flow-audit.md`.

**Architecture:**
- **C4:** Split review READY verdict into `READY_STRUCTURAL` vs `READY_BEHAVIORAL`. TRUST_REVIEW only auto-PASSES BEHAVIORAL. STRUCTURAL → `TEST_PENDING` (forces test lane to replay).
- **C5:** Each test step writes outcome to `.test-step-status.json`. Verdict computation MAX(goal coverage, step ledger). Any step BLOCK/FAIL overrides goal-only PASS.
- **C9:** Close gates replace bare `[ -f marker.done ]` with `verify_marker` strict-mode call. Require active `run_id` match.

**Tech Stack:** Python 3.11+, bash. No third-party deps.

**Working directory:** `main` per project rule.

---

## Conventions

- Python: `from __future__ import annotations`, type-hinted.
- Mirror byte-identical to `.claude/commands/` + `.claude/scripts/` after every edit.
- Regression sweep before each commit: `python -m pytest tests/ -q --tb=no -k "verdict or marker or matrix_intent or trust_review"`.
- Commits use `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.

---

## Task 1: C4 — Split READY verdict + TRUST_REVIEW forces replay for structural

**Files:**
- Modify: `commands/vg/_shared/review/matrix-intent.md` (verdict definition + algorithm)
- Modify: `commands/vg/_shared/test/goal-verification/delegation.md` (TRUST_REVIEW Step D point 4)
- Mirror: `.claude/commands/vg/_shared/review/matrix-intent.md` + `.claude/commands/vg/_shared/test/goal-verification/delegation.md`
- Test: `tests/test_c4_ready_no_auto_pass.py`

**Step 1: Failing test**

```python
"""tests/test_c4_ready_no_auto_pass.py — Batch 9 C4 gap.

Verifies:
1. matrix-intent.md documents READY_BEHAVIORAL as the only state that
   auto-passes in TRUST_REVIEW.
2. goal-verification/delegation.md TRUST_REVIEW Step D does NOT auto-PASS
   bare READY goals — those go to TEST_PENDING / replay.
"""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "commands" / "vg" / "_shared" / "review" / "matrix-intent.md"
DELEG = REPO / "commands" / "vg" / "_shared" / "test" / "goal-verification" / "delegation.md"
MATRIX_MIR = REPO / ".claude" / "commands" / "vg" / "_shared" / "review" / "matrix-intent.md"
DELEG_MIR = REPO / ".claude" / "commands" / "vg" / "_shared" / "test" / "goal-verification" / "delegation.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_matrix_intent_defines_behavioral_split():
    body = _read(MATRIX)
    assert "READY_BEHAVIORAL" in body, (
        "C4: matrix-intent.md must define READY_BEHAVIORAL verdict for goals "
        "with persisted per-goal assertion evidence (not just structural scan)"
    )
    assert "READY_STRUCTURAL" in body or "READY" in body, (
        "Must retain structural READY state for endpoint+selector-only goals"
    )


def test_trust_review_does_not_auto_pass_structural():
    body = _read(DELEG)
    # Find the Step D Skip READY block
    if "Skip READY goals" in body:
        # NEW behavior: must distinguish structural vs behavioral
        idx = body.index("Skip READY goals")
        block = body[idx:idx + 800]
        assert "READY_BEHAVIORAL" in block or "TEST_PENDING" in block, (
            f"C4: TRUST_REVIEW Step D 'Skip READY goals' block must either "
            f"check READY_BEHAVIORAL specifically OR emit TEST_PENDING for "
            f"structural READY goals (forcing replay). Got block: {block[:300]}"
        )
        # Must NOT unconditionally emit PASSED for all READY
        bad_lines = [l for l in block.splitlines() if 'status: "PASSED"' in l and 'BEHAVIORAL' not in l and 'TEST_PENDING' not in l]
        # At least one PASSED-emit line must be conditional on BEHAVIORAL
        for l in bad_lines:
            if "trust-review" in l.lower():
                # Allow if it's specifically for BEHAVIORAL
                continue


def test_trust_review_mode_field_includes_structural_pending():
    body = _read(DELEG)
    # The mode/status enum must include TEST_PENDING for structural-only goals
    assert "TEST_PENDING" in body, (
        "C4: delegation.md must reference TEST_PENDING status for goals "
        "that pass structural review but require behavioral replay"
    )


def test_mirrors_byte_identical():
    if MATRIX_MIR.is_file():
        assert _read(MATRIX) == _read(MATRIX_MIR)
    if DELEG_MIR.is_file():
        assert _read(DELEG) == _read(DELEG_MIR)
```

**Step 2: Run** → 3 fail (no READY_BEHAVIORAL, no TEST_PENDING in Step D Skip-READY block, mirror may already match canonical pre-edit).

**Step 3: Implement**

Edit `commands/vg/_shared/review/matrix-intent.md`:

Replace the bullet list (lines 5-7):
```
- `READY` — goal has L1/L2 selector bindings + endpoint observed in RUNTIME-MAP
- `BLOCKED` — goal endpoint missing OR selectors unresolved
- `NOT_SCANNED` — goal not exercised during browser discovery
```

With:
```
- `READY_STRUCTURAL` — goal has L1/L2 selector bindings + endpoint observed in RUNTIME-MAP, but NO per-goal assertion evidence persisted by review. Test lane MUST replay (NOT auto-pass).
- `READY_BEHAVIORAL` — goal has structural readiness PLUS persisted assertion evidence (e.g. observed mutation + persistence_check passed during review discovery). TRUST_REVIEW may auto-pass.
- `BLOCKED` — goal endpoint missing OR selectors unresolved
- `NOT_SCANNED` — goal not exercised during browser discovery

> **Backward compatibility:** Bare `READY` is treated as `READY_STRUCTURAL` (safe default — forces replay). New `READY_BEHAVIORAL` is opt-in when review captures `evidence_ref` per goal.
```

Update Python algorithm:
```python
for goal in goals:
    if goal.endpoint_observed and goal.selectors_resolved:
        if goal.assertion_evidence_persisted:  # NEW
            verdict = "READY_BEHAVIORAL"
        else:
            verdict = "READY_STRUCTURAL"
    elif not goal.endpoint_observed:
        verdict = "BLOCKED"
    else:
        verdict = "NOT_SCANNED"
```

Edit `commands/vg/_shared/test/goal-verification/delegation.md` Step D point 4 (line 231-232 currently `Skip READY goals: Emit status PASSED, source trust-review — review 100% gate`):

```markdown
4. READY goals — split by review depth:
   - `READY_BEHAVIORAL`: review captured assertion evidence. Emit `status: "PASSED", source: "trust-review — behavioral evidence"`.
   - `READY_STRUCTURAL` or bare `READY`: review only confirmed structural readiness. Emit `status: "TEST_PENDING", source: "trust-review — structural only, replay required"`. Test lane MUST run goal replay (do NOT auto-pass).
```

**Step 4: Run tests** → 3 pass.

**Step 5: Mirror byte-identical**

```bash
cp commands/vg/_shared/review/matrix-intent.md .claude/commands/vg/_shared/review/matrix-intent.md
cp commands/vg/_shared/test/goal-verification/delegation.md .claude/commands/vg/_shared/test/goal-verification/delegation.md
```

**Step 6: Commit**

```bash
git add commands/vg/_shared/review/matrix-intent.md \
        commands/vg/_shared/test/goal-verification/delegation.md \
        .claude/commands/vg/_shared/review/matrix-intent.md \
        .claude/commands/vg/_shared/test/goal-verification/delegation.md \
        tests/test_c4_ready_no_auto_pass.py
git commit -m "fix(verdict): C4 — split READY into STRUCTURAL/BEHAVIORAL (Batch 9)

Codex audit Gap 4 (CRITICAL): review READY auto-promoted to test PASSED
without replay. Structural scan became behavioral success — pipeline
biggest correctness lie.

Root cause: matrix-intent.md defined READY = endpoint_observed +
selectors_resolved (structural). goal-verification/delegation.md Step D
point 4 mapped READY → PASSED in TRUST_REVIEW mode without replay.

Fix:
- matrix-intent.md splits READY into READY_STRUCTURAL (no assertion
  evidence) vs READY_BEHAVIORAL (review captured assertion evidence).
  Bare 'READY' treated as STRUCTURAL for backward compat (safer default).
- delegation.md Step D point 4: only READY_BEHAVIORAL auto-PASSES under
  TRUST_REVIEW. READY_STRUCTURAL emits TEST_PENDING — test lane MUST
  replay.

Tests: tests/test_c4_ready_no_auto_pass.py (3 tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: C5 — Step-status ledger + verdict integration

**Files:**
- Create: `scripts/step-status-ledger.py` (writer helper) + `.claude/scripts/` mirror
- Modify: `commands/vg/_shared/test/close.md` (verdict computation reads ledger)
- Modify steps that should write ledger entries:
  - `commands/vg/_shared/test/deploy.md` (5a_deploy)
  - `commands/vg/_shared/test/runtime.md` (5b/5c)
  - `commands/vg/_shared/test/regression-security.md` (5e/5f)
- Test: `tests/test_c5_step_status_overrides_verdict.py`

**Step 1: Failing test**

```python
"""tests/test_c5_step_status_overrides_verdict.py — Batch 9 C5 gap.

Verifies test/close.md verdict computation ingests step-status ledger.
Any step BLOCK/FAIL must override goal-only PASS math.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "scripts" / "step-status-ledger.py"
LEDGER_MIR = REPO / ".claude" / "scripts" / "step-status-ledger.py"
CLOSE = REPO / "commands" / "vg" / "_shared" / "test" / "close.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_ledger_script_exists():
    assert LEDGER.is_file(), "C5: step-status-ledger.py must ship in scripts/"


def test_ledger_write_creates_json(tmp_path):
    """Calling ledger writer with --step + --status must produce/update
    .test-step-status.json with the entry."""
    phase_dir = tmp_path / "phase"
    phase_dir.mkdir()
    r = subprocess.run(
        [sys.executable, str(LEDGER), "--phase-dir", str(phase_dir),
         "--step", "5b_runtime_contract_verify",
         "--status", "BLOCK",
         "--reason", "endpoint /api/refund returned 404"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    ledger_file = phase_dir / ".test-step-status.json"
    assert ledger_file.is_file()
    data = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert "steps" in data
    assert "5b_runtime_contract_verify" in data["steps"]
    assert data["steps"]["5b_runtime_contract_verify"]["status"] == "BLOCK"


def test_close_md_verdict_reads_ledger():
    """close.md verdict computation must reference .test-step-status.json
    (or equivalent ledger) so step-level FAIL overrides goal-only PASS."""
    body = _read(CLOSE)
    assert ".test-step-status.json" in body, (
        "C5: close.md verdict computation must read step-status ledger to "
        "ensure step BLOCK/FAIL overrides goal-only PASS"
    )


def test_close_md_verdict_logic_includes_step_block_override():
    """close.md verdict computation must include logic that downgrades
    verdict when any step status is BLOCK or FAIL."""
    body = _read(CLOSE)
    # Look for the override pattern — step_status BLOCK/FAIL forces FAILED
    has_override = any(
        marker in body for marker in [
            "step_status_block", "step BLOCK overrides", "step_blocks > 0",
            "step.get('status') in", "BLOCK', 'FAIL'", "STEP_BLOCK_OVERRIDE",
        ]
    )
    assert has_override, (
        "C5: close.md must include logic mapping any step ledger entry "
        "with status=BLOCK or FAIL to override goal-only PASS. Look for "
        "step_status_block or similar verdict-override hook."
    )


def test_mirror_byte_identical():
    if LEDGER_MIR.is_file():
        assert _read(LEDGER) == _read(LEDGER_MIR)
```

**Step 2: Run** → 5 fail (no script, no close.md ledger ref, no override logic).

**Step 3: Implement**

Create `scripts/step-status-ledger.py`:

```python
#!/usr/bin/env python3
"""step-status-ledger.py — Batch 9 C5

Per-step outcome ledger so test verdict can override goal-only PASS when
non-goal steps BLOCK/FAIL (contract verify, deploy, security, regression).

Schema:
{
  "steps": {
    "<step_name>": {
      "status": "PASS|BLOCK|FAIL|WARN|SKIP",
      "reason": "<text>",
      "ts": "<ISO timestamp>",
      "evidence_ref": "<optional path>"
    }
  }
}

Atomic write — read existing, merge, write tmp + rename.
"""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--step", required=True)
    ap.add_argument("--status", required=True,
                    choices=["PASS", "BLOCK", "FAIL", "WARN", "SKIP"])
    ap.add_argument("--reason", default="")
    ap.add_argument("--evidence-ref", default="")
    args = ap.parse_args()

    ledger = args.phase_dir / ".test-step-status.json"
    data = {"steps": {}}
    if ledger.is_file():
        try:
            data = json.loads(ledger.read_text(encoding="utf-8"))
            data.setdefault("steps", {})
        except Exception:
            pass

    entry = {
        "status": args.status,
        "reason": args.reason,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if args.evidence_ref:
        entry["evidence_ref"] = args.evidence_ref
    data["steps"][args.step] = entry

    # Atomic write
    args.phase_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(args.phase_dir), prefix=".test-step-status.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, ledger)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    print(f"ledger updated: {args.step}={args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Modify `commands/vg/_shared/test/close.md` verdict computation (after line 117, before `VERDICT=...` extraction):

Insert before line 120:
```python
# C5 Batch 9: step-status ledger override
# Any step with status=BLOCK or FAIL forces verdict downgrade regardless of
# goal-only math.
step_blocks = 0
step_ledger_path = Path("${PHASE_DIR}/.test-step-status.json")
step_reasons = []
if step_ledger_path.is_file():
    try:
        ledger = json.loads(step_ledger_path.read_text(encoding="utf-8"))
        for step_name, entry in ledger.get("steps", {}).items():
            if entry.get("status") in ("BLOCK", "FAIL"):
                step_blocks += 1
                step_reasons.append(f"{step_name}={entry.get('status')}: {entry.get('reason','')}")
    except Exception:
        pass

if step_blocks > 0:
    verdict = "FAILED"
    reasons = [f"STEP_BLOCK_OVERRIDE: {step_blocks} non-goal step(s) BLOCK/FAIL"] + step_reasons + (reasons if reasons else [])
```

Modify each step file to write ledger entry on outcome:

- `commands/vg/_shared/test/deploy.md`: after deploy result determined, add:
  ```bash
  "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/step-status-ledger.py" \
    --phase-dir "${PHASE_DIR}" --step "5a_deploy" --status "${DEPLOY_STATUS:-PASS}" \
    --reason "${DEPLOY_REASON:-}" || true
  ```

- `commands/vg/_shared/test/runtime.md`: after 5b result, similar with `--step "5b_runtime_contract_verify"`. After 5c_smoke, with `--step "5c_smoke"`.

- `commands/vg/_shared/test/regression-security.md`: after 5e regression, with `--step "5e_regression"`. After 5f security tier 0, with `--step "5f_security_audit"`.

**Step 4: Run tests** → 5 pass.

**Step 5: Mirror byte-identical**

```bash
cp scripts/step-status-ledger.py .claude/scripts/step-status-ledger.py
cp commands/vg/_shared/test/close.md .claude/commands/vg/_shared/test/close.md
cp commands/vg/_shared/test/deploy.md .claude/commands/vg/_shared/test/deploy.md
cp commands/vg/_shared/test/runtime.md .claude/commands/vg/_shared/test/runtime.md
cp commands/vg/_shared/test/regression-security.md .claude/commands/vg/_shared/test/regression-security.md
```

**Step 6: Commit**

```bash
git add scripts/step-status-ledger.py \
        .claude/scripts/step-status-ledger.py \
        commands/vg/_shared/test/{close,deploy,runtime,regression-security}.md \
        .claude/commands/vg/_shared/test/{close,deploy,runtime,regression-security}.md \
        tests/test_c5_step_status_overrides_verdict.py
git commit -m "fix(verdict): C5 — step-status ledger overrides goal-only verdict (Batch 9)

Codex audit Gap 5 (CRITICAL): final VERDICT computed from goal-*-result.json
+ priority buckets only. Step-level BLOCK/FAIL (deploy, contract verify,
smoke, regression, security) invisible to verdict. User misrouted to
/vg:accept with broken pipeline.

Fix:
- scripts/step-status-ledger.py: atomic writer for .test-step-status.json
  per-phase. Schema: {steps: {step_name: {status, reason, ts, evidence_ref}}}
- close.md verdict computation reads ledger BEFORE final verdict extraction.
  Any step with status=BLOCK or FAIL forces verdict=FAILED with
  STEP_BLOCK_OVERRIDE reason. Goal-only PASS math cannot override.
- deploy/runtime/regression-security step files emit ledger entries on
  outcome determination (5a_deploy, 5b_runtime_contract_verify, 5c_smoke,
  5e_regression, 5f_security_audit).

Tests: tests/test_c5_step_status_overrides_verdict.py (5 tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: C9 — close gates call verify_marker strict mode + run_id match

**Files:**
- Modify: `commands/vg/_shared/test/close.md` (close gate marker checks)
- Modify: `commands/vg/_shared/lib/marker-schema.sh` (add `verify_all_markers_strict_runid` helper if missing)
- Test: `tests/test_c9_marker_strict_run_id.py`

**Step 1: Failing test**

```python
"""tests/test_c9_marker_strict_run_id.py — Batch 9 C9 gap."""
from __future__ import annotations
import os
import subprocess
import tempfile
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
SCHEMA_SH = REPO / "commands" / "vg" / "_shared" / "lib" / "marker-schema.sh"
CLOSE = REPO / "commands" / "vg" / "_shared" / "test" / "close.md"


def test_close_gate_calls_verify_marker_strict():
    body = CLOSE.read_text(encoding="utf-8")
    # Must call verify_marker or verify_all_markers with strict mode
    assert "verify_marker" in body or "verify_all_markers" in body, (
        "C9: test/close.md terminal gate must invoke verify_marker/"
        "verify_all_markers (not bare [ -f marker.done ])"
    )
    # Must use VG_MARKER_STRICT=1 or pass strict flag
    assert "VG_MARKER_STRICT" in body or "--strict" in body or "strict" in body, (
        "C9: marker verification must run in strict mode (refuse legacy "
        "empty markers and forged markers)"
    )


def test_close_gate_checks_run_id():
    body = CLOSE.read_text(encoding="utf-8")
    # Must check run_id matches active run
    assert "VG_RUN_ID" in body or "run_id" in body, (
        "C9: close gate must require marker's run_id field to match "
        "active VG_RUN_ID — otherwise forged/stale markers pass"
    )


def test_schema_sh_has_run_id_match_helper():
    body = SCHEMA_SH.read_text(encoding="utf-8")
    # verify_marker should support run_id check
    assert "run_id" in body
    # New helper for full marker-set verify with run_id
    assert ("verify_marker_runid" in body or
            "verify_all_markers_strict_runid" in body or
            "expected_run_id" in body), (
        "C9: marker-schema.sh must export a helper that verifies marker "
        "run_id field matches the active VG_RUN_ID. Existing verify_marker "
        "supports the schema but doesn't enforce run_id match."
    )


def test_forged_empty_marker_rejected_in_strict_mode(tmp_path, monkeypatch):
    """Functional: forge empty marker, run verify in strict mode, expect non-zero."""
    phase_dir = tmp_path / "phase"
    marker_dir = phase_dir / ".step-markers"
    marker_dir.mkdir(parents=True)
    forged = marker_dir / "test_step.done"
    forged.write_text("")  # empty — legacy forge pattern

    bash_cmd = f"""
    set -e
    source '{SCHEMA_SH}'
    export VG_MARKER_STRICT=1
    verify_marker '{forged}' 'phase99' 'test_step'
    """
    r = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
    assert r.returncode != 0, (
        f"C9: forged empty marker must be REJECTED in strict mode. "
        f"verify_marker exit={r.returncode} stderr={r.stderr}"
    )
```

**Step 2: Run** → 4 fail (close.md uses bare existence check, no run_id, no helper, strict may already work but close doesn't enforce).

**Step 3: Implement**

Add `verify_all_markers_strict_runid` to `commands/vg/_shared/lib/marker-schema.sh` (append after existing `verify_marker`):

```bash
# verify_all_markers_strict_runid <phase_dir> <expected_phase> <expected_run_id>
# Strict mode + run_id match for every .done marker under phase_dir.
# Returns 0 if all markers parse + match phase + match run_id; non-zero else.
verify_all_markers_strict_runid() {
  local phase_dir="$1"
  local expected_phase="$2"
  local expected_run_id="$3"
  local marker_dir="${phase_dir}/.step-markers"

  if [ ! -d "$marker_dir" ]; then
    echo "verify_all_markers_strict_runid: no .step-markers dir under $phase_dir" >&2
    return 2
  fi

  local rc=0
  local marker
  for marker in "$marker_dir"/*.done; do
    [ -f "$marker" ] || continue
    local step
    step="$(basename "$marker" .done)"
    # Strict mode forces content check
    VG_MARKER_STRICT=1 verify_marker "$marker" "$expected_phase" "$step" >&2 || { rc=1; continue; }
    # Run_id match
    local content marker_run_id
    content="$(cat "$marker" 2>/dev/null)"
    marker_run_id="$(printf '%s' "$content" | awk -F'|' '{print $6}')"
    if [ -n "$expected_run_id" ] && [ "$marker_run_id" != "$expected_run_id" ]; then
      echo "verify_all_markers_strict_runid: run_id mismatch on $marker (got='$marker_run_id' expected='$expected_run_id')" >&2
      rc=1
    fi
  done
  return $rc
}
```

Modify `commands/vg/_shared/test/close.md` close gate (around line 532). Replace the bare existence check with:

```bash
# C9 Batch 9: marker integrity gate — strict mode + run_id match
MARKER_LIB="${VG_COMMAND_ROOT:-${VG_HOME:-$HOME/.vgflow}/commands/vg/_shared}/lib/marker-schema.sh"
[ -f "$MARKER_LIB" ] || MARKER_LIB="commands/vg/_shared/lib/marker-schema.sh"
[ -f "$MARKER_LIB" ] || MARKER_LIB=".claude/commands/vg/_shared/lib/marker-schema.sh"
if [ -f "$MARKER_LIB" ]; then
  source "$MARKER_LIB"
  export VG_MARKER_STRICT=1
  if ! verify_all_markers_strict_runid "${PHASE_DIR}" "${PHASE_NUMBER}" "${VG_RUN_ID:-}"; then
    echo "⛔ Marker integrity gate failed — empty/stale/forged markers detected" >&2
    echo "   Set VG_MARKER_STRICT=0 to bypass (UNSAFE — only for migration)." >&2
    exit 1
  fi
fi
```

**Step 4: Run tests** → 4 pass.

**Step 5: Mirror**

```bash
cp commands/vg/_shared/lib/marker-schema.sh .claude/commands/vg/_shared/lib/marker-schema.sh
cp commands/vg/_shared/test/close.md .claude/commands/vg/_shared/test/close.md
```

**Step 6: Commit**

```bash
git add commands/vg/_shared/lib/marker-schema.sh \
        commands/vg/_shared/test/close.md \
        .claude/commands/vg/_shared/lib/marker-schema.sh \
        .claude/commands/vg/_shared/test/close.md \
        tests/test_c9_marker_strict_run_id.py
git commit -m "fix(verdict): C9 — close gates use verify_marker strict + run_id match (Batch 9)

Codex audit Gap 9 (CRITICAL): hardened marker schema existed
(marker-schema.sh:9) with forgery detection (git_sha ancestry, ts age,
schema v1 fields parse, run_id) but test/close.md terminal gate only
checked file existence. Empty/stale/forged .done files satisfied gate.

Fix:
- marker-schema.sh: new verify_all_markers_strict_runid() helper iterates
  all .done markers under phase_dir, runs verify_marker in strict mode
  (VG_MARKER_STRICT=1), AND verifies marker run_id field matches active
  VG_RUN_ID.
- test/close.md: terminal gate now sources marker-schema.sh and calls
  verify_all_markers_strict_runid. Empty/forged/stale markers BLOCK
  close. Bypass requires explicit VG_MARKER_STRICT=0 (UNSAFE flag for
  migration only).

Tests: tests/test_c9_marker_strict_run_id.py (4 tests inc. functional
forge-marker-rejection test).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Regression sweep + release v4.3.0

**Step 1:** Full sweep on affected areas:

```bash
python -m pytest tests/ -q --tb=no -k "verdict or marker or matrix_intent or trust_review or c4 or c5 or c9 or step_status or ready or lifecycle"
```

All must pass. If pre-existing tests break:
- Pin update assertions to use `.get()` defaults
- If test asserted old `READY → PASSED` mapping, update to new `READY_BEHAVIORAL → PASSED + READY_STRUCTURAL → TEST_PENDING`

**Step 2:** Bump VERSION `4.2.0` → `4.3.0`. Update `package.json`.

**Step 3:** CHANGELOG entry:

```markdown
## v4.3.0 — Verdict + marker integrity (Batch 9, 3 CRITICAL fixes) (2026-05-XX)

Codex GPT-5.5 audit (2026-05-13) found 3 CRITICAL gaps where /vg:test
could report PASSED when reality was broken. Pipeline correctness lies.

### C4 — review READY no longer auto-promotes to test PASSED

Pre-fix: review verdict `READY` (endpoint observed + selectors resolved,
structural only) was auto-PASSED in TRUST_REVIEW mode without replay.
Structural scan became behavioral success.

Post-fix: `matrix-intent.md` splits into `READY_STRUCTURAL` (default) +
`READY_BEHAVIORAL` (requires persisted assertion evidence). TRUST_REVIEW
Step D point 4 only auto-passes BEHAVIORAL. STRUCTURAL → TEST_PENDING
forces test lane replay.

### C5 — step-status ledger overrides goal-only verdict

Pre-fix: final VERDICT computed from goal-*-result.json + priority
buckets only. Step BLOCK/FAIL (deploy/contract/smoke/regression/security)
invisible. User misrouted to /vg:accept on broken pipelines.

Post-fix: `.test-step-status.json` ledger (atomic writes via
scripts/step-status-ledger.py). close.md verdict reads ledger before
final extraction. Any step BLOCK/FAIL forces FAILED with
STEP_BLOCK_OVERRIDE.

### C9 — terminal marker gate verifies content + run_id

Pre-fix: marker-schema.sh defined hardened schema (phase|step|git_sha|
iso_ts|run_id) with verify_marker() forgery detection. But test/close.md
terminal gate only checked file existence. Empty/stale/forged .done
files satisfied gate.

Post-fix: marker-schema.sh adds verify_all_markers_strict_runid() helper.
test/close.md sources lib + invokes strict-mode verification with active
VG_RUN_ID match. Bypass requires explicit VG_MARKER_STRICT=0 flag.

### Tests

12 new tests across 3 files. All pre-existing tests still pass.

### Audit reference

Closes Gaps C4 + C5 + C9 from `docs/plans/2026-05-13-pipeline-flow-audit.md`.
```

**Step 4:** Commit + tag + push:

```bash
git add VERSION package.json CHANGELOG.md
git commit -m "release: v4.3.0 — Batch 9 verdict + marker integrity (C4+C5+C9 CRITICAL)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git tag v4.3.0 -m "v4.3.0 — Batch 9 verdict integrity"
git push origin main v4.3.0
```

**Step 5:** Re-sync global install:

```bash
cp commands/vg/_shared/lib/marker-schema.sh ~/.vgflow/commands/vg/_shared/lib/marker-schema.sh
cp commands/vg/_shared/review/matrix-intent.md ~/.vgflow/commands/vg/_shared/review/matrix-intent.md
cp commands/vg/_shared/test/{close,deploy,runtime,regression-security}.md ~/.vgflow/commands/vg/_shared/test/
cp commands/vg/_shared/test/goal-verification/delegation.md ~/.vgflow/commands/vg/_shared/test/goal-verification/delegation.md
cp scripts/step-status-ledger.py ~/.vgflow/scripts/step-status-ledger.py
```

---

End of Batch 9 plan. Estimated 4-5 hours engineering wall-clock.

## Risk register

| Risk | Mitigation |
|---|---|
| Existing READY-PASSED tests break en masse | Pre-flight grep for "READY" in tests/; update assertions to new dual-state model |
| Step ledger missing on phases that never wrote one | close.md falls through gracefully — empty ledger = no override; original goal-only verdict applies |
| Marker strict mode breaks legacy phases | Default VG_MARKER_STRICT=1 in close.md ONLY (not globally). Migrate via scripts/marker-migrate.py per phase |
| run_id missing in legacy markers | verify_all_markers_strict_runid skips run_id check when expected_run_id is empty (graceful) |
| Cross-CLI compat (Codex runtime) | All edits to canonical commands/ which mirror to .claude/. Codex resolves via VG_COMMAND_ROOT, gets the same files |

## Out of scope (Batch 9)

- C1 deploy evidence enforcement (→ Batch 5)
- C2 5c_smoke artifact contract (→ Batch 5)
- C3 URL semantic validation (→ Batch 3)
- C6/C7 subagent return strict schema (→ Batch 4)
- C8 phase 2a proof split (→ Batch 2)
- C10/C11 cleanup + flag fragmentation (→ Batch 5/2)
