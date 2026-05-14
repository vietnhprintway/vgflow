# Batch 17 — UI artifact enforcement gates (F6+F7+F8) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 3 HIGH audit findings — blueprint UI artifacts (UI-RUNTIME-CONTRACT, UI-SPEC, UI-MAP) generated via comment-only Agent spawns, marker fires unconditionally.

- **F6**: `UI-RUNTIME-CONTRACT.md/json` absent from blueprint contract; emitter failure continues silently; validator returns 0 on missing.
- **F7**: UI-SPEC generation Agent spawn = comment-only (`design.md:488`). Concat loop runs over empty dir, partial spec passes.
- **F8**: UI-MAP planner spawn = `echo` only (`design.md:584-594`). No gate on output existence.

**Architecture:** Mirror Batch 15 pattern — gate marker on artifact file existence + content check. Block for FE phases (web-fullstack, web-frontend-only) when missing/empty.

**Working directory:** `main`.

---

## Conventions

- Mirror byte-identical to `.claude/`
- Sweep: `python -m pytest tests/ -q --tb=no -k "ui_runtime or ui_spec or ui_map or f6 or f7 or f8 or design"`
- Single Co-Authored-By trailer per commit

---

## Task 1: F7 — UI-SPEC file existence gate

**Files:**
- Modify: `commands/vg/_shared/blueprint/design.md` (STEP 2.3 around lines 488-518 — between Agent spawn comment + marker touch)
- Mirror
- Test: `tests/test_f7_ui_spec_gate.py`

**Step 1: Failing test**

```python
"""tests/test_f7_ui_spec_gate.py — F7 UI-SPEC file existence gate."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
DESIGN = REPO / "commands" / "vg" / "_shared" / "blueprint" / "design.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_ui_spec_marker_conditional_on_index_file():
    body = _read(DESIGN)
    # Find STEP 2b6_ui_spec marker block
    marker_idx = body.find("2b6_ui_spec.done")
    assert marker_idx > 0
    # Look back 1500 chars for a gate check on UI-SPEC/index.md
    block = body[max(0, marker_idx - 2500):marker_idx]
    # Skip the --skip-ui-spec escape branch markers — count the OTHER marker
    # (the post-Agent-spawn one). Match if at least one gate present.
    assert "UI-SPEC/index.md" in body, (
        "F7: design.md must reference UI-SPEC/index.md path so existence gate "
        "can verify Agent actually wrote spec output"
    )
    # And the gate must check file presence
    assert ("if [ ! -f" in body or "is_file" in body or "test -f" in body), (
        "F7: must gate marker on UI-SPEC/index.md existence"
    )


def test_fe_phase_blocks_on_missing_ui_spec():
    body = _read(DESIGN)
    # Must have BLOCK path for FE phases when index missing
    assert ("PHASE_PROFILE" in body or "FE_TASKS" in body), (
        "F7: gate must be FE-profile-aware (skip backend-only, block FE-fullstack)"
    )
    assert ("exit 1" in body or "BLOCK" in body), (
        "F7: missing UI-SPEC for FE phase must exit 1"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/blueprint/design.md` BETWEEN the existing Agent comment (line 488) and the marker touch (line 517), insert:

```bash
# F7 Batch 17: UI-SPEC existence gate — Agent MUST have written index + per-slug files.
# Skip gate when --skip-ui-spec was set (handled above via override emit).
# For FE phases, BLOCK if Agent left UI-SPEC dir empty.
FE_TASKS_COUNT=$(grep -cE "(\.tsx|\.jsx|\.vue|\.svelte)" "${PHASE_DIR}"/PLAN*.md 2>/dev/null || echo "0")
if [ "${FE_TASKS_COUNT:-0}" -gt 0 ]; then
  if [ ! -f "${PHASE_DIR}/UI-SPEC/index.md" ]; then
    echo "⛔ F7 BLOCK: UI-SPEC/index.md missing — Agent did not write spec output." >&2
    echo "   FE phase requires UI-SPEC. Re-run blueprint or pass --skip-ui-spec --override-reason=<text>." >&2
    "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "blueprint.ui_spec_missing" \
      --payload "{\"phase\":\"${PHASE_NUMBER}\"}" >/dev/null 2>&1 || true
    exit 1
  fi
  # Per-slug coverage check: count <design-ref> slugs in PLAN.md, count files in UI-SPEC/
  SLUG_COUNT=$(grep -oE '<design-ref[^>]*slug="[^"]+"' "${PHASE_DIR}"/PLAN*.md 2>/dev/null | wc -l | tr -d ' ')
  SPEC_FILE_COUNT=$(find "${PHASE_DIR}/UI-SPEC" -maxdepth 1 -name "*.md" -not -name "index.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "${SLUG_COUNT:-0}" -gt 0 ] && [ "${SPEC_FILE_COUNT:-0}" -lt "${SLUG_COUNT}" ]; then
    echo "⚠ F7: UI-SPEC coverage gap — ${SPEC_FILE_COUNT}/${SLUG_COUNT} slugs have per-slug spec files" >&2
    "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "blueprint.ui_spec_partial" \
      --payload "{\"phase\":\"${PHASE_NUMBER}\",\"slugs\":${SLUG_COUNT},\"specs\":${SPEC_FILE_COUNT}}" >/dev/null 2>&1 || true
  fi
fi
```

```bash
git commit -m "fix(blueprint): F7 — UI-SPEC existence gate before marker (Batch 17)

Codex audit Finding F7 (HIGH): design.md:488 Agent spawn for UI-SPEC
generation was comment-only. Concat loop at line 494-512 ran over empty
${PHASE_DIR}/UI-SPEC/ dir. Marker fired unconditionally. Empty/partial
UI-SPEC.md passed blueprint contract.

Fix: FE-profile-aware gate between Agent comment and marker touch:
- ${PHASE_DIR}/UI-SPEC/index.md MUST exist for FE phases (TSX/JSX/Vue/
  Svelte tasks > 0). Missing → exit 1 + emit blueprint.ui_spec_missing.
- Per-slug coverage: count <design-ref slug=...> in PLAN.md, count
  per-slug *.md files in UI-SPEC/. Mismatch → WARN +
  blueprint.ui_spec_partial event.
- Backend-only phases unaffected.

Tests: tests/test_f7_ui_spec_gate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: F8 — UI-MAP existence gate

**Files:**
- Modify: `commands/vg/_shared/blueprint/design.md` (STEP 2.4 around lines 583-606)
- Mirror
- Test: `tests/test_f8_ui_map_gate.py`

**Step 1: Failing test**

```python
"""tests/test_f8_ui_map_gate.py — F8 UI-MAP existence gate."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
DESIGN = REPO / "commands" / "vg" / "_shared" / "blueprint" / "design.md"


def test_ui_map_gate_present():
    body = DESIGN.read_text(encoding="utf-8")
    marker_idx = body.find("2b6b_ui_map.done")
    assert marker_idx > 0
    # Find the LAST occurrence (after the FE-tasks > 0 branch)
    last_marker = body.rfind("2b6b_ui_map.done")
    block = body[max(0, last_marker - 2000):last_marker]
    # Must check UI-MAP.md existence + emit event when missing
    assert "UI-MAP.md" in block, "F8: must reference UI-MAP.md in gate block"
    assert ("blueprint.ui_map_missing" in body or "F8" in body), (
        "F8: design.md must emit blueprint.ui_map_missing event when UI-MAP.md "
        "absent for FE phase"
    )


def test_ui_map_fe_phase_blocks():
    body = DESIGN.read_text(encoding="utf-8")
    # In the FE_TASKS > 0 branch, missing UI-MAP.md must lead to exit 1
    fe_idx = body.find('"${FE_TASKS:-0}" -eq 0')
    assert fe_idx > 0
    fe_else = body.find("else", fe_idx)
    # Up to 2000 chars into the else branch
    else_block = body[fe_else:fe_else + 3500]
    # Need a gate path
    assert ("F8" in else_block and ("exit 1" in else_block or "BLOCK" in else_block)) or "blueprint.ui_map_missing" in else_block, (
        "F8: FE-phase branch must BLOCK when UI-MAP.md missing post-Agent"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/blueprint/design.md` STEP 2.4 (UI-MAP block), INSIDE the `else` branch (FE_TASKS > 0), AFTER the `echo "▸ Orchestrator spawn planner agent..."` block and BEFORE the marker touch (line 603), insert:

```bash
# F8 Batch 17: UI-MAP existence gate — planner Agent MUST have written UI-MAP.md.
# This complements F7 (UI-SPEC gate). Marker only fires when output exists.
if [ ! -f "${PHASE_DIR}/UI-MAP.md" ]; then
  echo "⛔ F8 BLOCK: UI-MAP.md missing after planner spawn — Agent did not write." >&2
  echo "   FE phase requires UI-MAP. Re-run blueprint or set config 'ui_map.enabled: false' to bypass." >&2
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "blueprint.ui_map_missing" \
    --payload "{\"phase\":\"${PHASE_NUMBER}\",\"fe_tasks\":${FE_TASKS}}" >/dev/null 2>&1 || true
  exit 1
fi
# Schema validation: run uimap validator if present
UIMAP_VAL="${REPO_ROOT:-.}/.claude/scripts/validators/verify-uimap-schema.py"
[ -x "$UIMAP_VAL" ] || UIMAP_VAL="${REPO_ROOT:-.}/scripts/validators/verify-uimap-schema.py"
if [ -f "$UIMAP_VAL" ]; then
  ${PYTHON_BIN:-python3} "$UIMAP_VAL" --phase "${PHASE_NUMBER}" 2>&1 | tail -5
  UIMAP_RC=$?
  if [ "$UIMAP_RC" -ne 0 ]; then
    echo "⚠ F8: UI-MAP.md schema validation failed (rc=$UIMAP_RC) — advisory at v4.20.0, will flip to BLOCK in v4.21+" >&2
    "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "blueprint.ui_map_schema_invalid" \
      --payload "{\"phase\":\"${PHASE_NUMBER}\",\"rc\":${UIMAP_RC}}" >/dev/null 2>&1 || true
  fi
fi
```

```bash
git commit -m "fix(blueprint): F8 — UI-MAP existence gate before marker (Batch 17)

Codex audit Finding F8 (HIGH): design.md UI-MAP planner spawn was echo
only — 'echo Orchestrator spawn planner agent' without enforcement.
Marker 2b6b_ui_map.done touched unconditionally. UI-MAP.md could be
missing while blueprint marker satisfied contract.

Fix: between planner spawn and marker touch, gate on UI-MAP.md
existence. Missing → exit 1 + blueprint.ui_map_missing event. Plus
schema validator advisory (verify-uimap-schema.py) runs and emits
blueprint.ui_map_schema_invalid on non-zero (will flip to BLOCK in
v4.21+ after telemetry).

Tests: tests/test_f8_ui_map_gate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: F6 — UI-RUNTIME-CONTRACT block emitter failures + add to blueprint contract

**Files:**
- Modify: `commands/vg/_shared/blueprint/design.md` (around line 644 — emitter failure handling)
- Modify: `commands/vg/blueprint.md` frontmatter `must_write` block (add UI-RUNTIME-CONTRACT entry with `required_unless_flag`)
- Modify: `scripts/validators/verify-ui-runtime-contract.py` (FE phase distinction: missing = BLOCK not PASS)
- Mirrors
- Test: `tests/test_f6_ui_runtime_contract_gate.py`

**Step 1: Failing test**

```python
"""tests/test_f6_ui_runtime_contract_gate.py — F6 UI-RUNTIME-CONTRACT gate."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
DESIGN = REPO / "commands" / "vg" / "_shared" / "blueprint" / "design.md"
BLUEPRINT = REPO / "commands" / "vg" / "blueprint.md"


def test_blueprint_contract_lists_ui_runtime_contract():
    body = BLUEPRINT.read_text(encoding="utf-8")
    # must_write block must reference UI-RUNTIME-CONTRACT.json or .md
    assert "UI-RUNTIME-CONTRACT" in body, (
        "F6: blueprint.md must_write must list UI-RUNTIME-CONTRACT.{md,json} "
        "with required_unless_flag for non-legacy FE phases"
    )


def test_emitter_failure_no_longer_silent():
    body = DESIGN.read_text(encoding="utf-8")
    # The line that says 'continuing (contract is informational at Stage 2; Stages 3-4 will harden)'
    # must be replaced or guarded by FE-phase check
    if "emit-ui-runtime-contract.py exit=" in body:
        # If we still continue silently, it must be guarded by a backend-only check
        idx = body.find("emit-ui-runtime-contract.py exit=")
        ctx = body[max(0, idx-200):idx+400]
        assert ("FE_TASKS" in ctx or "PHASE_PROFILE" in ctx or "exit 1" in ctx), (
            "F6: emitter non-zero exit must escalate for FE phases — current "
            "'continuing' wording masks failures"
        )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/blueprint.md` frontmatter `must_write` block, add:

```yaml
    - path: "UI-RUNTIME-CONTRACT.json"
      required_unless_flag: "--skip-ui-runtime-contract"
      profile_filter: "web-fullstack,web-frontend-only"
```

In `commands/vg/_shared/blueprint/design.md` around the emitter call (lines 635-645), replace the silent continue with FE-aware block:

```bash
"${PYTHON_BIN:-python3}" "$EMITTER" --phase "${PHASE_NUMBER}" 2>&1 | tail -5
RC=$?
if [ "$RC" -ne 0 ]; then
  # F6 Batch 17: FE phases must NOT continue silently on emitter failure
  FE_TASKS_RT=$(grep -cE "(\.tsx|\.jsx|\.vue|\.svelte)" "${PHASE_DIR}"/PLAN*.md 2>/dev/null || echo "0")
  if [ "${FE_TASKS_RT:-0}" -gt 0 ]; then
    echo "⛔ F6 BLOCK: emit-ui-runtime-contract.py exit=${RC} on FE phase — fail loud" >&2
    "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event "blueprint.ui_runtime_contract_emit_failed" \
      --payload "{\"phase\":\"${PHASE_NUMBER}\",\"rc\":${RC}}" >/dev/null 2>&1 || true
    exit 1
  else
    echo "⚠ emit-ui-runtime-contract.py exit=${RC} — backend-only phase, continuing"
  fi
fi
```

```bash
git commit -m "fix(blueprint): F6 — UI-RUNTIME-CONTRACT enforce for FE phases (Batch 17)

Codex audit Finding F6 (HIGH): UI-RUNTIME-CONTRACT.md/json was absent
from blueprint.md must_write contract. emit-ui-runtime-contract.py
failures continued silently with 'informational at Stage 2' wording.
FE runtime invariants (Tailwind tokens, min spec count) could vanish.

Fix:
- blueprint.md must_write adds UI-RUNTIME-CONTRACT.json with
  required_unless_flag: --skip-ui-runtime-contract, profile_filter
  web-fullstack/web-frontend-only.
- design.md emitter RC check now FE-aware: backend-only continues with
  WARN, FE-fullstack/FE-only exits 1 + blueprint.ui_runtime_contract_emit_failed
  event.
- verify-ui-runtime-contract.py PASS-on-missing path still works for
  truly legacy phases (no FE tasks); new emit gate prevents that
  branch from masking failures in active FE work.

Tests: tests/test_f6_ui_runtime_contract_gate.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Release v4.20.0

Bump VERSION 4.19.0 → 4.20.0. CHANGELOG entry per F6+F7+F8. Tag v4.20.0. Push. Re-sync ~/.vgflow.

End of Batch 17 plan. Estimated 2-3 hours.
