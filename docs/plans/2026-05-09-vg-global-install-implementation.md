# VG v3.0.0 Global Install Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship VG harness as global install (`~/.vgflow/`) with path resolver dual-mode, decoupled deploy state, .vg/-rooted layout, hook installer dual-mode, and npm public distribution.

**Architecture:** Static harness (commands/skills/scripts/schemas) ships globally via npm `vgflow` package; project repo retains only DYNAMIC state under `.vg/`. Path resolver walks `cwd → .git` (with `__file__` fallback for legacy installs). Hooks register at `~/.claude/settings.json` (global) pointing at `~/.vgflow/scripts/hooks/...`. Deploy state moves from per-phase to project-level (`.vg/deploy/STATE.json`). Migration script `vg-migrate-v3.sh` handles existing v2.x projects.

**Tech Stack:** Python 3 (orchestrator + validators), Bash (hooks + dispatcher), Node.js (npm CLI entry), JSON Schemas, SQLite (events.db), pytest.

**Source design:** `docs/plans/2026-05-09-vg-global-install-design.md` (10 sections, 657 lines).

**Sequencing:** Per design Section 9.3 (Option A) — meta-memory v2.5x ships FIRST (separate plan `2026-05-08-meta-memory-implementation.md`). v3.0.0 = pure layout + deploy refactor. NO meta-memory features added in v3.0.0 itself.

**Critical risk gates:**
- Stage 1 (resolver) HARD-GATES Stages 2-9 — without dual-mode resolver, nothing works
- Stage 6 (deploy STATE.json) HARD-GATES Stage 7 (consumer migrations)
- Stage 8 (migration script) HARD-GATES Stage 9 (release) — must pass on real existing project

**Rollout flag:** `vg.config.md → install_layout = "v2"|"v3"`. Default `v2` (legacy resolver). Migration flips to `v3`. Each stage tested under both layouts.

---

## Stage 0: Pre-flight + worktree

### Task 0.1: Create worktree for v3 work

**Files:**
- New worktree: `../vgflow-v3/`

**Step 1: Create worktree**

```bash
git worktree add -b v3-dev ../vgflow-v3
cd ../vgflow-v3
```

**Step 2: Verify isolation**

Run: `python -m pytest tests/test_worktree_isolation.py -q`
Expected: 4 PASS (regression test from v2.52.2).

**Step 3: Tag baseline**

```bash
git tag v3-dev-baseline
git push origin v3-dev-baseline
```

---

### Task 0.2: Verify existing infra intact

**Files (read-only):**

```bash
ls .claude/scripts/vg-orchestrator/_repo_root.py
ls .claude/scripts/hooks/install-hooks.sh
ls bin/vg.js bin/vg-cli-dispatcher.sh package.json
```

**Step 1: Sanity check**

Run: `node bin/vg.js version`
Expected: prints current VERSION (2.52.2 or higher).

**Step 2: Run full test suite baseline**

Run: `python -m pytest tests/ -q 2>&1 | tail -3`
Expected: all PASS (record count for regression baseline).

---

## Stage 1: Resolver dual-mode (HARD GATE for Stages 2-9)

### Task 1.1: `find_repo_root()` priority swap (cwd-walk first)

**Files:**
- Modify: `.claude/scripts/vg-orchestrator/_repo_root.py:22-49`
- Modify: `scripts/vg-orchestrator/_repo_root.py:22-49` (canonical mirror)
- Test: `tests/test_resolver_dual_mode.py` (NEW)

**Step 1: Write failing test**

```python
# tests/test_resolver_dual_mode.py
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT_HELPER = Path(__file__).resolve().parent.parent / ".claude" / "scripts" / "vg-orchestrator" / "_repo_root.py"


def _run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=False)


def _make_repo(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.mkdir()
    _run(["git", "init", "-q"], cwd=p)
    _run(["git", "config", "user.email", "test@vg.local"], cwd=p)
    _run(["git", "config", "user.name", "VG Test"], cwd=p)
    (p / "README.md").write_text("# test\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=p)
    _run(["git", "commit", "-q", "-m", "init"], cwd=p)
    return p


def _resolve(cwd: Path, env_extra: dict | None = None) -> Path:
    code = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT_HELPER.parent)!r}); "
        "from _repo_root import find_repo_root; print(find_repo_root())"
    )
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = _run([sys.executable, "-c", code], cwd=cwd, env=env)
    assert r.returncode == 0, r.stderr
    return Path(r.stdout.strip())


def test_cwd_walk_takes_priority_over_file_walk(tmp_path):
    """Resolver walks from cwd first → finds project's .git, NOT the
    .git of the script's anchor location. Critical for global install
    where script lives in ~/.vgflow/ but cwd = user project."""
    proj = _make_repo(tmp_path, "user_project")
    # cwd = proj root; resolver should return proj, not vgflow-repo
    resolved = _resolve(proj)
    assert resolved.resolve() == proj.resolve()


def test_env_var_takes_top_priority(tmp_path):
    proj = _make_repo(tmp_path, "user_project")
    other = _make_repo(tmp_path, "other_project")
    resolved = _resolve(proj, env_extra={"VG_REPO_ROOT": str(other)})
    assert resolved.resolve() == other.resolve()


def test_vg_project_alias(tmp_path):
    """VG_PROJECT alias works same as VG_REPO_ROOT."""
    proj = _make_repo(tmp_path, "user_project")
    other = _make_repo(tmp_path, "other_project")
    resolved = _resolve(proj, env_extra={"VG_PROJECT": str(other)})
    assert resolved.resolve() == other.resolve()


def test_falls_back_to_file_walk_when_cwd_outside_repo(tmp_path):
    """cwd outside any git repo → fall back to __file__-walk (legacy)."""
    not_a_repo = tmp_path / "noplace"
    not_a_repo.mkdir()
    # No .git anywhere reachable from cwd. Resolver should NOT return cwd.
    # It walks __file__ → finds vgflow-repo's .git.
    resolved = _resolve(not_a_repo)
    # vgflow-repo path
    expected = Path(REPO_ROOT_HELPER).resolve().parent.parent.parent.parent
    assert resolved.resolve() == expected.resolve() or resolved.resolve() == not_a_repo.resolve()
    # Either: file-walk found vgflow-repo, OR final cwd-fallback hit
```

**Step 2: Run — FAIL**

```
pytest tests/test_resolver_dual_mode.py -v
```
Expected: 4 FAIL (resolver still uses old priority).

**Step 3: Patch resolver**

In `.claude/scripts/vg-orchestrator/_repo_root.py`, replace `find_repo_root` body:

```python
def find_repo_root(start_file: str | None = None) -> Path:
    # 1. Explicit env (existing behavior, unchanged) — VG_REPO_ROOT or VG_PROJECT alias
    env = os.environ.get("VG_REPO_ROOT") or os.environ.get("VG_PROJECT")
    if env:
        return Path(env).resolve()

    # 2. Walk from cwd (NEW v3 — works for global install)
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate

    # 3. Walk from __file__ anchor (legacy fallback for project-local install)
    anchor = Path(start_file).resolve().parent if start_file \
        else Path(__file__).resolve().parent
    for candidate in [anchor, *anchor.parents]:
        if (candidate / ".git").exists():
            return candidate

    # 4. Fallback: cwd with stderr warning (unchanged)
    print(
        "WARN: vg helper could not locate repo root via env, cwd, or __file__ "
        f"walk (anchor={anchor}, cwd={cwd}). Falling back to cwd — likely "
        "creates rogue .vg/ artifacts.",
        file=sys.stderr,
    )
    return Path.cwd().resolve()
```

Mirror to `scripts/vg-orchestrator/_repo_root.py`.

**Step 4: Run — PASS**

```
pytest tests/test_resolver_dual_mode.py -v
pytest tests/test_worktree_isolation.py -v   # ensure no regression
```
Expected: all PASS.

**Step 5: Commit**

```bash
git add .claude/scripts/vg-orchestrator/_repo_root.py \
        scripts/vg-orchestrator/_repo_root.py \
        tests/test_resolver_dual_mode.py
git commit -m "feat(resolver): cwd-walk takes priority over __file__-walk (v3 prep)

For global install: scripts in ~/.vgflow/ cannot walk __file__ → project's
.git. Cwd-walk now first; __file__-walk fallback for legacy installs.
VG_PROJECT alias added alongside VG_REPO_ROOT.

Stage 1.1 of v3.0.0 plan. Backwards compatible — project-local installs
still work via __file__-walk fallback."
```

---

### Task 1.2: `find_vg_home()` helper (NEW)

**Files:**
- Create: `.claude/scripts/vg-orchestrator/_vg_home.py`
- Test: `tests/test_find_vg_home.py`

**Step 1: Failing test**

```python
# tests/test_find_vg_home.py
import os, subprocess, sys, tempfile
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parent.parent / ".claude" / "scripts" / "vg-orchestrator" / "_vg_home.py"


def _run_resolver(cwd: Path, env_extra: dict | None = None) -> tuple[int, str, str]:
    code = (
        f"import sys; sys.path.insert(0, {str(HELPER.parent)!r}); "
        "from _vg_home import find_vg_home; print(find_vg_home())"
    )
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, "-c", code], cwd=str(cwd), env=env, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr


def test_env_var_top_priority(tmp_path):
    fake = tmp_path / "fake_vgflow"
    fake.mkdir()
    rc, out, err = _run_resolver(tmp_path, {"VG_HOME": str(fake)})
    assert rc == 0
    assert Path(out).resolve() == fake.resolve()


def test_marker_global_loads_from_home(tmp_path, monkeypatch):
    """Marker .vg/.install-target=global → resolve to ~/.vgflow/ if exists."""
    proj = tmp_path / "proj"
    (proj / ".vg").mkdir(parents=True)
    (proj / ".vg" / ".install-target").write_text("global", encoding="utf-8")
    (proj / ".git").mkdir()
    fake_home_vgflow = tmp_path / "fake_home_vgflow"
    fake_home_vgflow.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))   # macos/linux
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # win
    # Create ~/.vgflow inside the fake home
    (tmp_path / ".vgflow").mkdir()
    rc, out, err = _run_resolver(proj, {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})
    assert rc == 0
    assert Path(out).resolve() == (tmp_path / ".vgflow").resolve()


def test_marker_project_loads_from_dot_claude(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".vg").mkdir(parents=True)
    (proj / ".vg" / ".install-target").write_text("project", encoding="utf-8")
    (proj / ".claude").mkdir()
    (proj / ".git").mkdir()
    rc, out, err = _run_resolver(proj)
    assert rc == 0
    assert Path(out).resolve() == (proj / ".claude").resolve()


def test_marker_global_but_home_missing_errors(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".vg").mkdir(parents=True)
    (proj / ".vg" / ".install-target").write_text("global", encoding="utf-8")
    (proj / ".git").mkdir()
    rc, out, err = _run_resolver(proj, {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})
    assert rc != 0
    assert "global" in err.lower() or "vgflow" in err.lower()


def test_legacy_no_marker_falls_back(tmp_path):
    """No marker + .claude/VGFLOW-VERSION present → legacy mode."""
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "VGFLOW-VERSION").write_text("2.52.2", encoding="utf-8")
    (proj / ".git").mkdir()
    rc, out, err = _run_resolver(proj)
    assert rc == 0
    assert Path(out).resolve() == (proj / ".claude").resolve()
```

**Step 2: Run — FAIL** (helper missing).

**Step 3: Implement helper**

```python
# .claude/scripts/vg-orchestrator/_vg_home.py
"""Resolve VG harness location (where static assets live).

Distinct from _repo_root.py (project state location). VG_HOME tells code
where to load skills, commands, scripts FROM. find_repo_root tells code
where the user's project state lives.

Resolution priority:
  1. VG_HOME env var
  2. Project marker .vg/.install-target → "global"|"project"
  3. Legacy detect: .claude/VGFLOW-VERSION present → project mode
  4. Global fallback: ~/.vgflow/ if exists, else error
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from _repo_root import find_repo_root


def find_vg_home(start_file: str | None = None) -> Path:
    # 1. Explicit env
    env = os.environ.get("VG_HOME")
    if env:
        return Path(env).resolve()

    # 2. Marker-driven
    project = find_repo_root(start_file)
    marker = project / ".vg" / ".install-target"
    if marker.exists():
        target = marker.read_text(encoding="utf-8").strip()
        if target == "global":
            home_vgflow = Path.home() / ".vgflow"
            if home_vgflow.exists():
                return home_vgflow
            raise RuntimeError(
                f"Project marked install-target=global but ~/.vgflow/ missing "
                f"({home_vgflow}). Run /vg:install --repair or switch project mode."
            )
        elif target == "project":
            return project / ".claude"

    # 3. Legacy detect
    legacy = project / ".claude" / "VGFLOW-VERSION"
    if legacy.exists():
        return project / ".claude"

    # 4. Global fallback
    home_vgflow = Path.home() / ".vgflow"
    if home_vgflow.exists():
        return home_vgflow

    raise RuntimeError(
        "VG not installed. Run: npm install -g vgflow"
    )
```

Mirror to `scripts/vg-orchestrator/_vg_home.py`.

**Step 4: Run — PASS.**

**Step 5: Commit** (`feat(resolver): find_vg_home() helper for global vs project resolution`).

---

### Task 1.3: Shell helper `vg_resolve_project_root()`

**Files:**
- Modify: `.claude/scripts/hooks/_lib.sh` — add helper
- Modify: `scripts/hooks/_lib.sh` (mirror)
- Test: `tests/hooks/test_resolve_project_root.sh`

**Step 1: Write failing shell test**

```bash
# tests/hooks/test_resolve_project_root.sh
#!/usr/bin/env bash
set -euo pipefail

source .claude/scripts/hooks/_lib.sh

# Test 1: cwd inside git repo
cd /tmp
mkdir -p test-repo-1
cd test-repo-1
git init -q
result=$(vg_resolve_project_root)
[ "$result" = "$(pwd)" ] || { echo "FAIL test 1: expected $(pwd), got $result"; exit 1; }
echo "test 1 PASS"

# Test 2: VG_PROJECT env override
export VG_PROJECT=/tmp/override
result=$(vg_resolve_project_root)
[ "$result" = "/tmp/override" ] || { echo "FAIL test 2"; exit 1; }
unset VG_PROJECT
echo "test 2 PASS"

# Test 3: cwd outside any git repo
cd /tmp
result=$(vg_resolve_project_root || echo "ERR")
[ "$result" = "ERR" ] || [ -n "$result" ] && echo "test 3 PASS"

cleanup() { rm -rf /tmp/test-repo-1; }
trap cleanup EXIT
```

**Step 2: Run — FAIL** (helper missing).

**Step 3: Add helper to `_lib.sh`**

```bash
# Issue v3.0.0 Stage 1.3: shell-side find_repo_root for hooks.
# Walks cwd → .git, falls back to VG_PROJECT env, then errors.
vg_resolve_project_root() {
  if [ -n "${VG_PROJECT:-}" ]; then
    echo "$VG_PROJECT"
    return 0
  fi
  if [ -n "${VG_REPO_ROOT:-}" ]; then
    echo "$VG_REPO_ROOT"
    return 0
  fi
  local cur
  cur="$(pwd)"
  while [ "$cur" != "/" ] && [ "$cur" != "" ]; do
    if [ -e "$cur/.git" ]; then
      echo "$cur"
      return 0
    fi
    cur="$(dirname "$cur")"
  done
  echo "vg_resolve_project_root: no .git found in cwd ancestry" >&2
  return 1
}
```

**Step 4: Run — PASS.**

**Step 5: Commit** (`feat(hooks): vg_resolve_project_root() shell helper for v3`).

---

## Stage 2: Layout migration helpers + .gitignore

### Task 2.1: `resolve_vg_doc()` Python helper (dual-mode docs)

**Files:**
- Create: `.claude/scripts/vg-orchestrator/_doc_resolver.py`
- Test: `tests/test_doc_resolver.py`

**Step 1: Failing test**

```python
def test_resolves_new_layout_first(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / ".vg").mkdir(parents=True)
    (proj / ".vg" / "ROADMAP.md").write_text("new", encoding="utf-8")
    (proj / "ROADMAP.md").write_text("legacy", encoding="utf-8")
    monkeypatch.setenv("VG_PROJECT", str(proj))
    # Run resolver subprocess...
    # Expected: returns .vg/ROADMAP.md
```

**Step 2: Implement**

```python
def resolve_vg_doc(name: str) -> Path:
    """Resolve VG doc file — new .vg/ layout first, legacy root fallback."""
    project = find_repo_root()
    new = project / ".vg" / name
    legacy = project / name
    if new.exists():
        return new
    if legacy.exists():
        return legacy
    return new   # default for future writes
```

Used by all callers needing ROADMAP.md, FOUNDATION.md, vg.config.md.

**Step 3-5:** Run, pass, commit.

---

### Task 2.2: `.gitignore` whitelist generator

**Files:**
- Create: `.claude/scripts/migrate/generate-gitignore-v3.py`
- Test: `tests/test_gitignore_v3.py`

Generates whitelist patterns for `.vg/` tracked files. Used by migration script.

---

### Task 2.3: Update ~50+ scripts to use `resolve_vg_doc()`

**Files (audit grep targets):**
```bash
grep -rn "ROADMAP\.md\|FOUNDATION\.md\|vg\.config\.md" commands/ scripts/ skills/ codex-skills/ | wc -l
```

Expected: ~50+ matches.

**Approach:** batch search-and-replace via grep + sed, validate per-file. Each file: 1 commit.

Sub-tasks 2.3.a through 2.3.n (~10-15 commits depending on grouping).

---

## Stage 3: Hook installer dual-mode

### Task 3.1: Add `--mode` flag to `install-hooks.sh`

**Files:**
- Modify: `scripts/hooks/install-hooks.sh:43-94`
- Mirror: `.claude/scripts/hooks/install-hooks.sh`
- Test: `tests/test_install_hooks_mode.py`

**Step 1: Failing test**

```python
def test_global_mode_emits_home_path(tmp_path):
    target = tmp_path / "settings.json"
    subprocess.run([
        "bash", "scripts/hooks/install-hooks.sh",
        "--target", str(target),
        "--mode", "global",
    ], check=True)
    settings = json.loads(target.read_text())
    cmd = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "$HOME/.vgflow/scripts/hooks/" in cmd
    assert "${CLAUDE_PROJECT_DIR}" not in cmd

def test_project_mode_emits_claude_project_dir(tmp_path):
    target = tmp_path / "settings.json"
    subprocess.run([
        "bash", "scripts/hooks/install-hooks.sh",
        "--target", str(target),
        "--mode", "project",
    ], check=True)
    settings = json.loads(target.read_text())
    cmd = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PROJECT_DIR}/.claude/scripts/hooks/" in cmd
```

**Step 2-4:** Implement `--mode global|project` flag, default `project` (backwards compat). Run + pass.

**Step 5:** Commit.

---

### Task 3.2: Codex hooks dual-mode

Same pattern for `~/.codex/hooks.json` global vs project's `.codex/hooks.json`.

---

## Stage 4: npm package — extend skeleton

### Task 4.1: Add `vg install --global` real implementation

Skeleton (commit `173f598`) had stub. Wire it up to call `install-hooks.sh --mode global`.

### Task 4.2: Add `vg install --project` real implementation

### Task 4.3: Add `vg uninstall` real implementation

### Task 4.4: Add `vg update` (global) — `git pull` in `~/.vgflow/`

### Task 4.5: Test global install end-to-end

```bash
npm pack
npm install -g ./vgflow-2.53.0.tgz
vg install --global   # writes ~/.claude/settings.json
vg doctor             # verify hooks count > 0
```

---

## Stage 5: `/vg:install` skill ASK flow

### Task 5.1: Create `commands/vg/install.md` skill

First-run ASK via AskUserQuestion. Marker `.vg/.install-target` write. Backup logic.

### Task 5.2: Add `--target=global|project|switch` flags

### Task 5.3: Add `--repair` flag for stale markers

---

## Stage 6: Deploy decouple — `.vg/deploy/STATE.json`

### Task 6.1: Schema for new STATE.json

**Files:**
- Create: `schemas/deploy-state.v1.json`
- Test: `tests/test_deploy_state_schema.py`

Validate: schema_version=1, envs[], preferred_env_for_phase{}, active_environments[].

### Task 6.2: STATE.json reader/writer module

**Files:**
- Create: `.claude/scripts/deploy/state.py`
- Test: `tests/test_deploy_state_io.py`

Read, write atomic, merge, backup-before-write semantics.

### Task 6.3: history.jsonl appender

**Files:**
- Create: `.claude/scripts/deploy/history.py`
- Test: `tests/test_deploy_history.py`

Append-only event log. Rotate at 10MB.

### Task 6.4: Per-env flock `.vg/deploy/.deploy.lock`

Prevent 2-session same-env race.

### Task 6.5: Auto-detect phase context

Query `.vg/active-runs/*.json` for current phase. Fallback git branch. Final fallback last `/vg:scope` run.

---

## Stage 7: Deploy migration + consumer updates

### Task 7.1: `merge-deploy-states.py` migration helper

Collect all per-phase DEPLOY-STATE.json, merge to project-level. Latest SHA per env wins.

### Task 7.2: `build-deploy-history.py` from events.db

Reconstruct history.jsonl from past `phase.deploy_*` events.

### Task 7.3: Update `commands/vg/deploy.md` to v3 args

Phase arg → optional `--phase=<N>` override.

### Task 7.4: Telemetry rename — emit both `phase.deploy_*` AND `deploy.*`

Backwards-compat aliases for 1 minor cycle.

### Task 7.5: Consumer updates (~10 sites)

| File | Change |
|---|---|
| `commands/vg/_shared/scope/env-preference.md` | Read `.vg/deploy/STATE.json.preferred_env_for_phase[{N}]` |
| `commands/vg/_shared/build/pre-test-gate.md` | Read project-level STATE.json |
| `commands/vg/_shared/test/deploy.md` | Same |
| `.claude/scripts/enrich-env-question.py` | Read project-level |
| `commands/vg/_shared/roam/config-gate/*.md` | Same |
| `commands/vg/test.md`, `review.md`, `roam.md` | Reference updates |

1 commit per file (or grouped logically).

---

## Stage 8: Migration script `vg-migrate-v3.sh`

### Task 8.1: Pre-flight detection

Check: clean working tree, current state (legacy markers, .vg/ exists), VG version.

### Task 8.2: Backup phase

`cp -r .claude/{commands/vg,skills/vg-*,scripts} .vg/.backup-{date}/`.

### Task 8.3: Move root docs to `.vg/`

`git mv ROADMAP.md .vg/ROADMAP.md` etc. Atomic in single commit.

### Task 8.4: Branch by target (global vs project)

If global: rm legacy, install global hooks. If project: keep mirror, install project hooks.

### Task 8.5: Update `.gitignore` whitelist

Append patterns from Task 2.2 generator.

### Task 8.6: Smoke test post-migrate

`vg doctor` + `vg health` + scan for broken paths.

### Task 8.7: Commit migrated state

Atomic single commit with migration manifest.

---

## Stage 9: E2E + smoke + release

### Task 9.1: Migration smoke test on real legacy project

Use a fixture project (clone of vgflow-repo with v2.x layout) → run migration → verify all tests pass.

### Task 9.2: Cross-platform smoke (Win + macOS + Linux)

```bash
# CI matrix:
- ubuntu-latest
- macos-latest
- windows-latest (Git Bash)
```

### Task 9.3: Bump VERSION → 3.0.0

Update VERSION, VGFLOW-VERSION, .claude/VGFLOW-VERSION, package.json.

### Task 9.4: Update CHANGELOG.md

`## v3.0.0 - Global install + .vg/-rooted layout + deploy decouple` with full breaking-changes documentation.

### Task 9.5: Update README.md

Install section: `npm install -g vgflow` first option.

### Task 9.6: Tag + publish

```bash
git tag v3.0.0
git push origin main
git push origin v3.0.0
npm publish --access=public
gh release create v3.0.0 --title "v3.0.0 — Global install + layout refactor + deploy decouple"
```

### Task 9.7: Verify post-release

```bash
npm view vgflow@3.0.0
npm install -g vgflow@3.0.0
vg install --global   # on a test machine
```

---

## Estimated effort

| Stage | Tasks | Days |
|---|---|---|
| 0 — Pre-flight | 2 | 0.5 |
| 1 — Resolver | 3 | 2 |
| 2 — Layout migration | 3 (+10-15 sub-tasks) | 3 |
| 3 — Hook installer | 2 | 1 |
| 4 — npm package | 5 | 2 |
| 5 — `/vg:install` skill | 3 | 2 |
| 6 — Deploy STATE.json | 5 | 3 |
| 7 — Deploy migration + consumers | 5 (+~10 sub-tasks) | 4 |
| 8 — Migration script | 7 | 3 |
| 9 — E2E + release | 7 | 2 |
| **Total** | ~42 + sub-tasks | **~22 days** (~4 weeks) |

Sequencing reminder: meta-memory (3 months, 23 tasks per separate plan) ships v2.5x BEFORE v3.0.0 starts.

---

## DRY/YAGNI checks

- Reuse `_repo_root.py`, `bootstrap-loader.py`, `bootstrap-shadow-evaluator.py` (no parallel infra)
- Hook context guard pattern reused (no new pattern invented)
- Cross-session destructive guard (v2.52.2) handles install/upgrade race
- Deploy STATE.json schema mirrors existing per-phase fields (no semantic invention)
- npm package skeleton already shipped (Task 4 = wire-up only)
- Recovery via 3 native methods (no custom rollback script)

---

## References

- Design: `docs/plans/2026-05-09-vg-global-install-design.md`
- Meta-memory plan: `docs/plans/2026-05-08-meta-memory-implementation.md` (ships v2.5x first)
- npm publish workflow: `docs/PUBLISH-NPM.md`
- Multi-session guide: `docs/multi-session.md`
- Existing infra:
  - `.claude/scripts/vg-orchestrator/_repo_root.py` — resolver
  - `.claude/scripts/hooks/install-hooks.sh` — hook installer
  - `bin/vg.js` + `bin/vg-cli-dispatcher.sh` — npm CLI (skeleton DONE)
- v2.52.2 cross-session destructive guard — protects install/upgrade race
