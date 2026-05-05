# Task 07: Refactor `vg-build-crossai-loop.py` to use library

**Goal:** Convert existing `scripts/vg-build-crossai-loop.py` (656 lines) into a thin wrapper that imports `crossai_loop.run_loop()`. Preserve CLI signature (`--phase X --iteration N --max-iterations M`) and existing behavior. Define `pack_review_brief()` for build-stage artifacts as the wrapper's main responsibility.

**Files:**
- Modify: `scripts/vg-build-crossai-loop.py`
- Mirror: `.claude/scripts/vg-build-crossai-loop.py`
- Test: existing `scripts/tests/test_codex_blueprint_plan_contract.py`, `scripts/tests/test_build_references_exist.py`, etc. — full regression must pass.

---

- [ ] **Step 1: Capture current behavior baseline**

Run existing tests + record outputs:

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
python3 -m pytest scripts/tests/test_codex_blueprint_plan_contract.py \
                  scripts/tests/test_build_references_exist.py \
                  scripts/tests/test_codex_runtime_adapter.py \
                  -v 2>&1 | tail -10
```

Record passed count. Goal: number unchanged after refactor.

- [ ] **Step 2: Read existing wrapper**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
wc -l scripts/vg-build-crossai-loop.py
```

Expected: 656 lines. Inspect `pack_review_brief()` (around line 123-247), `invoke_codex()` (250-285), `invoke_gemini()` (287-315), and `main()` (around 470+).

- [ ] **Step 3: Refactor — replace existing main with library call**

Rewrite `scripts/vg-build-crossai-loop.py` to this thin form:

```python
#!/usr/bin/env python3
"""Build CrossAI loop wrapper — invokes shared library with build-stage
brief packer.

CLI: vg-build-crossai-loop.py --phase X --iteration N [--max-iterations M]

Refactored M1 Task 07: previously contained orchestration logic (650+
lines); now delegates to scripts/lib/crossai_loop.run_loop(). Brief
packer for build-stage artifacts (4 source-of-truth: API-CONTRACTS,
TEST-GOALS, CONTEXT, PLAN) lives here. M3 will extend brief to include
new artifacts (UI-MAP, WORKFLOW-SPECS, CRUD-SURFACES, BLOCK 5 FE).

Exit codes preserved: 0 CLEAN, 1 BLOCKS_FOUND, 2 INFRA_FAIL.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from crossai_config import resolve_stage_config  # noqa: E402
from crossai_loop import run_loop  # noqa: E402

# Re-export for tests + callers that import these directly.
from crossai_loop import EXIT_CLEAN, EXIT_BLOCKS_FOUND, EXIT_INFRA_FAIL  # noqa: E402,F401


def pack_review_brief(
    phase_dir: Path,
    phase_num: str,
    iteration: int,
    max_iter: int,
) -> str:
    """Pack the 4 source-of-truth artifacts for build-stage CrossAI review.

    M1: same artifacts as pre-refactor (API-CONTRACTS / TEST-GOALS /
    CONTEXT / PLAN, capped per-section). M3 Task TBD will extend to
    include UI-MAP / VIEW-COMPONENTS / WORKFLOW-SPECS / CRUD-SURFACES /
    BLOCK 5 FE-contracts.
    """
    def read(rel: str, cap: int) -> str:
        p = phase_dir / rel
        if not p.is_file():
            return f"({rel} missing)"
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:cap] + ("\n... [truncated]" if len(text) > cap else "")

    contracts = read("API-CONTRACTS.md", 8000)
    goals = read("TEST-GOALS.md", 8000)
    context = read("CONTEXT.md", 6000)
    plan = read("PLAN.md", 4000)

    return f"""# OHOK-7 Build Verification — Phase {phase_num} iteration {iteration}/{max_iter}

## Your task

Determine whether the build is COMPLETE against the four source-of-truth
artifacts below. This is NOT a generic code review. Check specifically:

1. **Every endpoint/schema in API-CONTRACTS.md** has a matching handler +
   types + validation in the code diff. Missing endpoint → BLOCK finding.
2. **Every goal with priority=critical in TEST-GOALS.md** has real test
   coverage (NOT just unit; runtime/E2E for UI goals). Uncovered → BLOCK.
3. **Every decision D-XX in CONTEXT.md** is honored by code patterns.
4. **Every task in PLAN.md** has a matching commit (feat/fix/refactor/test/
   docs/style/perf/chore/revert/build/ci prefixes accepted).

## Output format

Respond ONLY with:

<crossai-verdict>
  <verdict>PASS|FAIL</verdict>
  <findings>
    <finding severity="BLOCK"><message>...</message></finding>
    <!-- one finding per BLOCK -->
  </findings>
</crossai-verdict>

## Artifacts (source of truth)

### API-CONTRACTS.md
{contracts}

### TEST-GOALS.md
{goals}

### CONTEXT.md (decisions)
{context}

### PLAN.md (tasks)
{plan}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--max-iterations", type=int, default=5)
    args = ap.parse_args()

    repo_root = Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()

    # Resolve build stage config — fall back to single-CLI mode if
    # crossai_stages block missing (legacy project before M2 migrate).
    try:
        stage_cfg = resolve_stage_config("build", repo_root)
    except ValueError as exc:
        # Legacy fallback: try parsing crossai_clis directly and use first
        # entry as primary. Emit warning.
        from crossai_config import _parse_crossai_clis_full, _find_config
        cfg_file = _find_config(repo_root)
        if cfg_file is None:
            print(
                f"\033[38;5;208mvg.config.md missing; cannot run "
                f"CrossAI loop: {exc}\033[0m",
                file=sys.stderr,
            )
            return EXIT_INFRA_FAIL
        text = cfg_file.read_text(encoding="utf-8")
        clis = _parse_crossai_clis_full(text)
        if not clis:
            print(
                "\033[33mlegacy vg.config.md has no crossai_clis; "
                "cannot run CrossAI loop\033[0m",
                file=sys.stderr,
            )
            return EXIT_INFRA_FAIL
        from crossai_config import StageConfig
        stage_cfg = StageConfig(
            stage="build", primary_clis=clis, verifier_cli=None,
        )
        print(
            "\033[33mLegacy mode: crossai_stages missing, using first "
            "crossai_clis entry. Run `vg-orchestrator migrate-crossai` "
            "to upgrade config.\033[0m",
            file=sys.stderr,
        )

    return run_loop(
        phase=args.phase,
        iteration=args.iteration,
        brief_packer=pack_review_brief,
        stage_config=stage_cfg,
    )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run regression suite**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
python3 -m pytest scripts/tests/ -v -x 2>&1 | tail -20
```

Expected: count from Step 1 unchanged. If any test fails, the refactor changed behavior — investigate before committing.

- [ ] **Step 5: Sync mirror + commit**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
cp scripts/vg-build-crossai-loop.py .claude/scripts/vg-build-crossai-loop.py
git add scripts/vg-build-crossai-loop.py \
        .claude/scripts/vg-build-crossai-loop.py
git commit -m "refactor(build-crossai): thin wrapper using crossai_loop library

M1 Task 07 — replace 650+ lines of orchestration in
vg-build-crossai-loop.py with delegation to crossai_loop.run_loop().
Wrapper now contains only: argparse, pack_review_brief() for build-stage
4 source-of-truth artifacts, legacy fallback when crossai_stages block
missing.

CLI signature preserved: --phase --iteration --max-iterations.
Exit codes preserved: 0/1/2 (CLEAN/BLOCKS/INFRA).
Existing test suite passes unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
