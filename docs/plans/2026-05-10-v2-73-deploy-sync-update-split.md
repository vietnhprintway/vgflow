# v2.73.0 — Deploy sync + update.md split

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:**
1. Complete deploy split (deploy.md 574 → ~150) + slim codex vg-deploy (669 → ~300) — closes last codex-sync drift
2. Split update.md (676 → ~150) into NEW `_shared/update/` + slim codex vg-update (818 → ~300)

**Tech:** Markdown text. Mirror byte-identity for `commands/` ↔ `.claude/commands/`. `codex-skills/` canonical-only. CRLF preserved via Python.

---

## Context

After v2.72.0 codex sync, deploy + update remain bloated:

| File | Claude | Codex |
|---|---|---|
| deploy | 574 (5 inline steps + 2 sub-files exist) | 669 ⚠ |
| update | 676 (14 inline steps, no _shared dir) | 818 ⚠ |

VERSION baseline: 2.72.0. Bump to 2.73.0.

---

## Task 1 (T1): Extract deploy preflight (steps 0+0a)

**Source:** deploy.md lines 99-338 covering 2 steps:
- `0_parse_and_validate`
- `0a_env_select_and_confirm`

**Files:**
- Create: `commands/vg/_shared/deploy/preflight.md` + mirror
- Modify: `commands/vg/deploy.md` + mirror (slim routing)
- Test: `tests/test_v2_73_deploy_split_preflight.py` (NEW, 6 tests)

**Slim routing:**

```markdown
### Preflight section (extracted v2.73.0 T1)

Read `_shared/deploy/preflight.md` and follow it exactly.
Includes 2 steps: 0_parse_and_validate, 0a_env_select_and_confirm.
```

**Commit msg:** `refactor(deploy): T1 extract preflight to _shared/deploy/preflight.md (v2.73.0)`

---

## Task 2 (T2): Extract deploy execute (step 1)

**Source:** deploy.md (post-T1) covering 1 step:
- `1_deploy_per_env`

**Files:** Create `_shared/deploy/execute.md` + mirror. Modify deploy.md + mirror. Test.

**Slim routing:**

```markdown
### Execute per-env (extracted v2.73.0 T2)

Read `_shared/deploy/execute.md` and follow it exactly.
Includes 1 step: 1_deploy_per_env.
```

**Commit msg:** `refactor(deploy): T2 extract execute to _shared/deploy/execute.md (v2.73.0)`

---

## Task 3 (T3): Extract deploy persist-and-close (steps 2 + complete)

**Source:** deploy.md (post-T2) covering 2 steps:
- `2_persist_summary`
- `complete`

**Files:** Create `_shared/deploy/persist-and-close.md` + mirror. Modify deploy.md + mirror. Test.

**Slim routing:**

```markdown
### Persist + close (extracted v2.73.0 T3 — final)

Read `_shared/deploy/persist-and-close.md` and follow it exactly.
Includes 2 steps: 2_persist_summary, complete.
```

**Commit msg:** `refactor(deploy): T3 extract persist-and-close to _shared/deploy/persist-and-close.md (v2.73.0)`

---

## Task 4 (T4): Deploy ceiling test

**File:** `tests/test_v2_73_deploy_slim_ceiling.py` (NEW, 3 tests)

```python
def test_deploy_md_under_slim_ceiling():
    # 574 → target ≤ 200
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    assert len(body.splitlines()) <= 200


def test_shared_deploy_dir_has_5_files():
    # 2 existing (overview, per-env-executor-contract) + 3 NEW (preflight, execute, persist-and-close)
    md_files = sorted(Path("commands/vg/_shared/deploy").glob("*.md"))
    assert len(md_files) >= 5


def test_deploy_md_routes_to_each_subfile():
    body = Path("commands/vg/deploy.md").read_text(encoding="utf-8")
    expected = ["preflight.md", "execute.md", "persist-and-close.md"]
    missing = [s for s in expected if f"_shared/deploy/{s}" not in body]
    assert not missing
```

**Commit msg:** `refactor(deploy): T4 ceiling test + verify slim deploy.md ≤ 200 lines (v2.73.0)`

---

## Task 5 (T5): Slim codex-skills/vg-deploy/SKILL.md

**Source:** 669 lines monolithic. **Target:** ~300 lines slim routing.

**Pattern:** Mirror v2.72.0 codex slims (T6/T7/T8). Read codex-skills/vg-deploy/SKILL.md, identify frontmatter + codex_skill_adapter + HARD-GATE-CODEX (preserve), find `<step name="X">` blocks, replace with slim routing entries pointing to existing `_shared/deploy/*` (overview, per-env-executor-contract, preflight, execute, persist-and-close).

**Files:**
- Modify: `codex-skills/vg-deploy/SKILL.md` (669→~300)
- Test: `tests/test_v2_73_codex_deploy_slim.py` (NEW, 4 tests pattern from v2.72.0)

**Commit msg:** `refactor(codex-skills): slim vg-deploy SKILL.md 669→~300 routing _shared/deploy/* (v2.73.0)`

---

## Tasks 6-10 (T6-T10): Update.md split (5 sub-files)

update.md has 14 steps. Group into 5 sub-files:

| T# | Sub-file | Steps |
|---|---|---|
| T6 | `_shared/update/preflight.md` | 0_preflight, 1_check_only_mode |
| T7 | `_shared/update/version-and-changelog.md` | 2_version_compare, 3_changelog_preview, 4_breaking_gate |
| T8 | `_shared/update/fetch-and-merge.md` | 5_fetch_tarball, 6_three_way_merge_per_file, 6b_verify_gate_integrity |
| T9 | `_shared/update/rotate-and-repair.md` | 7_rotate_ancestor_and_version, 7b_repair_hooks |
| T10 | `_shared/update/sync-and-report.md` | 8_sync_codex, 8b_repair_playwright_mcp, 8c_ensure_graphify, 9_report |

Each task: extract sub-file + mirror + slim routing entry in update.md + 6 tests.

**Per-task commit msg pattern:** `refactor(update): T{N} extract <name> to _shared/update/<file>.md (v2.73.0)`

---

## Task 11 (T11): Update ceiling test

**File:** `tests/test_v2_73_update_slim_ceiling.py` (NEW, 3 tests)

Verify update.md ≤ 250 lines + 5 sub-files exist + routing complete.

**Commit msg:** `refactor(update): T11 ceiling test + verify slim update.md ≤ 250 lines (v2.73.0)`

---

## Task 12 (T12): Slim codex-skills/vg-update/SKILL.md

**Source:** 818 lines. **Target:** ~300 lines slim routing.

**Pattern:** Same as T5. Routes to NEW v2.73.0 `_shared/update/*` (5 sub-files from T6-T10).

**Commit msg:** `refactor(codex-skills): slim vg-update SKILL.md 818→~300 routing _shared/update/* (v2.73.0)`

---

## Task 13 (T13): VERSION + CHANGELOG + tag + push

VERSION 2.72.0→2.73.0. CHANGELOG. Tag. Push. GitHub release.

---

## Constraints

- VERBATIM extraction (CRLF preserved via Python)
- Mirror byte-identity for `commands/` ↔ `.claude/commands/`
- `codex-skills/` canonical-only
- New commit per task
- No --no-verify, no --amend
- PRESERVE codex frontmatter + codex_skill_adapter + HARD-GATE-CODEX

## Execution mode

Subagent-driven. Suggested batches:
- **Batch A:** T1+T2+T3+T4 (deploy split — 4 commits)
- **Batch B:** T5 (codex deploy slim — 1 commit)
- **Batch C:** T6+T7+T8 (update first half — 3 commits)
- **Batch D:** T9+T10+T11 (update second half + ceiling — 3 commits)
- **Batch E:** T12 (codex update slim — 1 commit)
- **Release:** T13
