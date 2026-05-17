I couldn’t write `dev-phases/B71-tasklist-reliability/CODEX-AUDIT.md` because this run is read-only. Exact content:

```markdown
# B71 Plan — Adversarial Audit

**Verdict:** FAIL

## BLOCKERS (fix before B71a)
- **B-1:** Legacy numeric snapshots are unrecoverable from snapshot alone — `vg-tasklist-snapshot.py:57-60` drops `content` and persists only `{id,status}`, so B71d cannot map RTB `10faabdb` numeric IDs by "piping snapshot through resolver" — fix by resolving before content loss and, for legacy runs, rehydrate from `.taskcreate-trace.jsonl` or `.tasklist-id-map.json`; otherwise emit explicit unresolvable telemetry.
- **B-2:** Collision handling is unsafe — labels like group `Complete` and step `↳ Complete` collide after stripping `↳`; "log + fallback to first match" silently shadows a real step — fix by failing closed on ambiguity and matching with kind, parent, order, exact title, and contract ID.
- **B-3:** TaskCreate trace schema boundary is undefined — current trace replay keys updates by raw backend `task_id` (`vg-post-tool-use-todowrite.sh:44-102`, `262-273`); changing trace IDs to step IDs breaks future `TaskUpdate` joins — fix by keeping trace raw and projecting only the snapshot layer.
- **B-4:** Contract merge can resurrect deleted or renamed steps — `_write_contract` currently rewrites a fresh pending contract (`emit-tasklist.py:687-775`), but B71c does not define authoritative new-vs-old semantics — fix by treating new `filter-steps.py` output as canonical, merging exact IDs only, dropping removed IDs, and treating renames as new unless an explicit alias exists.
- **B-5:** Restore-time resolver cannot fix the stated RTB regression as planned — `emit-tasklist.py:856-878` overlays only snapshot IDs, and legacy numeric snapshots have no labels left — add a concrete RTB fixture proving numeric trace + snapshot reconciliation, not just display-label reconciliation.
- **B-6:** Mirror parity assumption is false — the repo has real `.claude/scripts` mirrors and tests enforce byte parity for `emit-tasklist.py` and hook helpers; a new `scripts/tasklist_id_resolver.py` with "no .claude mirror" can break `.claude/scripts/emit-tasklist.py` imports — mirror the helper and test canonical/.claude/global resolution.
- **B-7:** Empty-snapshot rc=1 is not a failure signal — caller still swallows the helper via `|| true` at `vg-post-tool-use-todowrite.sh:235`; this is only diagnostic noise unless the hook captures stderr/rc and emits durable telemetry — define fail/warn semantics before changing exit codes.

## MAJORS (integrate into batch scope)
- **M-1:** Normalization spec is underdefined for empty content, long labels, punctuation, status words, and Unicode. Specify Unicode normalization, max label length, allowed statuses, and unresolved behavior.
- **M-2:** Slugified fallback is dangerous. Test #3 says unmatched todo becomes "not None", but an invented slug is ignored by overlay or can collide with a future ID. Store unresolved rows separately instead.
- **M-3:** B71b can create context bloat. Current non-slash branch emits a cheap stderr reminder (`vg-user-prompt-submit.sh:30-72`); a 300-500 line restore table every stale prompt is too much. Use compact digest + hash dedupe; reserve full table for resume/compact or mismatch.
- **M-4:** B71b conflicts with simple replies and AskUserQuestion flow. Post-AskUserQuestion already emits a targeted reminder; do not dump full restore state on yes/no answers unless the tasklist actually changed.
- **M-5:** The 5-minute and 1-hour thresholds are arbitrary and inconsistent with existing active-run stale rules. Base decisions on active run liveness, latest marker/snapshot time, and contract source fingerprint.
- **M-6:** Telemetry can spam and attach to the wrong run. `emit-event` resolves current run unless `--run-id` is passed; restore hooks can run with multiple active sessions. Emit with explicit run ID and dedupe by run + snapshot hash + contract hash.
- **M-7:** Secondary restore resolver needs an import/runtime design. Avoid shell-piping JSON through a helper on every restore; import a pure function from the resolved `VG_HOME/scripts` path and benchmark 500+ projection rows.
- **M-8:** New `.tasklist-id-map.json` has no atomicity contract. Snapshot writes use temp + replace (`vg-tasklist-snapshot.py:88`); the new map must do the same and tolerate partial JSONL trace reads.
- **M-9:** Contract merge must recompute group statuses. Preserving old group status directly can contradict child statuses after added/removed steps.
- **M-10:** The test plan says "~50 tests" but lists 30. Critical infra needs property/collision tests, legacy fixture tests, concurrency tests, and hook-output schema tests.

## MINORS
- **m-1:** Test numbering is inconsistent: slug collision mitigation points to test #29, but #29 is Vietnamese diacritics.
- **m-2:** Warning text says "snapshot will be ignored" and "reconciling" in the same message. Make the runtime behavior unambiguous.
- **m-3:** `confidence < 0.5` is arbitrary. Use deterministic match classes: exact, unique normalized, ambiguous, unresolved.
- **m-4:** `--allow-empty` as "for tests" is a smell. If clearing is legitimate, make it a production `--clear`/`--allow-empty` mode with caller semantics.
- **m-5:** Plan should state whether `.tasklist-id-map.json` is diagnostic-only or authoritative during restore.

## Coverage gaps
- Resolver collisions: group-vs-step same label, duplicate step titles, AI-renamed labels, missing `↳`, numeric IDs with content, numeric IDs without content.
- Legacy RTB fixtures: `10faabdb` numeric snapshot + trace and `c1a5edc3` display-label snapshot.
- Contract merge: added, removed, renamed, reordered, profile-flipped, command-upgraded, and stale-but-active runs.
- UserPromptSubmit: compact digest, full restore, no-restore for fresh hash, AskUserQuestion yes/no reply, burst prompts, and long chat sessions.
- Telemetry: explicit `--run-id`, dedupe, multi-active-session behavior, and no spam on repeated restore.
- Race tests: restore while PostToolUse writes snapshot, trace append during replay, corrupt id-map, partial JSONL line.
- Mirror/import tests: `scripts/`, `.claude/scripts/`, global `~/.vgflow/scripts`, and Codex/fallback adapter no-regression.
- Empty snapshot: empty stdin, empty items, malformed JSON, explicit clear, and prior snapshot preservation.

## Risk assessment
The plan diagnoses the right root cause, but the proposed fixes still allow silent progress corruption. The highest risks are unrecoverable legacy numeric snapshots, ambiguous label resolution, unsafe contract merges, and context bloat on ordinary prompts. Ship only after resolver semantics, trace compatibility, merge rules, telemetry dedupe, and mirror parity are made deterministic and tested against real RTB fixtures.
```

Summary: **FAIL**. Counts: **7 BLOCKERS**, **10 MAJORS**, **5 MINORS**. The plan is directionally right, but B71a/B71c as written can silently corrupt task progress instead of restoring it.