# Codex Adversarial Audit — B71 TaskList Reliability Plan

You are an ADVERSARIAL code reviewer auditing an implementation plan for VGFlow's TaskList/TodoWrite subsystem hardening. Be skeptical. Attack the plan.

Plan: `dev-phases/B71-tasklist-reliability/PLAN.md`

## Context

VGFlow uses a multi-layer TaskList system:
- `emit-tasklist.py` (CLI helper) writes `.vg/runs/{run_id}/tasklist-contract.json` from `filter-steps.py` step lists.
- Native TodoWrite/TaskCreate/TaskUpdate tools — AI projection layer.
- `vg-post-tool-use-todowrite.sh` (PostToolUse hook) captures AI's TodoWrite payload, writes `.vg/runs/{run_id}/.todowrite-snapshot.json`.
- `vg-session-start.sh` on `resume|compact` events calls `emit-tasklist --restore-mode` to re-project from contract+snapshot.
- `vg-tasklist-snapshot.py` is the snapshot writer (stdin → file).
- `vg-pre-tool-use-bash.sh` gates `step-active|mark-step` until evidence file exists.

Bug evidence:
- Run RTB `10faabdb-...`: contract IDs = `{step5_fix_loop, step7_matrix_verdict}`; snapshot IDs = `{353,...,360}`. 0% overlap.
- Run RTB `c1a5edc3-...`: contract IDs = `{0_parse_and_validate, ...}`; snapshot IDs = `{"↳ 0 Parse And Validate", ...}`. 0% overlap.
- Result: `emit-tasklist.py:878` overlay always returns None → restore output shows all-pending.

## Audit attack vectors

1. **B71a ID resolver correctness:** Does normalization correctly map `↳ 0 Parse And Validate` → `0_parse_and_validate`? What about edge cases — empty content, non-ASCII chars, very long labels, numeric IDs vs slugs, identical labels for different steps, AI-renamed labels that don't include step prefix?

2. **B71a slugify collision:** Two completely different display labels normalize to same step_id. Plan's mitigation says "log + fallback to first match" — what if they're different actual steps? Silent step shadowing.

3. **B71a TaskCreate trace replay:** Current `vg-post-tool-use-todowrite.sh:79-103` reconstructs todos from `.taskcreate-trace.jsonl` JSONL on EACH update. If we change to use step_id instead of tid, what happens to existing in-flight traces with raw tids? Backward compat / migration?

4. **B71b re-projection threshold (5min):** User types 10 messages in 10 minutes — at least 1-2 will trigger re-projection. Restore output is markdown table ~300-500 lines. Context bloat over a long session. Is 5min the right threshold? What about the 60s rate limit — does it actually prevent spam if many prompts arrive in burst?

5. **B71b non-slash branch behavior change:** Currently non-slash branch only injects flow-context reminder (cheap). Adding restore-mode invocation makes EVERY non-slash prompt slower (file IO + json parse). What about prompts that are simple "yes/no" answers to AskUserQuestion — they don't need restore.

6. **B71c contract merge semantics:** "If exists AND not stale (>1 hour) → READ existing → merge into new contract." What if filter-steps.py output CHANGED between runs (e.g. profile flipped, command upgraded)? Merge could carry over deleted/renamed steps. How does merge handle:
   - New steps added in new contract: keep with "pending"
   - Old steps removed in new contract: drop or preserve?
   - Step ID changed (renamed): treat as new or merge to renamed?
   Plan says "phase change → fresh rewrite" but step rename within same phase?

7. **B71c 1-hour staleness threshold:** Arbitrary. Mid-day work session can easily span >1h. Should it be based on phase activity instead (e.g. step-markers timestamps)?

8. **B71d telemetry emission:** Each restore call may emit `tasklist.id_schema_mismatch`. If user has 5 active phases all with mismatched legacy snapshots → 5 events per restore. Cost?

9. **B71d secondary resolution attempt:** "Pipe snapshot through resolver and re-overlay" — this means restore-mode invokes resolver synchronously. What's the perf impact? Resolver must be import-able from emit-tasklist (currently scripts/ structure).

10. **B71e empty-snapshot rc=1 change:** PostToolUse hook line 235 currently `|| true` swallows. Changing snapshot to rc=1 just makes the log fire — but hook still continues. Where is the actual "I want to fail" signal? Or is this just diagnostic logging? If diagnostic, why not rc=0 with stderr log?

11. **B71e `--allow-empty` flag for tests:** Adds a CLI flag JUST for tests. Code smell — production code shouldn't have test-only flags. Alternative: tests mock the file or use fixtures.

12. **Mirror parity coverage:** Plan mentions emit-tasklist + hooks mirror to `.claude/`. New file `scripts/tasklist_id_resolver.py` — plan says "no .claude mirror (scripts not mirrored)". Verify: are scripts/ ever mirrored? Check `generate-codex-skills.sh` and test_*.py.

13. **Race conditions:** UserPromptSubmit hook + SessionStart hook + PostToolUse hook all touch snapshot file. Plan doesn't audit ordering. What if PostToolUse fires WHILE SessionStart restore is reading snapshot?

14. **30+ test count adequacy:** 6 sub-batches × 5 tests average = 30. Plan lists 30 tests. Is that adequate for a critical infra fix? B70 shipped 38 tests for similar-scope change.

15. **Out-of-scope items:** Plan defers "Stop hook tasklist validation" to B72 and "Cross-runtime adapter migration" — verify these aren't actually load-bearing for the user's reported symptoms.

## Deliverable

Write structured markdown to: `D:\Workspace\Messi\Code\vgflow-repo\dev-phases\B71-tasklist-reliability\CODEX-AUDIT.md`

Format:
```markdown
# B71 Plan — Adversarial Audit

**Verdict:** PASS | PASS-WITH-NOTES | FAIL

## BLOCKERS (fix before B71a)
- **B-N:** [title] — [problem] — [fix]

## MAJORS (integrate into batch scope)
- **M-N:** [title] — [problem] — [recommendation]

## MINORS
- **m-N:** [observation]

## Coverage gaps
- [test coverage missing for X]

## Risk assessment
- [overall risk + key concerns]
```

After writing, return brief summary (<200 words): verdict + BLOCKER/MAJOR/MINOR counts.

Be ruthless. Past audit on B70 caught 6 BLOCKERS that saved a full re-plan cycle. Do the same here.
