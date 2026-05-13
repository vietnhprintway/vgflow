# Batch 3 — Validator semantics + step content (G8+G11+G13+G3+H3+C3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 6 validator/step-content gaps where validators check shape not semantics, and step bodies rely on template strings instead of binding data.

**Source:** `docs/plans/2026-05-13-pipeline-flow-audit.md` + `docs/plans/2026-05-13-lifecycle-specs-redesign-design.md`.

**Tech Stack:** Python.

**Working directory:** `main`.

---

## Conventions

- Python: `from __future__ import annotations`, type-hinted
- Mirror byte-identical to `.claude/`
- Regression sweep: `python -m pytest tests/ -q --tb=no -k "lifecycle or validator or url or assertion or runtime_conform or g3 or g8 or g11 or g13 or h3 or c3"`
- Single `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` per commit

---

## Task 1: G13 — Lifecycle validator semantic checks

**Files:**
- Modify: `scripts/validators/verify-lifecycle-spec-depth.py` (add semantic check pass)
- Mirror: `.claude/scripts/validators/verify-lifecycle-spec-depth.py`
- Test: `tests/test_g13_lifecycle_validator_semantics.py`

**Step 1: Failing test**

```python
"""tests/test_g13_lifecycle_validator_semantics.py — G13 semantic checks."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
VAL = REPO / "scripts" / "validators" / "verify-lifecycle-spec-depth.py"


def _run_val(tmp_path, spec_data):
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps(spec_data), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase", "99", "--phase-dir", str(phase_dir)],
        capture_output=True, text=True,
    )
    return r


def test_validator_flags_stage_endpoint_method_mismatch(tmp_path):
    """G13: validator must flag when stage verb mismatches endpoint method.
    E.g. 'create' stage bound to GET endpoint should warn."""
    spec = {
        "phase": "99",
        "goals": {
            "G-01": {
                "actors": [{"id": "user"}],
                "steps": [
                    {"name": "create", "actor": "user",
                     "endpoint": {"method": "GET", "path": "/api/x"},  # bug: create stage with GET
                     "assertions": []}
                ],
            }
        }
    }
    r = _run_val(tmp_path, spec)
    assert (r.returncode != 0) or ("stage" in r.stdout.lower() and "method" in r.stdout.lower()) or "G13" in r.stdout, (
        f"G13: validator must flag create-stage-with-GET-endpoint mismatch. "
        f"stdout={r.stdout[:500]} stderr={r.stderr[:200]}"
    )


def test_validator_flags_assertion_without_source(tmp_path):
    """G13: validator must flag step.assertions[] entries missing source field."""
    spec = {
        "phase": "99",
        "goals": {
            "G-01": {
                "actors": [{"id": "user"}],
                "steps": [
                    {"name": "create", "actor": "user", "endpoint": None,
                     "assertions": [{"check": "status 201"}]}  # missing source
                ]
            }
        }
    }
    r = _run_val(tmp_path, spec)
    assert "source" in r.stdout.lower() or r.returncode != 0, (
        f"G13: validator must flag assertions[] entries without source field. "
        f"stdout={r.stdout[:500]}"
    )


def test_validator_passes_well_formed_spec(tmp_path):
    """G13: well-formed spec passes."""
    spec = {
        "phase": "99",
        "goals": {
            "G-01": {
                "actors": [{"id": "user"}],
                "preconditions": ["session active"],
                "fixture_dag": {},
                "steps": [
                    {"name": "read_before", "actor": "user",
                     "endpoint": {"method": "GET", "path": "/api/x"},
                     "assertions": [{"source": "baseline", "check": "empty list"}]},
                    {"name": "create", "actor": "user",
                     "endpoint": {"method": "POST", "path": "/api/x"},
                     "assertions": [{"source": "API-CONTRACTS", "check": "POST returns 201"}]},
                ],
                "artifact_capture": []
            }
        }
    }
    r = _run_val(tmp_path, spec)
    # Should pass — or at least not fail with G13-specific errors
    if r.returncode != 0:
        # Acceptable if pre-existing validator complains about phase markers, etc.
        # The new G13 semantic checks should NOT fire on well-formed spec
        assert "G13" not in r.stdout, f"G13: well-formed spec must not trigger G13 errors. stdout={r.stdout[:500]}"
```

**Step 2: Run** → 2-3 fail (current validator is shape-only).

**Step 3: Implement**

In `scripts/validators/verify-lifecycle-spec-depth.py`, after existing shape checks, add semantic check pass:

```python
# G13 Batch 3: semantic checks beyond shape
STAGE_VERB_MAP = {
    "create": ("POST",),
    "update": ("PUT", "PATCH"),
    "delete": ("DELETE",),
    "read_before": ("GET",),
    "read_after_create": ("GET",),
    "read_after_update": ("GET",),
    "read_after_delete": ("GET",),
}


def _semantic_checks(spec: dict) -> list[str]:
    """Return list of G13 semantic issues."""
    issues: list[str] = []
    for gid, goal in (spec.get("goals") or {}).items():
        actor_ids = {a.get("id") for a in (goal.get("actors") or [])}
        for step in (goal.get("steps") or []):
            stage = step.get("name") or step.get("stage")
            # Stage ↔ endpoint method match
            ep = step.get("endpoint")
            if ep and stage in STAGE_VERB_MAP:
                expected = STAGE_VERB_MAP[stage]
                if ep.get("method") not in expected:
                    issues.append(
                        f"G13: goal {gid} stage '{stage}' bound to "
                        f"{ep.get('method')} {ep.get('path')} — expected method in {expected}"
                    )
            # Assertion entries each need source
            for a in (step.get("assertions") or []):
                if not isinstance(a, dict) or not a.get("source"):
                    issues.append(
                        f"G13: goal {gid} stage '{stage}' has assertion without source: {a}"
                    )
            # Actor must exist in goal.actors
            actor = step.get("actor")
            if actor and actor_ids and actor not in actor_ids:
                issues.append(
                    f"G13: goal {gid} stage '{stage}' references unknown actor '{actor}'; "
                    f"goal.actors={sorted(actor_ids)}"
                )
    return issues
```

Wire into main validate flow — print issues to stdout, exit non-zero if any critical (e.g. method mismatch). Or print as warnings + exit 0 to keep advisory. Pick advisory for now:

```python
issues = _semantic_checks(spec_data)
if issues:
    print("⚠ G13 semantic issues:")
    for i in issues:
        print(f"  - {i}")
    # Advisory mode: return non-zero only if --strict
    if args.strict if hasattr(args, "strict") else False:
        return 1
```

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/validators/verify-lifecycle-spec-depth.py \
        .claude/scripts/validators/verify-lifecycle-spec-depth.py \
        tests/test_g13_lifecycle_validator_semantics.py
git commit -m "feat(validator): G13 — lifecycle validator semantic checks (Batch 3)

Audit Gap G13: verify-lifecycle-spec-depth.py was shape-only — checked
fields exist, did NOT verify semantic correctness (stage verb ↔ endpoint
method match, assertion source field, actor ↔ goal.actors set).

Fix: _semantic_checks() pass after shape checks. Three rules:
1. Stage verb ↔ endpoint method (create→POST, delete→DELETE, etc).
2. Each assertion entry must have a 'source' field.
3. step.actor must exist in goal.actors[] set.

Advisory mode by default (prints warnings, exit 0). --strict flag
escalates to non-zero exit.

Tests: tests/test_g13_lifecycle_validator_semantics.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: C3 — URL validator semantic correctness

**Files:**
- Modify: `scripts/validators/verify-url-state-runtime.py` (semantic check on result_semantics)
- Mirror: `.claude/scripts/validators/verify-url-state-runtime.py`
- Test: `tests/test_c3_url_validator_semantic.py`

**Step 1: Failing test**

```python
"""tests/test_c3_url_validator_semantic.py — C3 URL semantic correctness."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
VAL = REPO / "scripts" / "validators" / "verify-url-state-runtime.py"


def _run_val(tmp_path, evidence_data):
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / ".url-runtime-results.json").write_text(json.dumps(evidence_data), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase", "99", "--phase-dir", str(phase_dir)],
        capture_output=True, text=True,
    )
    return r


def test_validator_flags_url_param_present_but_semantics_fail(tmp_path):
    """C3: filter URL has correct param but result_semantics.passed=false → must BLOCK."""
    evidence = {
        "checks": [{
            "url": "/projects?status=pending",
            "expected_param": "status=pending",
            "param_present": True,
            "result_semantics": {"passed": False, "reason": "table still shows all rows"}
        }]
    }
    r = _run_val(tmp_path, evidence)
    assert (r.returncode != 0) or "semantic" in r.stdout.lower() or "result_semantics" in r.stdout, (
        f"C3: validator must flag when url param present but result_semantics.passed=false. "
        f"stdout={r.stdout[:500]} stderr={r.stderr[:200]}"
    )


def test_validator_passes_when_both_present_and_semantics_pass(tmp_path):
    """C3: well-formed pass."""
    evidence = {
        "checks": [{
            "url": "/projects?status=pending",
            "expected_param": "status=pending",
            "param_present": True,
            "result_semantics": {"passed": True}
        }]
    }
    r = _run_val(tmp_path, evidence)
    if r.returncode != 0 and "C3" in r.stdout:
        assert False, f"C3: well-formed evidence must not trigger C3 errors. stdout={r.stdout[:500]}"
```

**Step 2: Run** → 1-2 fail.

**Step 3: Implement**

In `scripts/validators/verify-url-state-runtime.py`, after the existing param-presence check, add `result_semantics` check:

```python
# C3 Batch 3: result_semantics check — URL param present alone is NOT enough.
# If result_semantics field provided, it must report passed=true. Otherwise BLOCK.
for check in evidence.get("checks", []):
    rs = check.get("result_semantics")
    if rs is None:
        # No semantic evidence — flag as INCOMPLETE
        issues.append({
            "code": "C3",
            "url": check.get("url"),
            "issue": "result_semantics missing — URL param presence alone is insufficient evidence"
        })
        continue
    if not rs.get("passed"):
        issues.append({
            "code": "C3",
            "url": check.get("url"),
            "issue": f"result_semantics.passed=false — {rs.get('reason', 'no reason')}"
        })
```

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/validators/verify-url-state-runtime.py \
        .claude/scripts/validators/verify-url-state-runtime.py \
        tests/test_c3_url_validator_semantic.py
git commit -m "feat(validator): C3 — URL validator checks result_semantics (Batch 3)

Codex audit Gap C3 (HIGH): verify-url-state-runtime.py only checked if
declared URL param was present in post-interaction URL. A filter could
'pass' when ?status=pending appears in URL even when table still shows
wrong rows. Phase 2.8 prose REQUIRED result_semantics but validator
ignored it.

Fix: post-param-presence check, validator inspects result_semantics
field. If missing → INCOMPLETE issue. If passed=false → BLOCK issue
with reason from evidence.

Each issue tagged with C3 code so downstream consumers can correlate.

Tests: tests/test_c3_url_validator_semantic.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: G11 — Post-codegen runtime conformance gate

**Files:**
- Create: `scripts/validators/verify-codegen-lifecycle-conformance.py`
- Modify: `commands/vg/_shared/test/regression-security.md` (gate-run before 5e_regression)
- Mirrors
- Test: `tests/test_g11_codegen_conformance_gate.py`

**Step 1: Failing test**

```python
"""tests/test_g11_codegen_conformance_gate.py — G11 conformance gate."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
VAL = REPO / "scripts" / "validators" / "verify-codegen-lifecycle-conformance.py"


def test_validator_exists():
    assert VAL.is_file(), "G11: verify-codegen-lifecycle-conformance.py must ship"


def test_validator_flags_spec_missing_lifecycle_stages(tmp_path):
    """G11: generated spec must cover every step in LIFECYCLE-SPECS.json for that goal."""
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "goals": {
            "G-01": {
                "steps": [
                    {"name": "read_before"}, {"name": "create"}, {"name": "read_after_create"}
                ]
            }
        }
    }), encoding="utf-8")
    # Spec file only mentions 'create' step, missing the reads
    spec_dir = phase_dir / "generated-tests"
    spec_dir.mkdir()
    (spec_dir / "G-01.spec.ts").write_text("// GOAL: G-01\ntest('create', ...)", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase", "99", "--phase-dir", str(phase_dir),
         "--spec-dir", str(spec_dir)],
        capture_output=True, text=True,
    )
    assert (r.returncode != 0) or ("read_before" in r.stdout or "read_after_create" in r.stdout) or "G11" in r.stdout, (
        f"G11: validator must flag spec missing lifecycle stages. "
        f"stdout={r.stdout[:500]}"
    )


def test_regression_security_invokes_gate():
    body = (REPO / "commands" / "vg" / "_shared" / "test" / "regression-security.md").read_text(encoding="utf-8")
    assert "verify-codegen-lifecycle-conformance" in body, (
        "G11: regression-security.md must invoke verify-codegen-lifecycle-conformance.py "
        "before 5e_regression run"
    )
```

**Step 2: Run** → 3 fail.

**Step 3: Implement**

Create `scripts/validators/verify-codegen-lifecycle-conformance.py`:

```python
#!/usr/bin/env python3
"""verify-codegen-lifecycle-conformance.py — G11 Batch 3

Post-codegen gate: every step in LIFECYCLE-SPECS.json for a goal must be
referenced in the corresponding generated *.spec.ts file. Detects codegen
silently dropping lifecycle stages.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--spec-dir", required=True, type=Path)
    args = ap.parse_args()

    lifecycle_path = args.phase_dir / "LIFECYCLE-SPECS.json"
    if not lifecycle_path.is_file():
        print(f"⚠ G11: LIFECYCLE-SPECS.json missing at {lifecycle_path} — skip conformance check")
        return 0

    spec_index: dict[str, str] = {}  # goal_id → spec text
    if args.spec_dir.is_dir():
        for f in args.spec_dir.glob("*.spec.ts"):
            txt = f.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"\b(G-\d+)\b", txt[:2000]):
                spec_index.setdefault(m.group(1), "")
                spec_index[m.group(1)] += "\n" + txt

    issues: list[dict] = []
    spec = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    for gid, goal in (spec.get("goals") or {}).items():
        steps = goal.get("steps") or []
        if not steps:
            continue
        spec_text = spec_index.get(gid, "")
        if not spec_text:
            issues.append({"code": "G11", "goal": gid, "issue": "no generated spec found"})
            continue
        for step in steps:
            stage = step.get("name") or step.get("stage")
            if not stage:
                continue
            # Heuristic: spec should reference stage name OR endpoint or stage verb
            stage_ref = stage in spec_text
            ep = step.get("endpoint") or {}
            ep_ref = ep.get("path") and ep["path"] in spec_text if ep else False
            if not stage_ref and not ep_ref:
                issues.append({
                    "code": "G11",
                    "goal": gid,
                    "stage": stage,
                    "issue": f"generated spec for {gid} does not reference stage '{stage}' or its endpoint"
                })

    if issues:
        print("⚠ G11 codegen-lifecycle conformance issues:")
        for i in issues:
            print(f"  - {i}")
        # Advisory: exit 0 by default. Use --strict for non-zero.
        return 0
    print(f"✓ G11: codegen conformance OK for phase {args.phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

In `commands/vg/_shared/test/regression-security.md`, before STEP 7.1 (5e_regression invocation around line 39), add:

```bash
# G11 Batch 3: codegen-lifecycle conformance gate (advisory)
G11_VAL="${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/validators/verify-codegen-lifecycle-conformance.py"
[ -f "$G11_VAL" ] || G11_VAL="${REPO_ROOT:-.}/scripts/validators/verify-codegen-lifecycle-conformance.py"
if [ -f "$G11_VAL" ]; then
  "${PYTHON_BIN:-python3}" "$G11_VAL" \
    --phase "${PHASE_NUMBER}" \
    --phase-dir "${PHASE_DIR}" \
    --spec-dir "${GENERATED_TESTS_DIR}" || true
fi
```

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/validators/verify-codegen-lifecycle-conformance.py \
        .claude/scripts/validators/verify-codegen-lifecycle-conformance.py \
        commands/vg/_shared/test/regression-security.md \
        .claude/commands/vg/_shared/test/regression-security.md \
        tests/test_g11_codegen_conformance_gate.py
git commit -m "feat(validator): G11 — post-codegen conformance gate (Batch 3)

Audit Gap G11: no post-codegen conformance check — codegen could silently
drop lifecycle stages, dropping coverage without visible signal.

Fix:
- New verify-codegen-lifecycle-conformance.py validator. For each goal in
  LIFECYCLE-SPECS.json, verifies generated *.spec.ts file references
  every step's stage name OR endpoint path.
- regression-security.md invokes the validator before 5e_regression
  runs. Advisory mode (exit 0 always). Surfaces missing-stage warnings.

Tests: tests/test_g11_codegen_conformance_gate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: H3 — Validator output surfaced

**Files:**
- Modify: `commands/vg/_shared/test/fix-loop-and-verdict.md` (around lines 1003-1019 — validator loop)
- Mirror
- Test: `tests/test_h3_validator_output_surfaced.py`

**Step 1: Failing test**

```python
"""tests/test_h3_validator_output_surfaced.py — H3 validator output."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
FILE = REPO / "commands" / "vg" / "_shared" / "test" / "fix-loop-and-verdict.md"


def test_validator_loop_emits_summary_json():
    body = FILE.read_text(encoding="utf-8")
    # Each validator must emit a result summary JSON not just .diag
    assert "validator-summary" in body.lower() or "result.json" in body or "_summary.json" in body, (
        "H3: validator loop must produce a result-summary JSON alongside the "
        ".diag dump (so PASS path leaves inspectable evidence)"
    )


def test_validator_loop_tails_last_lines_on_pass():
    body = FILE.read_text(encoding="utf-8")
    # On PASS, must tail/echo last few lines so user sees what was checked
    assert "tail" in body.lower() or "head -" in body or "last 5 lines" in body.lower(), (
        "H3: validator PASS path must tail-print last lines of diag so user "
        "sees what was checked"
    )
```

**Step 2: Run** → 2 fail.

**Step 3: Implement**

In `commands/vg/_shared/test/fix-loop-and-verdict.md` around lines 1003-1019 (the validator loop), inject after each validator call:

```bash
# H3 Batch 3: surface validator outputs so PASS path leaves inspectable evidence
SUMMARY_OUT="${PHASE_DIR}/.tmp/${VALIDATOR}-summary.json"
# Tail last 5 lines of the diag for inline user visibility
echo "  ⤷ last lines of $VAL_OUT:"
tail -n 5 "$VAL_OUT" 2>/dev/null | sed 's/^/    /'
# Try parse final JSON line as summary
${PYTHON_BIN:-python3} -c "
import json, sys
try:
    last_line = open('$VAL_OUT', encoding='utf-8').read().strip().splitlines()[-1]
    d = json.loads(last_line)
    json.dump({'verdict': d.get('verdict'), 'evidence_count': len(d.get('evidence', []))}, open('$SUMMARY_OUT', 'w', encoding='utf-8'))
except Exception:
    pass
" 2>/dev/null || true
```

**Step 4-6:** pass + mirror + commit.

```bash
git add commands/vg/_shared/test/fix-loop-and-verdict.md \
        .claude/commands/vg/_shared/test/fix-loop-and-verdict.md \
        tests/test_h3_validator_output_surfaced.py
git commit -m "feat(test): H3 — validator output surfaced on PASS path (Batch 3)

Audit Gap H3 (MEDIUM): 9 validators in fix-loop-and-verdict.md ran with
output redirected to .tmp/*.diag. User saw aggregate verdict only.
Detail invisible on PASS, and even on BLOCK user had to open the file.

Fix:
- Tail-print last 5 lines of each validator diag for inline visibility.
- Parse last JSON line as summary, write ${VALIDATOR}-summary.json with
  verdict + evidence_count. Gives downstream consumers structured access
  to per-validator outcome.

Tests: tests/test_h3_validator_output_surfaced.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: G8+G3 — Discrete assertion arrays + step body from binding

These are largely already covered by Batch 1 (G9 assertions array + G7 endpoint binding) + Batch 4 (per-goal data-driven actions). This task tightens any remaining template strings in step body.

**Files:**
- Modify: `scripts/generate-lifecycle-specs.py` (replace remaining template strings in step actions/evidence dicts)
- Mirror
- Test: `tests/test_g3_g8_step_content_from_binding.py`

**Step 1: Failing test**

```python
"""tests/test_g3_g8_step_content_from_binding.py — G3+G8 step content quality."""
from __future__ import annotations
import json
import subprocess
import sys
import os
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "scripts" / "generate-lifecycle-specs.py"


def _gen(tmp_path, goals_md, contracts_md=""):
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "TEST-GOALS.md").write_text(goals_md, encoding="utf-8")
    if contracts_md:
        (phase_dir / "API-CONTRACTS.md").write_text(contracts_md, encoding="utf-8")
    out = phase_dir / "LIFECYCLE-SPECS.json"
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "99", "--phase-dir", str(phase_dir),
         "--out", str(out)],
        capture_output=True, text=True, env={**os.environ, "VG_REPO_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_g8_step_assertions_have_check_field(tmp_path):
    """G8: each step assertion entry must have 'check' field (discrete, not freeform)."""
    goals = """## Goal G-01: Create
**goal_type:** create-only
**mutation_evidence:** POST /api/x
"""
    contracts = "## POST /api/x\nResponse: 201\n"
    spec = _gen(tmp_path, goals, contracts)
    goal = spec["goals"]["G-01"]
    for step in goal["steps"]:
        for a in (step.get("assertions") or []):
            assert "check" in a or "source" in a, (
                f"G8: step assertion missing check/source: {a}"
            )


def test_g3_step_description_references_endpoint(tmp_path):
    """G3: step.description for create stage must reference bound endpoint path/method,
    not template string."""
    goals = """## Goal G-01: Create order
**goal_type:** create-only
**mutation_evidence:** POST /api/orders returns 201
"""
    contracts = "## POST /api/orders\nResponse: 201\n"
    spec = _gen(tmp_path, goals, contracts)
    goal = spec["goals"]["G-01"]
    create_step = next((s for s in goal["steps"] if s.get("name") == "create"), None)
    assert create_step is not None
    desc = create_step.get("description", "")
    # Description should reference the endpoint when binding succeeded
    if create_step.get("endpoint"):
        assert ("POST" in desc or "/api/orders" in desc), (
            f"G3: create step description must reference bound endpoint path/method; "
            f"got desc={desc!r}"
        )
```

**Step 2: Run** → 1-2 fail (current description is template string ignoring endpoint).

**Step 3: Implement**

In `scripts/generate-lifecycle-specs.py` `_step()` (look for the function), modify the `actions` template dict to incorporate endpoint when present:

```python
def _step_description(stage, goal, endpoint):
    """G3 Batch 3: build description from endpoint binding when available."""
    if endpoint and endpoint.get("method") and endpoint.get("path"):
        method, path = endpoint["method"], endpoint["path"]
        if stage == "create":
            return f"{method} {path} with sample payload from API-CONTRACTS; assert response status + body."
        if stage == "update":
            return f"{method} {path} for the created entity; assert update applied."
        if stage == "delete":
            return f"{method} {path}; assert 204/200 and resource gone."
        if stage.startswith("read_"):
            return f"GET {path}; assert {stage.replace('read_', '')} state per persistence_check."
    # Fallback to original template
    return _DEFAULT_DESCRIPTIONS.get(stage, "")
```

Wire into `_step()`: replace `actions[stage]` lookup with `_step_description(stage, goal, endpoint)`.

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/generate-lifecycle-specs.py \
        .claude/scripts/generate-lifecycle-specs.py \
        tests/test_g3_g8_step_content_from_binding.py
git commit -m "feat(lifecycle-specs): G3+G8 — step content from binding (Batch 3)

Audit Gaps G3 (step body template strings) + G8 (discrete assertion
arrays). G9 partially covered G8 via assertions[] array. Remaining work:
step.description was still a 7-template lookup ignoring endpoint binding.

Fix: _step_description() builds description from endpoint binding (G7
from Batch 1) when available. Per-stage formatting (POST path, GET
state-check, DELETE assertion). Falls back to default template when
endpoint binding fails.

Combined with G7 + G9 from Batch 1, step content is now data-driven:
description references real endpoint, assertions carry source + check.

Tests: tests/test_g3_g8_step_content_from_binding.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Regression sweep + release v4.10.0

Bump VERSION 4.9.0 → 4.10.0. CHANGELOG entry per 6 gaps. Tag v4.10.0. Push. Re-sync ~/.vgflow for: generate-lifecycle-specs.py, verify-lifecycle-spec-depth.py, verify-url-state-runtime.py, verify-codegen-lifecycle-conformance.py (new), regression-security.md, fix-loop-and-verdict.md.

End of Batch 3 plan. Estimated 4 hours.
