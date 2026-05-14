# Batch 19 — Review + Test-Spec CRITICAL fixes (F1+F2+F4+F5+F6) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 5 CRITICAL findings from `docs/plans/2026-05-14-codex-review-testspec-audit.md`. Review + test-spec lanes currently have scaffold-only execution paths, swallowed failures, and prompt-only blocking gates.

- **F1**: `test-spec.md:432,451` codegen Agent spawn is comment-only. Marker fires unconditionally.
- **F2**: `test-spec.md:538` `run-complete --outcome PASS ... || true` swallows failures. PASS verdict ships even if contract fails.
- **F4**: `review/api-and-discovery.md:787,1128` browser tour Agent pseudo. Contract requires only `scan-*.json glob >= 1`.
- **F5**: `review/lens-and-findings.md:260,373` + `review/close.md:93` RUNTIME-MAP merge is prose, not script. Contract min 80 bytes — fabricated JSON passes.
- **F6**: `scripts/lib/blocking-gate-prompt.sh:16` `blocking_gate_prompt_emit` returns 0 always. Callers (close.md:490,582,617,659,691,723,749) don't branch on result. Failed gates fall through.

**Architecture:** Mirror Batch 15 pattern — gate marker/verdict on artifact/file existence + content check. Make `|| true` swallow paths fail-loud. Add per-view browser evidence schema.

**Working directory:** `main`.

---

## Conventions

- Mirror byte-identical to `.claude/`
- Sweep: `python -m pytest tests/ -q --tb=no -k "test_spec or review or codegen or browser or runtime_map or blocking_gate or f1_codegen or f2_run or f4_browser or f5_runtime or f6_block"`
- Single Co-Authored-By trailer per commit

---

## Task 1: F2 — Remove `|| true` swallow in test-spec run-complete (EASIEST CRITICAL)

**Files:**
- Modify: `commands/vg/test-spec.md` around line 538
- Mirror
- Test: `tests/test_f2_test_spec_run_complete_strict.py`

**Step 1: Failing test**

```python
"""tests/test_f2_test_spec_run_complete_strict.py — F2 test-spec run-complete strict."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
TS = REPO / "commands" / "vg" / "test-spec.md"


def test_test_spec_run_complete_no_swallow():
    body = TS.read_text(encoding="utf-8")
    # Find the test-spec.completed emit + run-complete block (near line 535-540)
    idx = body.find('test_spec.completed')
    assert idx > 0
    block = body[idx:idx + 1000]
    # The run-complete line must NOT swallow failures via `|| true`
    rc_idx = block.find("run-complete")
    assert rc_idx > 0
    rc_line_end = block.find("\n", rc_idx)
    rc_line = block[rc_idx:rc_line_end]
    assert "|| true" not in rc_line, (
        "F2: 'vg-orchestrator run-complete --outcome PASS' line must NOT end "
        "with '|| true' — that swallows contract failures. PASS verdict "
        "should only ship if run-complete returns 0."
    )


def test_test_spec_verdict_pass_conditional_on_run_complete():
    body = TS.read_text(encoding="utf-8")
    # The Python block that writes verdict=PASS must come AFTER run-complete
    # passes, OR there must be a guard. Easier check: there's an explicit exit
    # path on run-complete failure.
    idx = body.find('verdict": "PASS"')
    if idx < 0:
        idx = body.find("'verdict': 'PASS'")
    assert idx > 0
    # Within 1500 chars after, either an exit 1 / fail path OR run-complete
    # without `|| true`
    after = body[idx:idx + 2000]
    assert ("exit 1" in after or "run-complete" in after and "|| true" not in after.split("run-complete", 1)[1].split("\n", 1)[0]), (
        "F2: verdict=PASS write must be guarded — either explicit exit 1 on "
        "failure path OR run-complete called without `|| true`"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/test-spec.md` around line 538, change:

```bash
"${PYTHON_BIN:-python3}" "$ORCH" run-complete --outcome PASS 2>/dev/null || true
```

To:

```bash
# F2 Batch 19: run-complete failure must NOT be swallowed. PASS verdict
# was written above (lines 521-525), but if run-complete fails the
# orchestrator contract validator caught a problem — surface it loudly.
if ! "${PYTHON_BIN:-python3}" "$ORCH" run-complete --outcome PASS 2>&1 | tee /tmp/run-complete-err.$$; then
  RC=${PIPESTATUS[0]:-1}
  echo "⛔ F2 BLOCK: test-spec run-complete failed (rc=$RC) — contract validator caught issue" >&2
  echo "   PASS verdict was written prematurely. Re-verify artifacts before retry." >&2
  rm -f /tmp/run-complete-err.$$
  exit 1
fi
rm -f /tmp/run-complete-err.$$
```

```bash
git commit -m "fix(test-spec): F2 — run-complete failure no longer swallowed (Batch 19 CRITICAL)

Codex audit Finding F2 (CRITICAL): test-spec.md:538 had
'\${PYTHON_BIN} \$ORCH run-complete --outcome PASS 2>/dev/null || true'.
The '|| true' swallowed contract-validator failures. verdict=PASS was
written to PIPELINE-STATE 17 lines earlier (line 523), but if run-complete
detected a real problem (missing artifact, marker check fail, etc), it
was hidden. Build appeared successful with broken contract.

Fix: drop '2>/dev/null || true'. Capture rc via PIPESTATUS, exit 1 on
non-zero, surface stderr to user.

Tests: tests/test_f2_test_spec_run_complete_strict.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: F1 — Test-spec codegen verdict-file gate

**Files:**
- Modify: `commands/vg/test-spec.md` around lines 451-475 (Agent spawn area) + add gate after
- Mirror
- Test: `tests/test_f1_codegen_verdict_gate.py`

**Step 1: Failing test**

```python
"""tests/test_f1_codegen_verdict_gate.py — F1 test-spec codegen verdict gate."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
TS = REPO / "commands" / "vg" / "test-spec.md"


def test_codegen_step_has_post_spawn_gate():
    body = TS.read_text(encoding="utf-8")
    # Find step 4_codegen
    idx = body.find('<step name="4_codegen">')
    assert idx > 0
    # Within next 3500 chars must reference CODEGEN-MANIFEST or playwright spec count check
    block = body[idx:idx + 4000]
    assert ("CODEGEN-MANIFEST" in block or "spec_count" in block.lower() or "playwright" in block.lower() and "count" in block.lower()), (
        "F1: 4_codegen step must reference CODEGEN-MANIFEST file or spec count "
        "check post-Agent-spawn (current spawn is comment-only)"
    )


def test_codegen_manifest_existence_gate_present():
    body = TS.read_text(encoding="utf-8")
    idx = body.find("4_codegen")
    assert idx > 0
    block = body[idx:idx + 4500]
    # Must check manifest file existence (similar to Batch 15 F3 spec-review pattern)
    assert ("CODEGEN-MANIFEST.json" in block and ("[ -f" in block or "[ ! -f" in block or "is_file" in block)), (
        "F1: codegen step must gate marker on CODEGEN-MANIFEST.json existence "
        "(Agent must write the manifest; missing file = exit 1)"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/test-spec.md` after the Agent prose block (around line 475 — after `Agent(...)` block ends and BEFORE marker touch), insert:

```bash
# F1 Batch 19: vg-test-codegen MUST write CODEGEN-MANIFEST.json + playwright
# spec files. Marker gates on those outputs (mirrors Batch 15 F3/F4 pattern).
CODEGEN_MANIFEST="${PHASE_DIR}/CODEGEN-MANIFEST.json"
if [ ! -f "$CODEGEN_MANIFEST" ]; then
  echo "⛔ F1 BLOCK: vg-test-codegen did not write CODEGEN-MANIFEST.json" >&2
  echo "   Codegen Agent spawn produced no output. Re-run /vg:test-spec ${PHASE_NUMBER}." >&2
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "test_spec.codegen_missing_manifest" \
    --payload "{\"phase\":\"${PHASE_NUMBER}\"}" >/dev/null 2>&1 || true
  exit 1
fi
# Spec count check — manifest must list playwright specs
SPEC_COUNT=$(${PYTHON_BIN:-python3} -c "
import json
m = json.loads(open('${CODEGEN_MANIFEST}', encoding='utf-8').read())
specs = m.get('playwright_specs', m.get('specs', []))
print(len(specs))
" 2>/dev/null || echo "0")
if [ "${SPEC_COUNT:-0}" -lt 1 ]; then
  echo "⛔ F1 BLOCK: CODEGEN-MANIFEST.json contains 0 playwright specs" >&2
  echo "   vg-test-codegen claims to have run but produced no spec files." >&2
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "test_spec.codegen_zero_specs" \
    --payload "{\"phase\":\"${PHASE_NUMBER}\"}" >/dev/null 2>&1 || true
  exit 1
fi
echo "✓ F1: codegen wrote ${SPEC_COUNT} playwright specs"
```

```bash
git commit -m "fix(test-spec): F1 — codegen CODEGEN-MANIFEST verdict gate (Batch 19 CRITICAL)

Codex audit Finding F1 (CRITICAL): test-spec.md:432,451 vg-test-codegen
Agent spawn was comment-only ('Agent(subagent_type=..., prompt=..., ...)'
in fenced code block). Marker 4_codegen.done fired unconditionally.
'Codegen complete' ran without actual codegen.

Fix: post-Agent gate requires \${PHASE_DIR}/CODEGEN-MANIFEST.json on
disk + playwright_specs array length >= 1. Missing file or zero specs
exits 1 with emit-event(test_spec.codegen_missing_manifest /
test_spec.codegen_zero_specs).

Tests: tests/test_f1_codegen_verdict_gate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: F6 — Blocking gate prompt-only → enforced resolve

**Files:**
- Modify: `scripts/lib/blocking-gate-prompt.sh` (add resolved-required mode)
- Modify: 7 callers in `commands/vg/_shared/review/close.md` (lines 490, 582, 617, 659, 691, 723, 749)
- Mirror
- Test: `tests/test_f6_blocking_gate_enforced.py`

**Step 1: Failing test**

```python
"""tests/test_f6_blocking_gate_enforced.py — F6 blocking gate enforced resolve."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "lib" / "blocking-gate-prompt.sh"
CLOSE = REPO / "commands" / "vg" / "_shared" / "review" / "close.md"


def test_emit_no_longer_returns_zero_on_critical():
    body = LIB.read_text(encoding="utf-8")
    # Find blocking_gate_prompt_emit function body
    fn_idx = body.find("blocking_gate_prompt_emit()")
    assert fn_idx > 0
    # Find the closing of the function (next function or EOF)
    next_fn = body.find("\nblocking_gate_prompt_resolve()", fn_idx)
    fn_body = body[fn_idx:next_fn if next_fn > 0 else len(body)]
    # On critical/error severity, must return non-zero so caller branches
    assert ("return 1" in fn_body or "return 2" in fn_body) and "critical" in fn_body, (
        "F6: blocking_gate_prompt_emit must return non-zero for critical/error "
        "severity by default, so callers cannot ignore the prompt and fall "
        "through to run-complete"
    )


def test_callers_handle_emit_return_code():
    body = CLOSE.read_text(encoding="utf-8")
    # Each blocking_gate_prompt_emit call must be guarded by a conditional
    # or follow with exit/abort logic. Spot-check 3 known critical callers.
    critical_callers = ["rcrurd_post_state", "evidence_provenance", "mutation_submit"]
    for caller in critical_callers:
        idx = body.find(f'blocking_gate_prompt_emit "{caller}"')
        assert idx > 0, f"caller '{caller}' not found"
        # Within next 500 chars, must reference $? / exit / RC variable
        after = body[idx:idx + 800]
        assert ("$?" in after or "EMIT_RC" in after or "exit 1" in after or "return 1" in after), (
            f"F6: caller '{caller}' must handle emit return code "
            f"(check $? or capture RC), not ignore it"
        )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `scripts/lib/blocking-gate-prompt.sh` `blocking_gate_prompt_emit()` function, after the EOF heredoc that prints options JSON (around line 80), CHANGE final `return 0` to:

```bash
  # F6 Batch 19: emit must signal severity to caller. Critical/error returns
  # non-zero so caller cannot fall through to run-complete without explicit
  # resolve via blocking_gate_prompt_resolve (Leg 2).
  case "$severity" in
    critical|error) return 2 ;;  # caller MUST resolve via Leg 2 or exit
    warn) return 0 ;;             # advisory — caller may proceed
    *) return 2 ;;
  esac
```

In `commands/vg/_shared/review/close.md` at each of the 7 caller sites, change:

```bash
    blocking_gate_prompt_emit "matrix_evidence_link" "$EVIDENCE_PATH" "warn"
```

To:

```bash
    blocking_gate_prompt_emit "matrix_evidence_link" "$EVIDENCE_PATH" "warn"
    EMIT_RC=$?
    if [ "$EMIT_RC" -ne 0 ]; then
      echo "⛔ F6: blocking gate 'matrix_evidence_link' must be resolved (rc=$EMIT_RC). AI controller must call blocking_gate_prompt_resolve or exit." >&2
      # AI handles via AskUserQuestion + Leg 2; if AI does nothing, fail loud:
      if [[ ! "${ARGUMENTS:-}" =~ --gate-resolved=matrix_evidence_link ]]; then
        exit 1
      fi
    fi
```

For each of the 7 callers, swap gate_id name. Critical/error severity gates exit 1 on unresolved. Warn severity (matrix_evidence_link, matrix_staleness, rcrurd_depth) emit returns 0 — no enforcement change but the wrapper makes it consistent.

```bash
git commit -m "fix(review): F6 — blocking gates enforced resolve (Batch 19 CRITICAL)

Codex audit Finding F6 (CRITICAL): scripts/lib/blocking-gate-prompt.sh
blocking_gate_prompt_emit() always returned 0 after printing the prompt
JSON. Callers in review/close.md (7 sites: matrix_evidence_link,
rcrurd_post_state, matrix_staleness, evidence_provenance, mutation_submit,
rcrurd_depth, asserted_drift) didn't branch on return code. If AI
controller skipped the AskUserQuestion + Leg 2 resolve, gate just
printed JSON and review continued to run-complete with verdict=PASS.

Fix:
- blocking_gate_prompt_emit returns 2 on critical/error severity,
  0 on warn. Caller must capture rc and resolve.
- Each of 7 close.md callers now captures EMIT_RC and exits 1 on
  unresolved (unless --gate-resolved=<gate_id> flag set by Leg 2
  dispatcher).
- AI controller path unchanged — still uses AskUserQuestion + Leg 2,
  but now the gate hard-fails if controller doesn't reach Leg 2.

Tests: tests/test_f6_blocking_gate_enforced.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: F4 — Review browser tour per-view evidence gate

**Files:**
- Modify: `commands/vg/_shared/review/api-and-discovery.md` (lines 787, 1128 area — Agent spawn + post-spawn gate)
- Mirror
- Test: `tests/test_f4_browser_tour_evidence.py`

**Step 1: Failing test**

```python
"""tests/test_f4_browser_tour_evidence.py — F4 browser tour per-view evidence."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
AD = REPO / "commands" / "vg" / "_shared" / "review" / "api-and-discovery.md"


def test_per_view_scan_count_match():
    body = AD.read_text(encoding="utf-8")
    # Must check that scan-*.json count equals assigned view count
    # OR reference nav-discovery.json with views[] array
    has_per_view_gate = (
        "nav-discovery.json" in body and "actual_views" in body or
        "scan-*.json" in body and "views" in body.lower() and ("equals" in body.lower() or "match" in body.lower() or "-eq " in body)
    )
    assert has_per_view_gate, (
        "F4: review browser tour must verify per-view scan count matches "
        "assigned view count (not just 'at least 1 scan file exists')"
    )


def test_provenance_check_current_run():
    body = AD.read_text(encoding="utf-8")
    # Must reference current run/session for provenance — scans from a previous
    # cached run should be rejected
    assert ("RUN_ID" in body or "run_id" in body or "current run" in body.lower() or "current-run" in body), (
        "F4: scan files must be tagged with current run_id so cached scans "
        "from prior runs don't count as 'toured'"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/review/api-and-discovery.md` after the existing Agent spawn area around line 1128 (post-discovery), insert:

```bash
# F4 Batch 19: per-view evidence contract — Agent claims to tour N views,
# must produce N scan-*.json files tagged with current run_id.
NAV_DISCOVERY="${PHASE_DIR}/.review/nav-discovery.json"
if [ -f "$NAV_DISCOVERY" ]; then
  ASSIGNED_VIEWS=$(${PYTHON_BIN:-python3} -c "
import json
d = json.loads(open('${NAV_DISCOVERY}', encoding='utf-8').read())
print(len(d.get('views', d.get('assigned_views', []))))
" 2>/dev/null || echo "0")
  SCAN_COUNT=$(find "${PHASE_DIR}/.scan" -maxdepth 1 -name "scan-*.json" 2>/dev/null | wc -l | tr -d ' ')
  if [ "${ASSIGNED_VIEWS:-0}" -ne "${SCAN_COUNT:-0}" ]; then
    echo "⛔ F4 BLOCK: nav-discovery assigned ${ASSIGNED_VIEWS} views but only ${SCAN_COUNT} scan-*.json files found" >&2
    echo "   Agent claims '${ASSIGNED_VIEWS} views toured' — evidence does not match." >&2
    "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "review.browser_tour_evidence_gap" \
      --payload "{\"phase\":\"${PHASE_NUMBER}\",\"assigned\":${ASSIGNED_VIEWS},\"scans\":${SCAN_COUNT}}" >/dev/null 2>&1 || true
    exit 1
  fi
  # Provenance — each scan must reference current run_id
  CURRENT_RUN_ID="${VG_RUN_ID:-$(cat ".vg/active-runs/${VG_SESSION_ID:-current}.json" 2>/dev/null | ${PYTHON_BIN:-python3} -c "import json,sys; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null)}"
  if [ -n "$CURRENT_RUN_ID" ]; then
    STALE_SCANS=$(find "${PHASE_DIR}/.scan" -name "scan-*.json" 2>/dev/null | while read f; do
      if ! grep -q "\"run_id\": *\"${CURRENT_RUN_ID}\"" "$f" 2>/dev/null; then
        echo "$f"
      fi
    done | wc -l | tr -d ' ')
    if [ "${STALE_SCANS:-0}" -gt 0 ]; then
      echo "⚠ F4: ${STALE_SCANS} scan(s) from prior runs detected (not current run_id ${CURRENT_RUN_ID})" >&2
      "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "review.browser_tour_stale_scans" \
        --payload "{\"phase\":\"${PHASE_NUMBER}\",\"stale\":${STALE_SCANS}}" >/dev/null 2>&1 || true
    fi
  fi
fi
```

```bash
git commit -m "fix(review): F4 — browser tour per-view evidence gate (Batch 19 CRITICAL)

Codex audit Finding F4 (CRITICAL): review/api-and-discovery.md browser
tour Agent spawn was prose ('Agent(...)' in markdown). Telemetry fired
BEFORE spawn. Contract required only 'scan-*.json glob >= 1'. Receipt
claims '12 views toured' but no per-view evidence enforced.

Fix:
- Post-spawn gate reads .review/nav-discovery.json views array,
  counts .scan/scan-*.json files, requires equality.
- Provenance check: each scan must reference current run_id. Cached
  scans from prior runs emit review.browser_tour_stale_scans warning
  (will flip to BLOCK in v4.23+).
- Emit review.browser_tour_evidence_gap on count mismatch.

Closes 'received 12 views toured but no proof' dogfood gap from
PrintwayV3 phase 7 receipt.

Tests: tests/test_f4_browser_tour_evidence.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: F5 — RUNTIME-MAP merge script + schema validator

**Files:**
- Create: `scripts/merge-runtime-map.py` (deterministic merge of per-view scans into RUNTIME-MAP.json)
- Modify: `commands/vg/_shared/review/lens-and-findings.md` (replace prose merge with script call)
- Modify: `commands/vg/_shared/review/close.md` (increase min size from 80 bytes + reference schema validator)
- Possibly add: `scripts/validators/verify-runtime-map-schema.py` if not exists
- Mirror
- Test: `tests/test_f5_runtime_map_merge.py`

**Step 1: Failing test**

```python
"""tests/test_f5_runtime_map_merge.py — F5 RUNTIME-MAP merge + schema."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
MERGE = REPO / "scripts" / "merge-runtime-map.py"


def test_merge_script_exists():
    assert MERGE.is_file(), "F5: scripts/merge-runtime-map.py must exist"


def test_merge_script_rejects_empty_scans_dir(tmp_path):
    scan_dir = tmp_path / ".scan"
    scan_dir.mkdir()
    out = tmp_path / "RUNTIME-MAP.json"
    r = subprocess.run(
        [sys.executable, str(MERGE), "--scan-dir", str(scan_dir), "--out", str(out)],
        capture_output=True, text=True,
    )
    # Empty scan dir = no views to merge — must fail (not silently emit 80-byte stub)
    assert r.returncode != 0, "F5: empty scan dir must fail merge, not produce stub"


def test_merge_produces_schema_compliant_output(tmp_path):
    """Smoke test: 2 scan files → merged RUNTIME-MAP.json with views[] array."""
    import json
    scan_dir = tmp_path / ".scan"
    scan_dir.mkdir()
    (scan_dir / "scan-login.json").write_text(json.dumps({
        "view": "login",
        "url": "/login",
        "elements": [{"selector": "input[name=email]"}],
        "actions": [{"type": "click", "selector": "button[type=submit]"}],
    }), encoding="utf-8")
    (scan_dir / "scan-dashboard.json").write_text(json.dumps({
        "view": "dashboard",
        "url": "/dashboard",
        "elements": [{"selector": ".kpi-card"}],
        "actions": [],
    }), encoding="utf-8")
    out = tmp_path / "RUNTIME-MAP.json"
    r = subprocess.run(
        [sys.executable, str(MERGE), "--scan-dir", str(scan_dir), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"merge failed: {r.stderr}"
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "views" in data
    assert len(data["views"]) == 2
    assert all("elements" in v for v in data["views"])


def test_lens_findings_references_merge_script():
    body = (REPO / "commands/vg/_shared/review/lens-and-findings.md").read_text(encoding="utf-8")
    assert "merge-runtime-map.py" in body, (
        "F5: review/lens-and-findings.md must invoke merge-runtime-map.py "
        "for deterministic RUNTIME-MAP.json generation (not prose Glob merge)"
    )


def test_close_min_size_raised():
    body = (REPO / "commands/vg/_shared/review/close.md").read_text(encoding="utf-8")
    # Old: 80 bytes minimum. New: substantially higher (e.g. 500+) since
    # schema-compliant output with 1+ views will exceed that.
    # Look for content_min_bytes near RUNTIME-MAP entries
    import re
    matches = re.findall(r"RUNTIME-MAP[^\n]*\n[^\n]*content_min_bytes:\s*(\d+)", body)
    if matches:
        for m in matches:
            assert int(m) >= 500, (
                f"F5: RUNTIME-MAP content_min_bytes was 80, must be raised to "
                f"500+ so fabricated stub JSON cannot satisfy contract. Got: {m}"
            )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

Create `scripts/merge-runtime-map.py`:

```python
#!/usr/bin/env python3
"""merge-runtime-map.py — F5 Batch 19

Deterministic merge of per-view scan-*.json files into RUNTIME-MAP.json.
Replaces prose-instruction Glob merge in commands/vg/_shared/review/
lens-and-findings.md that allowed fabricated 80-byte stubs to satisfy
the contract.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--phase-number", default="")
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()

    if not args.scan_dir.is_dir():
        print(f"ERROR: scan dir not found: {args.scan_dir}", file=sys.stderr)
        return 1

    scan_files = sorted(args.scan_dir.glob("scan-*.json"))
    if not scan_files:
        print(f"ERROR: no scan-*.json files in {args.scan_dir}", file=sys.stderr)
        print("       review browser tour produced no per-view scans — cannot merge.", file=sys.stderr)
        return 1

    views = []
    for sf in scan_files:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARN: skipping {sf.name}: {e}", file=sys.stderr)
            continue
        view_entry = {
            "view": data.get("view", sf.stem.replace("scan-", "")),
            "url": data.get("url", ""),
            "elements": data.get("elements", []),
            "actions": data.get("actions", []),
            "goal_sequences": data.get("goal_sequences", []),
            "source_scan": sf.name,
            "scan_run_id": data.get("run_id", ""),
        }
        views.append(view_entry)

    if not views:
        print("ERROR: all scan files unparseable — refusing to write stub", file=sys.stderr)
        return 1

    out = {
        "schema_version": "1.0",
        "phase": args.phase_number,
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "view_count": len(views),
        "views": views,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"✓ F5: merged {len(views)} views → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

In `commands/vg/_shared/review/lens-and-findings.md` around lines 260-373 (the prose merge area), add bash invocation:

```bash
# F5 Batch 19: deterministic RUNTIME-MAP merge (replaces prose Glob merge).
MERGE_SCRIPT="${REPO_ROOT:-.}/.claude/scripts/merge-runtime-map.py"
[ -f "$MERGE_SCRIPT" ] || MERGE_SCRIPT="${REPO_ROOT:-.}/scripts/merge-runtime-map.py"
if [ ! -f "$MERGE_SCRIPT" ]; then
  echo "⛔ F5 BLOCK: merge-runtime-map.py missing — review cannot build RUNTIME-MAP.json deterministically" >&2
  exit 1
fi
"${PYTHON_BIN:-python3}" "$MERGE_SCRIPT" \
  --scan-dir "${PHASE_DIR}/.scan" \
  --out "${PHASE_DIR}/RUNTIME-MAP.json" \
  --phase-number "${PHASE_NUMBER}" \
  --run-id "${VG_RUN_ID:-}" || {
  echo "⛔ F5 BLOCK: RUNTIME-MAP merge failed — see stderr" >&2
  exit 1
}
```

In `commands/vg/_shared/review/close.md` raise `content_min_bytes` from 80 to 500 for RUNTIME-MAP entries.

```bash
git commit -m "fix(review): F5 — RUNTIME-MAP deterministic merge script (Batch 19 CRITICAL)

Codex audit Finding F5 (CRITICAL): review/lens-and-findings.md merged
RUNTIME-MAP.json via prose instruction ('Use Glob to find scan-*.json').
review/close.md content_min_bytes: 80. Fabricated 80-byte JSON could
satisfy contract. Per-view evidence (elements, actions, goal_sequences,
provenance) was not enforced.

Fix:
- New scripts/merge-runtime-map.py deterministic merge — reads each
  scan-*.json, builds views[] array with elements/actions/goal_sequences/
  source_scan/scan_run_id. Refuses to write stub when scan dir empty.
- lens-and-findings.md invokes script; failure exits 1.
- close.md content_min_bytes raised 80 → 500.

Tests: tests/test_f5_runtime_map_merge.py (5 tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Release v4.22.0

Bump VERSION 4.21.0 → 4.22.0. CHANGELOG entry per 5 CRITICAL findings. Tag v4.22.0. Push. Re-sync ~/.vgflow. Verify codex mirror; regen if drift.

End of Batch 19 plan. Estimated 4 hours.
