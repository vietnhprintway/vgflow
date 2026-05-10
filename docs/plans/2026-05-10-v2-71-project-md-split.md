# v2.71.0 — project.md Full Split

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Extract `commands/vg/project.md` (1590 lines) into `_shared/project/` subdir mirroring v2.70.0 review.md split + build.md pattern. project.md slims to ~400 lines (frontmatter + STEP routing).

**Architecture:** 13 `<step name>` blocks + 9 rounds in first-time mode. Group into 5 sub-files by phase + mode. project.md becomes routing entry; each STEP block replaced with: "Read `_shared/project/X.md` and follow it exactly." (mirror v2.70.0 review.md slim pattern).

**Tech Stack:** Markdown text manipulation. Mirror byte-identity for both `commands/` ↔ `.claude/commands/` pairs.

---

## Context

`commands/vg/project.md` is the 4th-biggest VG command file at 1590 lines. v2.70.0 review.md split (8159→539, 93%) demonstrated extraction pattern. project.md is similar architecture: many sequential steps + nested round-based discussion. Split improves AI context budget for project-related operations.

**Section map** (13 steps + 9 rounds):

| # | Sub-file | Lines (approx) | Steps |
|---|---|---|---|
| 1 | `_shared/project/preflight.md` | 47-515 (~470) | 0_parse_args, 0b_print_state_summary, 0c_scan_existing_docs |
| 2 | `_shared/project/routing.md` | 515-698 (~180) | 1_route_mode, 2a_resume_check, 2b_mode_menu, 3_mode_view |
| 3 | `_shared/project/first-time-rounds.md` | 698-1243 (~545) **BIGGEST** | 4_mode_first_time + Rounds 1-9 (description, parse, dialog, confirmation gate, constraints, auto-derive, architecture lock, security strategy, write+commit) |
| 4 | `_shared/project/update-modes.md` | 1243-1344 (~100) | 5_mode_update, 6_mode_milestone, 7_mode_rewrite |
| 5 | `_shared/project/migrate-and-init.md` | 1344-end (~250) | 8_mode_migrate, 9_mode_init_only, 10_complete |

Total extracted: ~1545 lines into 5 files. Slim project.md retains: frontmatter + HARD-GATE + STEP routing (≈400-500 lines).

**Reference pattern:** v2.70.0 review.md split (commit `a3ab258`).

VERSION baseline: 2.70.0. Bump to 2.71.0.

---

## Per-Task Strategy

Same as v2.70.0 split:
1. Create `_shared/project/<name>.md` with extracted verbatim content
2. Replace section in project.md with slim STEP routing entry
3. Mirror canonical → `.claude/commands/`
4. Test (subfile exists + extracted steps + routes_to_subfile + mirror byte-identity)
5. Commit per section

**Test impact:** Tests grep'ing project.md body content updated to use `project_text_full()` helper that concatenates project.md + `_shared/project/*.md` (precedent: v2.70.0 review.md `review_text_full()`).

---

## Task 1: Bootstrap + extract preflight

**Files:**
- Create: `commands/vg/_shared/project/preflight.md` + mirror
- Modify: `commands/vg/project.md` + mirror (slim routing for 0_parse_args + 0b + 0c)
- Test: `tests/test_v2_71_project_split_preflight.py` (NEW, 6 tests pattern)

**Slim routing entry:**

```markdown
### Preflight section (extracted v2.71.0 T1)

Read `_shared/project/preflight.md` and follow it exactly.
Includes 3 steps: 0_parse_args, 0b_print_state_summary, 0c_scan_existing_docs.
```

**Commit msg:** `refactor(project): T1 extract preflight section to _shared/project/preflight.md (v2.71.0)`

---

## Task 2: Extract routing

**Files:** Create `commands/vg/_shared/project/routing.md` + mirror. Modify project.md + mirror.

Steps: 1_route_mode, 2a_resume_check, 2b_mode_menu, 3_mode_view.

**Commit msg:** `refactor(project): T2 extract routing to _shared/project/routing.md (v2.71.0)`

---

## Task 3: Extract first-time-rounds (LARGEST)

**Files:** Create `commands/vg/_shared/project/first-time-rounds.md` + mirror. Modify project.md + mirror.

Steps: 4_mode_first_time + Rounds 1-9 (capture, parse, dialog, confirmation, constraints, auto-derive, architecture lock, security strategy, atomic write).

This is the largest sub-file (~545 lines). Per-round content must remain verbatim — these are nested operational instructions for `/vg:project` first-time mode.

**Commit msg:** `refactor(project): T3 extract first-time-rounds to _shared/project/first-time-rounds.md (v2.71.0)`

---

## Task 4: Extract update-modes

**Files:** Create `commands/vg/_shared/project/update-modes.md` + mirror. Modify project.md + mirror.

Steps: 5_mode_update, 6_mode_milestone, 7_mode_rewrite.

**Commit msg:** `refactor(project): T4 extract update-modes to _shared/project/update-modes.md (v2.71.0)`

---

## Task 5: Extract migrate-and-init (final)

**Files:** Create `commands/vg/_shared/project/migrate-and-init.md` + mirror. Modify project.md + mirror.

Steps: 8_mode_migrate, 9_mode_init_only, 10_complete.

**Commit msg:** `refactor(project): T5 extract migrate-and-init to _shared/project/migrate-and-init.md (v2.71.0)`

---

## Task 6: Ceiling test + verify slim

**Files:** `tests/test_v2_71_project_slim_ceiling.py` (NEW, 3 tests).

Verify project.md ≤ 600 lines after split. Verify ≥5 sub-files in `_shared/project/`. Verify project.md routes to each sub-file.

**Commit msg:** `refactor(project): T6 ceiling test + verify slim project.md ≤ 600 lines (v2.71.0)`

---

## Task 7: VERSION + CHANGELOG + tag + push

VERSION 2.70.0 → 2.71.0. CHANGELOG entry. Tag `v2.71.0`. Push. GitHub release.

---

## Constraints (all tasks)

- VERBATIM extraction. NO behavior changes. Markers/telemetry/bash/XML preserved exactly.
- Mirror byte-identity for `commands/` ↔ `.claude/commands/` pairs.
- New commit per task. No --amend, no --no-verify.
- Use helper-pattern (concat project.md + `_shared/project/*.md`) for any breaking tests.

## Execution mode

Subagent-driven development. Suggested batches:
- **Batch A:** T1 + T2 (preflight + routing — 2 commits)
- **Batch B:** T3 (first-time-rounds — 1 big commit, alone)
- **Batch C:** T4 + T5 (update-modes + migrate-and-init — 2 commits)
- **Batch D:** T6 (ceiling) — 1 commit
- **Release:** T7

Each task = own commit.
