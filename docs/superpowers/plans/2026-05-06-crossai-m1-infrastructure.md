# CrossAI M1 Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship infrastructure (config schema, registry, library, init wizard, lazy migrate) for CrossAI multi-stage multi-primary design — WITHOUT changing existing build CrossAI behavior.

**Architecture:** Rename `crossai_skip_validation.py` → `crossai_config.py` and extend with `StageConfig` + `resolve_stage_config()`. Introduce shared `crossai_loop.py` library so existing build wrapper + new scope/blueprint wrappers all share one orchestration codepath. Extend orchestrator with init wizard + lazy migration commands. Extend `vg.config.md` template with new commented sections. M1 ships single-primary passthrough (preserves existing behavior); M2/M3 add gating + multi-primary later.

**Tech Stack:** Python 3.12+, pytest, custom YAML-ish parser (extending existing `_parse_crossai_clis`), subprocess for CLI invocation, sqlite3 events.db, bash slim entries (touched in M2/M3 only).

**Spec:** `docs/superpowers/specs/2026-05-06-crossai-multi-stage-multi-primary-design.md`

---

## File Structure

**New files (sources):**
- `scripts/lib/crossai_config.py` — rename target, extends from existing `crossai_skip_validation.py`. Adds `StageConfig` dataclass + `CLISpec` + `resolve_stage_config(stage, repo_root)` + heuristic threshold parsing.
- `scripts/lib/crossai_loop.py` — orchestration library. `run_loop(phase, iteration, brief_packer, stage_config) -> int`. M1 implements single-primary passthrough (calls one CLI, mirrors existing logic). M3 will extend to parallel multi-primary.
- `scripts/vg-scope-crossai-loop.py` — thin wrapper for scope stage. Defines `pack_review_brief()` for scope artifacts (SPECS + CONTEXT). Imports library.
- `scripts/vg-blueprint-crossai-loop.py` — thin wrapper for blueprint stage. Defines `pack_review_brief()` for blueprint artifacts (PLAN + CONTRACTS + TEST-GOALS + CONTEXT + UI-MAP + WORKFLOW-SPECS + CRUD-SURFACES + VIEW-COMPONENTS + BLOCK 5). Imports library.

**Modified files (sources):**
- `scripts/lib/crossai_skip_validation.py` — DELETE. Replaced by `crossai_config.py` rename. Add thin re-export shim if any external code imports old name.
- `scripts/vg-build-crossai-loop.py` — refactor: keep public CLI signature, delegate orchestration to `crossai_loop.run_loop()`. Define `pack_review_brief()` (existing logic moved into wrapper).
- `scripts/vg-orchestrator/__main__.py` — add `cmd_init_crossai_config(args)` (lines TBD by Task 10) + `cmd_migrate_crossai_config(args)` (Task 11). Wire to argparse subcommands `init-crossai` + `migrate-crossai`.
- `tests/fixtures/phase0-diagnostic-smoke/vg.config.md` — extend with new sections: `crossai.policy`, `crossai.heuristic_thresholds`, `crossai_clis[].role`, `crossai_stages.{scope,blueprint,build}`. Commented defaults to make migration testable.

**Mirror sync (after every source change):**
- `.claude/scripts/lib/crossai_config.py`
- `.claude/scripts/lib/crossai_loop.py`
- `.claude/scripts/vg-scope-crossai-loop.py`
- `.claude/scripts/vg-blueprint-crossai-loop.py`
- `.claude/scripts/vg-build-crossai-loop.py`
- `.claude/scripts/vg-orchestrator/__main__.py`
- (no mirror for `tests/fixtures/...` — fixtures are source-only)

**New tests:**
- `scripts/tests/test_crossai_config_resolve.py` (Tasks 2–4 cover this)
- `scripts/tests/test_crossai_loop_library.py` (Tasks 5–6)
- `scripts/tests/test_crossai_init_wizard.py` (Task 10)
- `scripts/tests/test_crossai_lazy_migrate.py` (Task 11)
- `scripts/tests/test_crossai_skip_validation_compat.py` (Task 1)

---

## Task Index

Per-task split files in `2026-05-06-crossai-m1-infrastructure/`:

- [Task 01: Rename `crossai_skip_validation.py` → `crossai_config.py` + import shim](2026-05-06-crossai-m1-infrastructure/task-01-rename-crossai-skip-validation.md)
- [Task 02: Add `CLISpec` + `StageConfig` dataclasses](2026-05-06-crossai-m1-infrastructure/task-02-stageconfig-dataclasses.md)
- [Task 03: Implement `resolve_stage_config(stage, repo_root)`](2026-05-06-crossai-m1-infrastructure/task-03-resolve-stage-config.md)
- [Task 04: Add heuristic thresholds parser](2026-05-06-crossai-m1-infrastructure/task-04-heuristic-thresholds.md)
- [Task 05: Skeleton `scripts/lib/crossai_loop.py` + `run_loop()` signature](2026-05-06-crossai-m1-infrastructure/task-05-crossai-loop-skeleton.md)
- [Task 06: Implement `run_loop()` single-primary passthrough](2026-05-06-crossai-m1-infrastructure/task-06-run-loop-single-primary.md)
- [Task 07: Refactor `vg-build-crossai-loop.py` to use library](2026-05-06-crossai-m1-infrastructure/task-07-refactor-build-wrapper.md)
- [Task 08: New `vg-scope-crossai-loop.py` wrapper](2026-05-06-crossai-m1-infrastructure/task-08-scope-wrapper.md)
- [Task 09: New `vg-blueprint-crossai-loop.py` wrapper](2026-05-06-crossai-m1-infrastructure/task-09-blueprint-wrapper.md)
- [Task 10: Orchestrator `cmd_init_crossai_config()`](2026-05-06-crossai-m1-infrastructure/task-10-init-crossai-config.md)
- [Task 11: Orchestrator `cmd_migrate_crossai_config()`](2026-05-06-crossai-m1-infrastructure/task-11-migrate-crossai-config.md)
- [Task 12: Extend `tests/fixtures/.../vg.config.md` template](2026-05-06-crossai-m1-infrastructure/task-12-extend-vg-config-template.md)
- [Task 13: Final mirror parity sweep + regression run](2026-05-06-crossai-m1-infrastructure/task-13-final-mirror-parity.md)

---

## Acceptance criteria for M1

- All existing `scripts/tests/test_crossai_skip_validation.py` tests still pass (compat shim works)
- All existing `scripts/tests/test_*` tests pass (full regression suite)
- New tests (Tasks 1–11) all pass; ~15 new tests total
- `python3 .claude/scripts/vg-orchestrator init-crossai --dry-run` on a fresh project prints valid `vg.config.md` content with all new sections
- `python3 .claude/scripts/vg-orchestrator migrate-crossai --dry-run` on PV3-style project shows additive diff only (no removals)
- `python3 .claude/scripts/vg-build-crossai-loop.py --phase 4.2 --iteration 1` on a sample fixture invokes via library and produces same output as before refactor
- `.claude/scripts/...` mirrors byte-identical to `scripts/...` after every commit (final sweep Task 13)

---

## Self-Review

**Spec coverage check:**
- Q15 (library + thin wrappers) → Tasks 5, 6, 7, 8, 9 ✅
- Q16 (rename + extend `crossai_config.py`) → Tasks 1, 2, 3, 4 ✅
- Q21 (`/vg:project --init` auto-detect) → Task 10 ✅
- Q22 (lazy migrate at first invocation) → Task 11 ✅
- vg.config.md template extension → Task 12 ✅
- Mirror parity discipline → enforced per task + final sweep Task 13 ✅
- Existing build CrossAI tests preserved → Task 7 explicit assertion ✅

**Placeholder scan:** No "TBD"/"TODO"/"implement later" in tasks. All file paths exact. All test code concrete (no "write tests for above").

**Type consistency:** `StageConfig`/`CLISpec` dataclass field names defined in Task 2 are reused verbatim in Tasks 3, 5, 6, 10. `pack_review_brief(phase_dir, phase_num, iteration, max_iter) -> str` signature consistent across Tasks 7, 8, 9. `run_loop(phase, iteration, brief_packer, stage_config) -> int` exit-code semantics (0=CLEAN, 1=BLOCKS, 2=INFRA_FAIL) match existing `vg-build-crossai-loop.py` to preserve compat.

**Scope check:** 13 tasks, each producing a green-tested commit. No task touches >3 files (most touch 2: source + test). Mirror sync is part of every commit.

---

**Next:** see `task-01-rename-crossai-skip-validation.md` to start.
