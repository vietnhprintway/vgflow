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


### Resolve + close (extracted v2.74.0 T3 — final)

Read `_shared/scope-review/resolve-and-close.md` and follow it exactly.
Includes 3 steps: 4_resolution, 4.5_baseline_write_and_telemetry, 5_commit_and_next.

Step coverage: 4_resolution, 4.5_baseline_write_and_telemetry, 5_commit_and_next.


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
