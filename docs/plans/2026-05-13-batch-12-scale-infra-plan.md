# Batch 12 — Scale infrastructure (F6+F7+F8+F9) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close last 4 findings from `docs/plans/2026-05-13-flow-chain-audit.md`. Lift scale verdict from FAIL to PASS for 50+ phase, multi-domain projects.

- **F6 (HIGH)**: Phase number width `zfill(2)` hardcoded across 14+ scripts. Breaks at 100+ phases or `07.10.1` sub-phase notation.
- **F7 (HIGH)**: No domain/team isolation. Parallel teams cannot run concurrent phases safely without coordination outside pipeline tooling.
- **F8 (HIGH)**: `test/close.md` next_command was wired in Batch 10 (F1), but `accept/preflight.md` doesn't cross-check PIPELINE-STATE.next_command vs current invocation. Stale routing possible.
- **F9 (MEDIUM)**: Deploy failure has no chain-back protocol. PIPELINE-STATE stays `build-complete` after failed deploy.

**Tech Stack:** Python + bash.

**Working directory:** `main`.

---

## Conventions

- Mirror byte-identical to `.claude/`
- Regression sweep: `python -m pytest tests/ -q --tb=no -k "zfill or phase_pad or domain or deploy or accept or f6 or f7 or f8 or f9"`
- Single `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` per commit

---

## Task 1: F6 — Shared phase_pad util + replace zfill(2) sites

**Files:**
- Create: `scripts/lib/phase_pad.py` (shared util)
- Modify: 14+ scripts that use `zfill(2)` for phase numbering. Locate via:
  `grep -rln "zfill(2)" scripts/ commands/vg/`
- Mirrors
- Test: `tests/test_f6_phase_pad_util.py`

**Step 1: Failing test**

```python
"""tests/test_f6_phase_pad_util.py — F6 shared phase_pad utility."""
from __future__ import annotations
import importlib.util
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
UTIL = REPO / "scripts" / "lib" / "phase_pad.py"


def _load_util():
    spec = importlib.util.spec_from_file_location("phase_pad", UTIL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_util_exists():
    assert UTIL.is_file(), "F6: scripts/lib/phase_pad.py must ship"


def test_util_handles_single_digit():
    mod = _load_util()
    assert mod.phase_pad(7) == "07"
    assert mod.phase_pad("7") == "07"


def test_util_handles_three_digit_no_truncate():
    mod = _load_util()
    # Critical: phase 100+ must NOT be truncated
    assert mod.phase_pad(100) == "100", "F6: phase 100 must NOT be zero-truncated"
    assert mod.phase_pad(123) == "123"


def test_util_handles_sub_phase_notation():
    mod = _load_util()
    # Sub-phase like 07.10.1 must preserve dot-notation
    assert mod.phase_pad("07.10.1") == "07.10.1"
    assert mod.phase_pad("5.2") == "05.2"  # leading zero applied to top-level only


def test_util_env_override_width():
    mod = _load_util()
    import os
    # Config-driven width via VG_PHASE_PAD_WIDTH env
    os.environ["VG_PHASE_PAD_WIDTH"] = "3"
    try:
        assert mod.phase_pad(7) == "007"
    finally:
        os.environ.pop("VG_PHASE_PAD_WIDTH", None)


def test_at_least_one_script_imports_phase_pad():
    """At least one production script must use the new util (not zfill(2) hardcode)."""
    found = False
    for p in (REPO / "scripts").rglob("*.py"):
        if p == UTIL:
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        if "from phase_pad" in body or "phase_pad(" in body or "phase_pad import" in body:
            found = True
            break
    assert found, (
        "F6: at least one script must import + use phase_pad() (not bare zfill(2)). "
        "Migrate the heaviest-traffic scripts first (vg-orchestrator, evidence-manifest)."
    )
```

**Step 2: Run** → RED on multiple.

**Step 3: Implement**

Create `scripts/lib/phase_pad.py`:

```python
"""phase_pad.py — F6 Batch 12

Shared phase-number padding. Replaces hardcoded `zfill(2)` calls that break
at phase 100+ or sub-phase notation like '07.10.1'.

- Default width: 2 (preserves backward compat for phases 1-99)
- Env override: VG_PHASE_PAD_WIDTH (e.g. "3" for projects expecting 100+ phases)
- Sub-phase notation: applies padding to top-level segment only
"""
from __future__ import annotations
import os


def phase_pad(phase: int | str, width: int | None = None) -> str:
    """Pad phase number to width. Handles ints, strings, and sub-phase notation.

    Examples:
      phase_pad(7) -> '07'
      phase_pad(100) -> '100' (NOT truncated)
      phase_pad('07.10.1') -> '07.10.1' (passthrough)
      phase_pad('5.2') -> '05.2' (top-level padded)
      phase_pad(7, width=3) -> '007'
    """
    if width is None:
        try:
            width = int(os.environ.get("VG_PHASE_PAD_WIDTH", "2"))
        except (TypeError, ValueError):
            width = 2

    s = str(phase).strip()
    if "." in s:
        head, _, tail = s.partition(".")
        return f"{_pad_segment(head, width)}.{tail}"
    return _pad_segment(s, width)


def _pad_segment(seg: str, width: int) -> str:
    """Pad a numeric segment to width. Never truncate when seg exceeds width."""
    if not seg.isdigit():
        return seg
    n = int(seg)
    return str(n).zfill(max(width, len(str(n))))


__all__ = ["phase_pad"]
```

Migrate the heaviest-traffic scripts first. Locate via:
```bash
grep -rln "zfill(2)" scripts/ commands/vg/ | head -20
```

Replace `str(phase).zfill(2)` with `phase_pad(phase)`. Add `from phase_pad import phase_pad` (or `sys.path` insert if not packaged). At minimum migrate:
- `scripts/vg-orchestrator/__main__.py` (or wherever phase is formatted)
- `scripts/emit-evidence-manifest.py`
- `scripts/validators/verify-artifact-freshness.py`

Document migration roadmap for remaining sites in CHANGELOG. Treat this as the FIRST step of a deprecation cycle — leave the rest as TODO for future batch.

**Step 4-6:** pass + mirror + commit.

```bash
git add scripts/lib/phase_pad.py \
        .claude/scripts/lib/phase_pad.py \
        scripts/vg-orchestrator/__main__.py \
        .claude/scripts/vg-orchestrator/__main__.py \
        scripts/emit-evidence-manifest.py \
        .claude/scripts/emit-evidence-manifest.py \
        tests/test_f6_phase_pad_util.py
git commit -m "feat(scale): F6 — shared phase_pad util replaces zfill(2) hardcode (Batch 12)

Flow-chain audit Finding 6 (HIGH): phase number padding via str(phase).zfill(2)
across 14+ scripts. Breaks at phase 100+ (silent truncate) and sub-phase
notation '07.10.1'. Blocker for 50+ phase projects.

Fix:
- scripts/lib/phase_pad.py: shared phase_pad(phase, width=None) util.
  Default width=2 (backward compat). VG_PHASE_PAD_WIDTH env override.
  Never truncates when phase >= 10^width. Sub-phase notation preserved.
- Migrated 2-3 heaviest-traffic scripts. Remaining sites are TODO in
  deprecation cycle (documented in CHANGELOG).

Tests: tests/test_f6_phase_pad_util.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: F7 — Domain/team isolation (minimal — schema + propagation)

**Files:**
- Modify: `templates/vg/ROADMAP.template.md` (add domain/team frontmatter to phase blocks)
- Modify: `scripts/vg-orchestrator/__main__.py` (read domain/team from PIPELINE-STATE on run-start, write to events)
- Modify: `commands/vg/_shared/specs/preflight.md` (read domain from ROADMAP, set PIPELINE-STATE.domain)
- Mirror
- Test: `tests/test_f7_domain_team_isolation.py`

**Step 1: Failing test**

```python
"""tests/test_f7_domain_team_isolation.py — F7 domain/team schema + propagation."""
from __future__ import annotations
import json
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_roadmap_template_documents_domain_team():
    tmpl_paths = [
        REPO / "templates" / "vg" / "ROADMAP.template.md",
        REPO / "commands" / "vg" / "_shared" / "templates" / "ROADMAP.template.md",
    ]
    found = False
    for p in tmpl_paths:
        if p.is_file():
            body = p.read_text(encoding="utf-8")
            if "domain" in body.lower() and "team" in body.lower():
                found = True
                break
    assert found, (
        "F7: ROADMAP template must document domain + team fields per phase. "
        "Required for 50+ phase, multi-team projects."
    )


def test_specs_preflight_reads_domain_from_roadmap():
    body = (REPO / "commands/vg/_shared/specs/preflight.md").read_text(encoding="utf-8")
    assert "domain" in body.lower(), (
        "F7: specs/preflight must propagate domain field from ROADMAP.md into "
        "PIPELINE-STATE.json so downstream phases + events can filter by domain"
    )


def test_pipeline_state_schema_documents_domain():
    """LIFECYCLE.md (or PIPELINE-STATE schema doc) must document domain/team."""
    paths_to_check = [
        REPO / "commands" / "vg" / "LIFECYCLE.md",
        REPO / "schemas" / "pipeline-state.schema.json",
    ]
    found_doc = False
    for p in paths_to_check:
        if p.is_file():
            body = p.read_text(encoding="utf-8")
            if "domain" in body.lower():
                found_doc = True
                break
    assert found_doc, (
        "F7: LIFECYCLE.md or pipeline-state schema must document domain/team fields"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

For ROADMAP template, add example block:
```markdown
### Phase 5 — User authentication
- **domain:** identity
- **team:** auth-team
- **goals:** G-12, G-13, G-14
- ...
```

In `commands/vg/_shared/specs/preflight.md`, add:
```bash
# F7 Batch 12: propagate domain/team from ROADMAP.md to PIPELINE-STATE
ROADMAP_PATH="${PHASE_DIR}/../ROADMAP.md"
[ -f "$ROADMAP_PATH" ] || ROADMAP_PATH=".vg/ROADMAP.md"
if [ -f "$ROADMAP_PATH" ]; then
  DOMAIN=$(grep -A 5 "^### Phase ${PHASE_NUMBER}" "$ROADMAP_PATH" | grep -i "domain:" | head -1 | sed 's/.*domain:\s*//' | tr -d '*' | xargs)
  TEAM=$(grep -A 5 "^### Phase ${PHASE_NUMBER}" "$ROADMAP_PATH" | grep -i "team:" | head -1 | sed 's/.*team:\s*//' | tr -d '*' | xargs)
  if [ -n "$DOMAIN" ]; then
    export VG_PHASE_DOMAIN="$DOMAIN"
    export VG_PHASE_TEAM="$TEAM"
    "${PYTHON_BIN:-python3}" -c "
import json
from pathlib import Path
p = Path('${PHASE_DIR}/PIPELINE-STATE.json')
if p.is_file():
    data = json.loads(p.read_text(encoding='utf-8'))
    data['domain'] = '${DOMAIN}'
    data['team'] = '${TEAM}'
    p.write_text(json.dumps(data, indent=2), encoding='utf-8')
"
    echo "✓ F7: domain=${DOMAIN} team=${TEAM} propagated to PIPELINE-STATE"
  fi
fi
```

Update LIFECYCLE.md doc with new "Domain/Team Isolation" section.

```bash
git commit -m "feat(scale): F7 — domain/team isolation schema + propagation (Batch 12)

Flow-chain audit Finding 7 (HIGH): no multi-domain isolation. ROADMAP.md,
CROSS-PHASE-DEPS.md, event stream had no domain/team partition. Parallel
teams couldn't safely run concurrent phases.

Fix (minimal first pass — full parallel scheduler deferred to v5.0+):
- ROADMAP template documents domain + team fields per phase.
- specs/preflight.md reads domain/team from ROADMAP, exports
  VG_PHASE_DOMAIN + VG_PHASE_TEAM env vars, writes them into
  PIPELINE-STATE.json.
- Future events + filters can query by domain (event store schema-ready).
- LIFECYCLE.md documents the new fields + future parallel scheduling roadmap.

Tests: tests/test_f7_domain_team_isolation.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: F8 — accept reads PIPELINE-STATE.next_command + cross-check

**Files:**
- Modify: `commands/vg/_shared/accept/preflight.md` (read next_command from PIPELINE-STATE, verify matches current invocation)
- Mirror
- Test: `tests/test_f8_accept_pipeline_state_crosscheck.py`

**Step 1: Failing test**

```python
"""tests/test_f8_accept_pipeline_state_crosscheck.py — F8 accept cross-check."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO / "commands" / "vg" / "_shared" / "accept" / "preflight.md"


def test_accept_reads_pipeline_state_next_command():
    body = PREFLIGHT.read_text(encoding="utf-8")
    assert "next_command" in body, (
        "F8: accept/preflight must read PIPELINE-STATE.next_command (written by "
        "test/close.md F1 fix) and cross-check it matches /vg:accept invocation"
    )


def test_accept_warns_on_routing_mismatch():
    body = PREFLIGHT.read_text(encoding="utf-8")
    assert "vg:accept" in body and "/vg:" in body, (
        "F8: cross-check logic must compare current command (/vg:accept) "
        "against PIPELINE-STATE.next_command. Mismatch = WARN (test verdict "
        "may not point here)."
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/accept/preflight.md`, add:

```bash
# F8 Batch 12: PIPELINE-STATE.next_command cross-check
PIPELINE_STATE="${PHASE_DIR}/PIPELINE-STATE.json"
if [ -f "$PIPELINE_STATE" ]; then
  EXPECTED_NEXT=$(${PYTHON_BIN:-python3} -c "
import json
from pathlib import Path
data = json.loads(Path('${PIPELINE_STATE}').read_text(encoding='utf-8'))
print(data.get('next_command', ''))
" 2>/dev/null)
  if [ -n "$EXPECTED_NEXT" ]; then
    if echo "$EXPECTED_NEXT" | grep -q "/vg:accept"; then
      echo "✓ F8: PIPELINE-STATE next_command='${EXPECTED_NEXT}' matches /vg:accept invocation"
    else
      echo "⚠ F8 WARN: PIPELINE-STATE.next_command='${EXPECTED_NEXT}' does NOT route to /vg:accept"
      echo "   Test verdict likely BLOCKED/FAILED. Expected next: ${EXPECTED_NEXT}"
      echo "   Continue at your own risk via --force, OR run: ${EXPECTED_NEXT}"
      if echo "${ARGUMENTS:-}" | grep -q -- "--force"; then
        echo "   --force flag set; continuing..."
      else
        "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/vg-orchestrator" emit-event \
          "accept.routing_mismatch_block" \
          --payload "{\"phase\":\"${PHASE_NUMBER}\",\"expected_next\":\"${EXPECTED_NEXT}\"}" \
          >/dev/null 2>&1 || true
        exit 1
      fi
    fi
  fi
fi
```

```bash
git commit -m "feat(accept): F8 — accept cross-checks PIPELINE-STATE next_command (Batch 12)

Flow-chain audit Finding 8 (HIGH): test/close.md emits next_command in
PIPELINE-STATE.json (per F1 Batch 10). PASSED/GAPS_FOUND → /vg:accept;
FAILED → /vg:review --resume. But accept/preflight never validated that
the current invocation matched. Operator could run /vg:accept on a phase
whose test verdict was FAILED → ship broken phase.

Fix: accept/preflight reads PIPELINE-STATE.next_command, compares against
/vg:accept invocation. Mismatch → WARN + BLOCK unless --force. Emits
accept.routing_mismatch_block event on BLOCK.

Closes the test → accept routing-correctness gap.

Tests: tests/test_f8_accept_pipeline_state_crosscheck.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: F9 — Deploy failure chain-back

**Files:**
- Modify: `commands/vg/_shared/deploy/execute.md` (catch failures, update PIPELINE-STATE)
- Modify: `commands/vg/_shared/deploy/persist-and-close.md` (write status=failed, emit deploy.failed event, set next_command)
- Mirror
- Test: `tests/test_f9_deploy_failure_chain_back.py`

**Step 1: Failing test**

```python
"""tests/test_f9_deploy_failure_chain_back.py — F9 deploy failure recovery."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
EXEC_MD = REPO / "commands" / "vg" / "_shared" / "deploy" / "execute.md"
CLOSE_MD = REPO / "commands" / "vg" / "_shared" / "deploy" / "persist-and-close.md"


def test_deploy_failure_updates_pipeline_state():
    body = EXEC_MD.read_text(encoding="utf-8") + CLOSE_MD.read_text(encoding="utf-8")
    assert "deploy_status" in body or "deploy.failed" in body or "deploy_failed" in body, (
        "F9: deploy must set pipeline_step or deploy_status='failed' in "
        "PIPELINE-STATE on failure (not silent stay at build-complete)"
    )


def test_deploy_failure_emits_event():
    body = EXEC_MD.read_text(encoding="utf-8") + CLOSE_MD.read_text(encoding="utf-8")
    assert "deploy.failed" in body or "deploy_failure" in body, (
        "F9: deploy failure must emit deploy.failed event for telemetry "
        "+ accept-time cross-check"
    )


def test_deploy_failure_sets_next_command():
    body = CLOSE_MD.read_text(encoding="utf-8")
    assert "next_command" in body and "/vg:deploy" in body, (
        "F9: deploy failure must set PIPELINE-STATE.next_command='/vg:deploy --resume' "
        "so auto-chain rerun is unambiguous"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/deploy/persist-and-close.md`, add failure-path block:

```bash
# F9 Batch 12: deploy failure chain-back
if [ "${DEPLOY_STATUS:-OK}" != "OK" ] && [ "${DEPLOY_STATUS:-OK}" != "PASS" ]; then
  ${PYTHON_BIN:-python3} -c "
import json
from pathlib import Path
p = Path('${PHASE_DIR}/PIPELINE-STATE.json')
data = json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
data['pipeline_step'] = 'deploy-failed'
data['deploy_status'] = '${DEPLOY_STATUS}'
data['next_command'] = '/vg:deploy ${PHASE_NUMBER} --resume'
p.write_text(json.dumps(data, indent=2), encoding='utf-8')
"
  "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/vg-orchestrator" emit-event \
    "deploy.failed" \
    --payload "{\"phase\":\"${PHASE_NUMBER}\",\"status\":\"${DEPLOY_STATUS}\",\"reason\":\"${DEPLOY_REASON:-unknown}\"}" \
    >/dev/null 2>&1 || true
  echo "⛔ Deploy failed. PIPELINE-STATE.next_command='/vg:deploy ${PHASE_NUMBER} --resume'"
fi
```

```bash
git commit -m "feat(deploy): F9 — deploy failure chain-back protocol (Batch 12)

Flow-chain audit Finding 9 (MEDIUM): deploy failure was silent. PIPELINE-STATE
stayed at 'build-complete'. No event emitted. No --resume routing. Operator
had to manually unstick. In CI/auto-chain runs, the pipeline became opaque.

Fix:
- deploy/persist-and-close.md detects DEPLOY_STATUS != OK/PASS.
- Updates PIPELINE-STATE.pipeline_step='deploy-failed', deploy_status,
  next_command='/vg:deploy {phase} --resume'.
- Emits deploy.failed event with status + reason.
- Echo unambiguous next-action hint for operator.

Tests: tests/test_f9_deploy_failure_chain_back.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Regression sweep + release v4.15.0

Bump VERSION 4.14.0 → 4.15.0. CHANGELOG entry per 4 findings + summary that closes all 12 audit findings = scale verdict can flip from FAIL to **PASS (conditional)**. Tag v4.15.0. Push. Re-sync ~/.vgflow.

End of Batch 12 plan. Estimated 4 hours.

## Note on remaining zfill(2) sites

Batch 12 Task 1 migrates 2-3 heaviest scripts. Remaining ~11 sites are TODO. Document deprecation cycle in CHANGELOG: tooling will tolerate `zfill(2)` callers through v5.0, all migrated by v5.1. Provides safety net while ecosystem catches up.
