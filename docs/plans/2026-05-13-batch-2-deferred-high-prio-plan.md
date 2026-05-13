# Batch 2 — High-priority deferred items (G2 + G14 + C8 + C11) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 4 high-priority gaps: per-verb stage derivation (G2), read-only goal lifecycle (G14), Phase 2a proof split (C8), URL skip-flag canonical status (C11).

**Source:** `docs/plans/2026-05-13-pipeline-flow-audit.md` + `docs/plans/2026-05-13-lifecycle-specs-redesign-design.md`.

**Tech Stack:** Python + bash. No deps.

**Working directory:** `main`.

---

## Conventions

- Python: `from __future__ import annotations`, type-hinted
- Mirror byte-identical to `.claude/`
- Regression sweep: `python -m pytest tests/ -q --tb=no -k "lifecycle or phase2a or url or read_only or g2 or g14 or c8 or c11"`
- Single `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` per commit

---

## Task 1: C8 — Phase 2a proof reuse splits cleanly

**Files:**
- Modify: `commands/vg/_shared/review/api-and-discovery.md` (lines 47-57 skip-remainder block)
- Mirror: `.claude/commands/vg/_shared/review/api-and-discovery.md`
- Test: `tests/test_c8_phase2a_proof_split.py`

**Step 1: Failing test**

```python
"""tests/test_c8_phase2a_proof_split.py — C8 Phase 2a proof split."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
CANON = REPO / "commands" / "vg" / "_shared" / "review" / "api-and-discovery.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_proof_reuse_does_not_skip_interface_standards():
    body = _read(CANON)
    # When PROOF_FRESH=true block must NOT short-circuit the whole phase2a
    # Look for the proof-reuse block — it must NOT skip interface + api-docs
    proof_block_start = body.find("PROOF_FRESH=\"true\"")
    if proof_block_start < 0:
        proof_block_start = body.find('PROOF_FRESH" = "true"')
    assert proof_block_start > 0
    # The interface-standards validator MUST still run after proof reuse
    # Check that the block doesn't end with raw "else" that gates ALL remaining work
    proof_block = body[proof_block_start:proof_block_start + 1500]
    assert "Skip remainder of phase2a" not in proof_block or "Skip live probe only" in proof_block, (
        "C8: proof reuse must NOT skip the remainder of phase2a (interface "
        "standards + api-docs coverage). Only the live runtime probe is "
        "skipped — other validators each need their own proof or fresh run."
    )


def test_interface_standards_runs_under_both_paths():
    body = _read(CANON)
    # The interface-standards validator block must be reached regardless of
    # proof status. Inspect structure: interface val should NOT be inside the
    # `else` branch of `if PROOF_FRESH`.
    proof_idx = body.find('PROOF_FRESH" = "true"')
    interface_idx = body.find('INTERFACE_VAL=')
    if interface_idx < 0:
        interface_idx = body.find('INTERFACE_VAL="')
    assert proof_idx > 0 and interface_idx > 0
    # Interface val must come AFTER proof-fresh block ends (fi) OR be outside the if
    # Simplest check: find the matching `fi` after PROOF_FRESH and ensure
    # INTERFACE_VAL is BEFORE the conditional or AFTER the closing fi.
    # New behavior: INTERFACE_VAL should be reached in BOTH paths.
    # Look for marker comment confirming the split.
    assert ("C8 Batch 2" in body or
            "proof reuse only skips live probe" in body.lower() or
            "interface standards still runs" in body.lower()), (
        "C8: api-and-discovery.md must contain a comment marking the split "
        "fix (e.g. 'C8 Batch 2: proof reuse only skips live probe')"
    )


def test_api_docs_coverage_runs_under_both_paths():
    body = _read(CANON)
    # verify-api-docs-coverage.py invocation must NOT be inside the
    # `else` branch of `if PROOF_FRESH`
    docs_idx = body.find("verify-api-docs-coverage.py")
    assert docs_idx > 0, "api-docs coverage validator must be invoked"
    # Same comment marker check serves as proxy
    assert ("C8 Batch 2" in body or "interface + api-docs still run" in body.lower()), (
        "C8: api-docs coverage must run under proof-reused path too"
    )
```

**Step 2: Run** → 3 fail.

**Step 3: Implement**

In `commands/vg/_shared/review/api-and-discovery.md` around lines 47-58, refactor:

OLD:
```bash
if [ "$PROOF_FRESH" = "true" ]; then
  echo "phase2a: reusing fresh contract-runtime proof from build close (skip runtime probe)"
  cp "$PROOF_ARTIFACT" "${PHASE_DIR}/.api-contract-probe.json"
  # Mark step done without invoking probe script
  ...
  # Skip remainder of phase2a — proof is the evidence
else
  # Fall through to existing fresh-probe path (review-api-contract-probe.py)
  ...
```

NEW (proof reuse skips ONLY live probe; interface + api-docs still run):
```bash
# C8 Batch 2: proof reuse only skips live probe — interface + api-docs still run
SKIP_LIVE_PROBE=false
if [ "$PROOF_FRESH" = "true" ]; then
  echo "phase2a: reusing fresh contract-runtime proof from build close (skip live probe only)"
  cp "$PROOF_ARTIFACT" "${PHASE_DIR}/.api-contract-probe.json"
  SKIP_LIVE_PROBE=true
  "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/vg-orchestrator" emit-event \
    "review.phase2a_proof_reused" \
    --payload "{\"phase\":\"${PHASE_NUMBER:-${PHASE_ARG}}\",\"scope\":\"live_probe_only\"}" \
    >/dev/null 2>&1 || true
fi

if [ "$SKIP_LIVE_PROBE" != "true" ]; then
  # Fall through to existing fresh-probe path (review-api-contract-probe.py)
  echo "phase2a: no fresh proof artifact, running fresh runtime probe"

  if [ ! -f "$PROBE_SCRIPT" ]; then
    ... (unchanged probe-missing block) ...
  fi
fi

# C8: interface-standards + api-docs coverage ALWAYS run, regardless of proof status
mkdir -p "${PHASE_DIR}/.tmp" 2>/dev/null
INTERFACE_VAL="${VG_SCRIPT_ROOT}/validators/verify-interface-standards.py"
if [ -f "$INTERFACE_VAL" ]; then
  ... (existing interface-standards block) ...
fi

"${PYTHON_BIN:-python3}" ${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/validators/verify-api-docs-coverage.py \
  ... (existing api-docs block) ...
```

The actual refactor: convert the existing `if PROOF_FRESH=true ... else ... fi` structure (lines 47-around-130) so that the interface-standards + api-docs blocks (currently inside the `else` branch) live OUTSIDE the if/else, running unconditionally. The if/else only controls whether the live probe script runs.

Mark step write happens at the very end (existing pattern at line 225).

**Step 4-6:** pass + mirror + commit.

```bash
git add commands/vg/_shared/review/api-and-discovery.md \
        .claude/commands/vg/_shared/review/api-and-discovery.md \
        tests/test_c8_phase2a_proof_split.py
git commit -m "fix(review): C8 — Phase 2a proof reuse splits cleanly (Batch 2)

Codex audit Gap C8 (HIGH): if .contract-runtime-report.json fresh, phase2a
short-circuited and skipped interface-standards + api-docs coverage in
addition to live probe. Review proceeded to browser discovery on stale
docs/semantics with one runtime-contract artifact as proxy for distinct
subgates.

Fix: proof reuse only skips the live runtime probe. Interface standards
+ api-docs coverage validators always run, regardless of proof status.
Each subgate has its own evidence stream.

Event payload review.phase2a_proof_reused now carries scope=live_probe_only.

Tests: tests/test_c8_phase2a_proof_split.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: G2 — Per-verb stage derivation in generate-lifecycle-specs.py

**Files:**
- Modify: `scripts/generate-lifecycle-specs.py` (REQUIRED_STAGES + stage selection per goal)
- Mirror: `.claude/scripts/generate-lifecycle-specs.py`
- Test: `tests/test_g2_per_verb_stages.py`

**Step 1: Failing test**

```python
"""tests/test_g2_per_verb_stages.py — G2 per-verb stage derivation."""
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


def test_create_only_goal_has_short_lifecycle(tmp_path):
    """v5.0 G2: create-only goal → R+C+R (3 stages, not full 7)."""
    goals = """## Goal G-01: User creates note

**goal_type:** create-only
**Surface:** api
**mutation_evidence:** POST /api/notes returns 201
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-01"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    # Create-only must have read_before + create + read_after_create only
    assert "create" in stage_names
    assert "read_after_create" in stage_names
    # Must NOT have delete or update stages
    assert "delete" not in stage_names, (
        f"G2: create-only goal should not have delete stage; got {stage_names}"
    )
    assert "update" not in stage_names, (
        f"G2: create-only goal should not have update stage; got {stage_names}"
    )


def test_delete_only_goal_has_short_lifecycle(tmp_path):
    """v5.0 G2: delete-only goal → R+D+R (no create/update)."""
    goals = """## Goal G-02: User deletes existing note

**goal_type:** delete-only
**Surface:** api
**mutation_evidence:** DELETE /api/notes/:id returns 204
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-02"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    assert "delete" in stage_names
    assert "read_after_delete" in stage_names
    assert "create" not in stage_names, (
        f"G2: delete-only goal should not have create stage; got {stage_names}"
    )
    assert "update" not in stage_names


def test_full_mutation_goal_keeps_rcrurdr(tmp_path):
    """v5.0 G2: full CRUD goal → R+C+R+U+R+D+R (7 stages)."""
    goals = """## Goal G-03: Full CRUD on tasks

**goal_type:** mutation
**Surface:** api
**mutation_evidence:** POST/PUT/DELETE /api/tasks
"""
    spec = _gen(tmp_path, goals)
    goal = spec["goals"]["G-03"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    # Full RCRURDR
    assert "create" in stage_names
    assert "update" in stage_names
    assert "delete" in stage_names
    # 7 stages
    assert len(goal["steps"]) >= 6  # tolerant for goals where read_before merges
```

**Step 2: Run** → 2-3 fail (current generator uses fixed REQUIRED_STAGES tuple line 25).

**Step 3: Implement**

In `scripts/generate-lifecycle-specs.py` around line 25 (REQUIRED_STAGES):

OLD:
```python
REQUIRED_STAGES = (
    "read_before",
    "create",
    "read_after_create",
    "update",
    "read_after_update",
    "delete",
    "read_after_delete",
)
```

NEW: add per-goal stage derivation function. Keep REQUIRED_STAGES as fallback default:

```python
REQUIRED_STAGES = (
    "read_before",
    "create",
    "read_after_create",
    "update",
    "read_after_update",
    "delete",
    "read_after_delete",
)

# G2 Batch 2: per-verb stage derivation — shorten lifecycle for non-full-CRUD goals.
GOAL_TYPE_STAGES = {
    "create-only": ("read_before", "create", "read_after_create"),
    "update-only": ("read_before", "update", "read_after_update"),
    "delete-only": ("read_before", "delete", "read_after_delete"),
    "read-only":   ("read_before",),  # G14 covered separately
}


def _stages_for_goal(goal: dict) -> tuple[str, ...]:
    """Derive lifecycle stages per goal_type. Default RCRURDR for full mutation."""
    gtype = (goal.get("goal_type") or "").strip().lower()
    if gtype in GOAL_TYPE_STAGES:
        return GOAL_TYPE_STAGES[gtype]
    # Inspect mutation_evidence + persistence_check for HTTP verb hints
    evidence = " ".join(str(goal.get(k) or "") for k in ("mutation_evidence", "persistence_check", "title")).upper()
    has_post = "POST " in evidence or " POST" in evidence
    has_put_patch = "PUT " in evidence or "PATCH " in evidence
    has_del = "DELETE " in evidence
    if has_post and not has_put_patch and not has_del:
        return GOAL_TYPE_STAGES["create-only"]
    if has_del and not has_post and not has_put_patch:
        return GOAL_TYPE_STAGES["delete-only"]
    if has_put_patch and not has_post and not has_del:
        return GOAL_TYPE_STAGES["update-only"]
    return REQUIRED_STAGES
```

Find the `_goal_spec()` function and replace its `for stage in REQUIRED_STAGES` loop with `for stage in _stages_for_goal(goal)`.

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/generate-lifecycle-specs.py \
        .claude/scripts/generate-lifecycle-specs.py \
        tests/test_g2_per_verb_stages.py
git commit -m "feat(lifecycle-specs): G2 — per-verb stage derivation (Batch 2)

Audit Gap G2: REQUIRED_STAGES was a fixed 7-tuple. Delete-only goals
got R+C+R+U+R+D+R lifecycle with no-op create/update stages — codegen
had to skip them later, downstream noise.

Fix: GOAL_TYPE_STAGES map + _stages_for_goal() heuristic. Goal types
'create-only', 'update-only', 'delete-only' get 3-stage lifecycle.
Bare 'mutation' goals fall back to RCRURDR. HTTP verb inference from
mutation_evidence text used as secondary signal when goal_type unset.

Tests: tests/test_g2_per_verb_stages.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: G14 — Read-only goals get lifecycle

**Files:**
- Modify: `scripts/generate-lifecycle-specs.py` (read-only goal handling)
- Mirror: `.claude/scripts/generate-lifecycle-specs.py`
- Test: `tests/test_g14_read_only_lifecycle.py`

**Step 1: Failing test**

```python
"""tests/test_g14_read_only_lifecycle.py — G14 read-only goal lifecycle."""
from __future__ import annotations
import json
import subprocess
import sys
import os
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "scripts" / "generate-lifecycle-specs.py"


def _gen(tmp_path, goals_md):
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "TEST-GOALS.md").write_text(goals_md, encoding="utf-8")
    out = phase_dir / "LIFECYCLE-SPECS.json"
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "99", "--phase-dir", str(phase_dir),
         "--out", str(out)],
        capture_output=True, text=True, env={**os.environ, "VG_REPO_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_read_only_goal_produces_lifecycle(tmp_path):
    """v5.0 G14: read-only goal must produce read_before + filter_check steps."""
    goals = """## Goal G-01: User lists pending tasks

**goal_type:** read-only
**Surface:** api
**persistence_check:** GET /api/tasks?status=pending returns filtered list
"""
    spec = _gen(tmp_path, goals)
    assert "G-01" in spec["goals"]
    goal = spec["goals"]["G-01"]
    stage_names = [s.get("name") or s.get("stage") for s in goal["steps"]]
    assert "read_before" in stage_names, (
        "G14: read-only goal must have read_before stage (precondition + assertion)"
    )
    # Read-only goal lifecycle MUST NOT have create/update/delete
    assert "create" not in stage_names
    assert "update" not in stage_names
    assert "delete" not in stage_names


def test_read_only_goal_endpoint_binding(tmp_path):
    """G14: read-only step should bind GET endpoint from API-CONTRACTS when present."""
    goals = """## Goal G-02: List active users

**goal_type:** read-only
**persistence_check:** GET /api/users?active=true
"""
    contracts = """## GET /api/users
Response: 200 user list
"""
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    (phase_dir / "TEST-GOALS.md").write_text(goals, encoding="utf-8")
    (phase_dir / "API-CONTRACTS.md").write_text(contracts, encoding="utf-8")
    out = phase_dir / "LIFECYCLE-SPECS.json"
    r = subprocess.run(
        [sys.executable, str(GEN), "--phase", "99", "--phase-dir", str(phase_dir),
         "--out", str(out)],
        capture_output=True, text=True, env={**os.environ, "VG_REPO_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    spec = json.loads(out.read_text(encoding="utf-8"))
    goal = spec["goals"]["G-02"]
    rb = next((s for s in goal["steps"] if (s.get("name") or s.get("stage")) == "read_before"), None)
    assert rb is not None
    # endpoint binding should resolve GET
    if rb.get("endpoint") is not None:
        assert rb["endpoint"]["method"] == "GET"
```

**Step 2: Run** → 1-2 fail (current generator may not produce lifecycle for read-only; check).

**Step 3: Implement**

In `_stages_for_goal()` from Task 2, the "read-only" entry already maps to `("read_before",)`. Just verify the existing `_step()` produces valid output for read_before stage when goal_type=read-only. If the step output is empty/broken for read-only goals, extend the `actions` + `evidence` dicts in `_step()` to support `read-only` semantics (precondition + filter assertion).

Update `_step()` action template for read_before when goal_type=read-only:

```python
def _step(stage, goal, actor_id, contracts, decisions, decision_refs):
    ...
    actions = {
        ...
        "read_before": _read_before_action(goal),
    }
    ...


def _read_before_action(goal: dict) -> str:
    """Build read_before action description. Special-case read-only goals."""
    gtype = (goal.get("goal_type") or "").strip().lower()
    if gtype == "read-only":
        pc = goal.get("persistence_check") or ""
        return f"Execute read endpoint and assert filter/result semantics: {pc}"
    return "Read baseline via read endpoint or DB query from TEST-GOALS; assert target entity absent or initial state matches precondition."
```

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/generate-lifecycle-specs.py \
        .claude/scripts/generate-lifecycle-specs.py \
        tests/test_g14_read_only_lifecycle.py
git commit -m "feat(lifecycle-specs): G14 — read-only goals get lifecycle (Batch 2)

Audit Gap G14: read-only goals (e.g. 'list pending tasks',
'filter by status') were skipped by lifecycle generator. Coverage hole
— v4.0 review chains to test, test runs no lifecycle for these goals.

Fix:
- GOAL_TYPE_STAGES adds 'read-only' → ('read_before',) single-stage
  lifecycle.
- _read_before_action() special-cases read-only to produce a filter-
  assertion action description from persistence_check field.
- Endpoint binding (G7) still works — _bind_endpoint() resolves GET
  for read_before stage.

Tests: tests/test_g14_read_only_lifecycle.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: C11 — URL canonical status enum

**Files:**
- Create: `scripts/emit-url-runtime-status.py`
- Modify: `commands/vg/_shared/review/url-and-error.md` (emit at end)
- Mirror: `.claude/scripts/emit-url-runtime-status.py` + `.claude/commands/vg/_shared/review/url-and-error.md`
- Test: `tests/test_c11_url_runtime_status.py`

**Step 1: Failing test**

```python
"""tests/test_c11_url_runtime_status.py — C11 canonical URL status."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
EMITTER = REPO / "scripts" / "emit-url-runtime-status.py"
URL_MD = REPO / "commands" / "vg" / "_shared" / "review" / "url-and-error.md"


def test_emitter_exists():
    assert EMITTER.is_file(), "C11: scripts/emit-url-runtime-status.py must ship"


def test_emitter_writes_canonical_state(tmp_path):
    phase_dir = tmp_path / "phase"
    phase_dir.mkdir()
    r = subprocess.run(
        [sys.executable, str(EMITTER), "--phase-dir", str(phase_dir),
         "--state", "skipped", "--reason", "--skip-runtime flag set"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    status_file = phase_dir / "url-runtime-status.json"
    assert status_file.is_file()
    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["state"] == "skipped"
    assert data["reason"]


def test_emitter_rejects_invalid_state(tmp_path):
    phase_dir = tmp_path / "phase"
    phase_dir.mkdir()
    r = subprocess.run(
        [sys.executable, str(EMITTER), "--phase-dir", str(phase_dir),
         "--state", "BOGUS"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "invalid" in r.stderr.lower() or "choices" in r.stderr.lower()


def test_url_md_emits_canonical_status():
    body = URL_MD.read_text(encoding="utf-8")
    assert "emit-url-runtime-status.py" in body, (
        "C11: url-and-error.md must invoke emit-url-runtime-status.py at end "
        "of phase 2.8 to produce canonical url-runtime-status.json"
    )
    # Must emit state in {passed, drift, skipped, unexecuted, waived}
    for st in ("passed", "drift", "skipped", "unexecuted", "waived"):
        assert st in body, f"C11: url-and-error.md must reference state '{st}'"
```

**Step 2: Run** → 3-4 fail.

**Step 3: Implement**

Create `scripts/emit-url-runtime-status.py`:

```python
#!/usr/bin/env python3
"""emit-url-runtime-status.py — C11 Batch 2

Single canonical URL runtime status artifact. Replaces 3 fragmented skip/waive
flags (--allow-no-url-sync, --skip-runtime, --allow-runtime-drift) with one
status enum that downstream consumers can rely on.

Schema:
{
  "phase": "<N>",
  "ts": "<ISO>",
  "state": "passed|drift|skipped|unexecuted|waived",
  "reason": "<text>",
  "flags": {<original flags for audit>},
  "evidence_ref": "<optional path>"
}
"""
from __future__ import annotations
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


STATES = ["passed", "drift", "skipped", "unexecuted", "waived"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--state", required=True, choices=STATES)
    ap.add_argument("--reason", default="")
    ap.add_argument("--flags-json", default="{}")
    ap.add_argument("--evidence-ref", default="")
    ap.add_argument("--phase", default="")
    args = ap.parse_args()

    try:
        flags = json.loads(args.flags_json)
    except json.JSONDecodeError:
        flags = {}

    data = {
        "phase": args.phase or args.phase_dir.name,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": args.state,
        "reason": args.reason,
        "flags": flags,
    }
    if args.evidence_ref:
        data["evidence_ref"] = args.evidence_ref

    args.phase_dir.mkdir(parents=True, exist_ok=True)
    out = args.phase_dir / "url-runtime-status.json"
    fd, tmp = tempfile.mkstemp(dir=str(args.phase_dir), prefix=".url-runtime-status.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, out)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    print(f"url-runtime-status: state={args.state} reason={args.reason or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

In `commands/vg/_shared/review/url-and-error.md`, find the end of phase 2.8 verdict section. Append:

```bash
# C11 Batch 2: emit canonical url-runtime-status.json for downstream consumers
URL_EMIT="${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/emit-url-runtime-status.py"
[ -f "$URL_EMIT" ] || URL_EMIT="${REPO_ROOT:-.}/scripts/emit-url-runtime-status.py"

# Resolve state — precedence:
#   --skip-runtime  → state=skipped
#   --allow-no-url-sync (declaration waiver) → state=waived
#   --allow-runtime-drift (drift waiver)     → state=drift
#   no runtime evidence captured → state=unexecuted
#   default                                  → state=passed
URL_RUNTIME_STATE="passed"
URL_RUNTIME_REASON=""
if echo "${ARGUMENTS:-}" | grep -q -- "--skip-runtime"; then
  URL_RUNTIME_STATE="skipped"
  URL_RUNTIME_REASON="--skip-runtime flag set"
elif echo "${ARGUMENTS:-}" | grep -q -- "--allow-no-url-sync"; then
  URL_RUNTIME_STATE="waived"
  URL_RUNTIME_REASON="--allow-no-url-sync (declaration waiver)"
elif echo "${ARGUMENTS:-}" | grep -q -- "--allow-runtime-drift"; then
  URL_RUNTIME_STATE="drift"
  URL_RUNTIME_REASON="--allow-runtime-drift (drift waiver)"
elif [ ! -f "${PHASE_DIR}/url-runtime-evidence.json" ] && [ ! -f "${PHASE_DIR}/.url-runtime-results.json" ]; then
  URL_RUNTIME_STATE="unexecuted"
  URL_RUNTIME_REASON="no runtime evidence captured"
fi

if [ -f "$URL_EMIT" ]; then
  "${PYTHON_BIN:-python3}" "$URL_EMIT" \
    --phase-dir "${PHASE_DIR}" \
    --phase "${PHASE_NUMBER:-${PHASE_ARG:-unknown}}" \
    --state "${URL_RUNTIME_STATE}" \
    --reason "${URL_RUNTIME_REASON}" \
    --flags-json "{\"args\":\"${ARGUMENTS:-}\"}" || true
fi
```

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/emit-url-runtime-status.py \
        .claude/scripts/emit-url-runtime-status.py \
        commands/vg/_shared/review/url-and-error.md \
        .claude/commands/vg/_shared/review/url-and-error.md \
        tests/test_c11_url_runtime_status.py
git commit -m "feat(review): C11 — canonical url-runtime-status.json (Batch 2)

Codex audit Gap C11 (MEDIUM): URL runtime check had 3 fragmented bypass
flags (--allow-no-url-sync declaration waiver, --skip-runtime suppression,
--allow-runtime-drift drift waiver). Downstream lanes couldn't distinguish
'passed' from 'not executed'. WARN-only validator path provided no
canonical status.

Fix:
- scripts/emit-url-runtime-status.py: atomic writer for
  url-runtime-status.json with state enum {passed|drift|skipped|
  unexecuted|waived} + reason + flags audit trail.
- url-and-error.md emits at end of phase 2.8 with state resolved via
  flag precedence + evidence presence check.

Downstream lanes (test, accept) can read state directly without re-
parsing flags.

Tests: tests/test_c11_url_runtime_status.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Regression sweep + release v4.7.0

**Step 1:** Sweep:

```bash
python -m pytest tests/ -q --tb=no
```

Baseline: 32-33 pre-existing fail / 2148+ pass. No new regressions.

**Step 2:** Bump VERSION `4.6.0` → `4.7.0`. Update `package.json`.

**Step 3:** CHANGELOG entry per gaps closed.

**Step 4:** Commit + tag + push v4.7.0.

**Step 5:** Re-sync ~/.vgflow for modified files (api-and-discovery.md, generate-lifecycle-specs.py, url-and-error.md, emit-url-runtime-status.py).

---

End of Batch 2 plan. Estimated 3-4 hours engineering wall-clock.
