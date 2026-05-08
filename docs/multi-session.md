# Multi-Session VGFlow

Running multiple Claude Code sessions against the same project simultaneously is supported, with caveats. This doc maps what works, what blocks, and recommended setups.

## TL;DR

| Setup | Works? | Notes |
|---|---|---|
| 2 sessions, same repo, **different phases** | ✅ | Cross-phase mainline guard allows this since v2.51.13. |
| 2 sessions, same repo, **same phase, same command** | ❌ | Repo lock + cross-phase mainline guard refuse. |
| 2 sessions, **same repo same checkout**, one runs destructive git op | ⚠️ | v2.52.2 cross-session destructive guard blocks. Bypass via `VG_ALLOW_DESTRUCTIVE=1` if needed. |
| 2 sessions on **separate git worktrees** of the same repo | ✅ | Each worktree has its own `.vg/` tree. No collision. **Recommended for parallel phase work.** |
| 2 sessions on **separate clones** | ✅ | Fully isolated. No shared state. |

## How worktree isolation works

Each git worktree has its own working tree. The VG harness resolves `REPO_ROOT` by walking up from script location looking for `.git`. In a worktree, `.git` is a FILE (gitlink) pointing to `main_repo/.git/worktrees/<name>/`; the walker stops at the worktree root because `Path(".git").exists()` returns true for files.

Result:
- Worktree A: `REPO_ROOT = /path/to/wt-A/`, `.vg/events.db` lives at `/path/to/wt-A/.vg/events.db`
- Worktree B: `REPO_ROOT = /path/to/wt-B/`, separate `.vg/events.db`

No cross-talk on `events.db`, `active-runs/`, `.session-context.json`, or any other VG state.

Reference: `.claude/scripts/vg-orchestrator/_repo_root.py:37-39`. Regression test: `tests/test_worktree_isolation.py`.

## Recommended setup for parallel phase work

```bash
# From your main repo:
git worktree add ../proj-blueprint -b phase/5-blueprint
git worktree add ../proj-build -b phase/6-build

# Session A — open Claude Code in proj-blueprint:
cd ../proj-blueprint
# Run /vg:blueprint 5

# Session B — open Claude Code in proj-build:
cd ../proj-build
# Run /vg:build 6
```

Both sessions run independently. `events.db` per worktree captures own telemetry. Cross-session destructive guard (v2.52.2) protects each worktree from its own AI cascade but does NOT block cross-worktree git ops (different working trees, different untracked sets — git semantics handle the isolation natively).

## What still blocks across worktrees

Shared at the `.git/` level:
- Branch namespace — `git branch -D feature/x` from worktree A removes branch B is checked out → git refuses.
- Remote refs — `git push --force` from any worktree affects remote.
- Stash list — `git stash list` shows stashes from all worktrees.

These are git's native semantics. The VG harness doesn't add or remove constraints here.

## Anti-patterns

### ❌ Editing `.vg/` from outside the running session

```bash
# Don't:
echo '...' > /path/to/active-wt/.vg/active-runs/sid-X.json
```

The orchestrator owns `.vg/` lifecycle. Manual edits race against `state.py::set_active_run()` and may corrupt the run graph.

### ❌ Sharing one `.vg/` across worktrees via symlink

```bash
# Don't:
cd ../wt-2 && ln -s ../main_repo/.vg .vg
```

This re-introduces the collision the worktree mechanism was designed to avoid. Cross-session destructive guard would also become wrong because it scans all `.vg/active-runs/*.json` — symlinking would re-collapse two sessions into the same lock space.

### ❌ Running concurrent sessions on the same checkout (no worktree)

Two Claude Code instances both pointing at `D:\repo\` without worktrees:
- Same `.vg/events.db` — write contention possible (sqlite handles serialization but lock waits add latency).
- Same `.git/index` — `git add`/`git commit` from one session can race with the other.
- Same working tree — destructive git ops from session B drop session A's untracked artifacts.

If you must, set `VG_RUN_TTL_SEC` lower (e.g., 600 = 10min) so stale runs don't accumulate.

## Operator escape hatches

| Env var | Effect |
|---|---|
| `VG_REPO_ROOT=/path/to/root` | Override `REPO_ROOT` resolution (used by tests + intentional sibling-repo workflows). |
| `VG_ALLOW_DESTRUCTIVE=1` | Bypass cross-session destructive guard for one command. Operator-approved repair flow. |
| `VG_RUN_TTL_SEC=N` | Treat active runs older than N seconds as stale (default 3600). |

## See also

- `tests/test_worktree_isolation.py` — regression suite
- `.claude/scripts/vg-orchestrator/_repo_root.py` — resolver
- `.claude/scripts/hooks/vg-pre-tool-use-bash.sh` — destructive guard (cross-session scan added v2.52.2)
- CHANGELOG: v2.51.13 (subagent session isolation), v2.52.0 (single-session destructive guard), v2.52.2 (cross-session)
