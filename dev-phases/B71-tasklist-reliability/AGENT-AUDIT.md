# B71 Plan — Adversarial Audit (Agent cross-check)

**Verdict:** FAIL — must revise before B71a starts.

The plan correctly identifies the ID-mismatch root cause and the evidence at `emit-tasklist.py:878` is real. But the plan ships with a load-bearing FALSE assumption about the mirror layout, an under-specified resolver that won't actually map the on-disk data we have, and a snapshot-writer hand-off that drops the field the resolver needs. Six BLOCKERs identified.

## Evidence verification

| Plan claim | Status | What the file actually contains |
|---|---|---|
| Run 10faabdb snapshot IDs = `{353..360}` | **CONFIRMED** | `.todowrite-snapshot.json` line 4–34: 8 items, ids `"353"..."360"`, all `completed`. |
| Run 10faabdb contract IDs = `{step5_fix_loop, step7_matrix_verdict}` | **CONFIRMED + partial** | Contract has those two step ids + group `workflow_other` (3 projection_items total). |
| Run c1a5edc3 snapshot IDs = `{"↳ 0 Parse And Validate", ...}` | **CONFIRMED but incomplete** | Snapshot has **19 items** in two stylistic clusters: first 9 use `↳ N Title Case`, next 10 use `↳ test-spec N_snake_case` (e.g. `"↳ test-spec 3_crossai_sweep"`). Plan only describes the first cluster. |
| 0% ID overlap | **CONFIRMED for set-equality** | But the **second cluster** in c1a5edc3 (`"↳ test-spec 0_parse_and_validate"` etc.) literally contains the contract step_id as a substring — a substring-match resolver would hit 8/8 there. Plan's "exact normalized label" approach misses this. |
| `emit-tasklist.py:878` overlay is the failing site | **CONFIRMED** | `status = snapshot_overrides.get(iid) or str(it.get("status") or "pending")` — `iid` is contract step_id, `snapshot_overrides` keyed by snapshot `id`. |
| Snapshot writer stores tid without translating | **CONFIRMED** | `vg-post-tool-use-todowrite.sh:264` `entry = {"id": tid or rec.get("subject", ""), ...}`; tid wins when present. `vg-tasklist-snapshot.py:60` writes `{"id": sid, "status": sstatus}` — **`content` is DROPPED**. |
| Non-slash branch does NOT call emit-tasklist | **CONFIRMED** | `vg-user-prompt-submit.sh:28–88` stderr-only flow-context reminder, no restore call. |
| `scripts/` is NOT mirrored to `.claude/` | **REFUTED — DANGEROUS** | `.claude/scripts/emit-tasklist.py` exists and is byte-identical to canonical. `.claude/scripts/hooks/vg-post-tool-use-todowrite.sh` and `vg-tasklist-snapshot.py` both exist. Existing test `test_emit_tasklist_mirror_byte_identical` ASSERTS the mirror exists. Plan test #20 ("no `.claude/` mirror — scripts not mirrored") is wrong and would either fail or, worse, silently pass because the mirror just hasn't been re-synced yet. |
| Existing test count | **VERIFIED** | `tests/test_tasklist_session_restore.py` has 7 tests; one (`test_restore_uses_snapshot_status_when_present`) covers the happy path only — uses `id="step1"` on both sides. The failure-mode the plan targets has **zero existing coverage**. |

## BLOCKERS (must fix before B71a)

- **B-1: `scripts/` IS mirrored to `.claude/scripts/`, plan claims it is not.** The new helper `scripts/tasklist_id_resolver.py` MUST ship with a `.claude/scripts/tasklist_id_resolver.py` byte-identical copy, and the mirror-equivalence test must include it. Test #20 ("Mirror parity: `tasklist_id_resolver.py` no `.claude/` mirror") is inverted — replace with "canonical == mirror byte-identical". Verified: `.claude/scripts/emit-tasklist.py` exists; `tests/test_tasklist_session_restore.py:test_emit_tasklist_mirror_byte_identical` already asserts this pattern. — Fix: rename the helper to plain `.py`, ship in both trees, add equivalence test. Also audit `scripts/vg_sync_codex.py` / `scripts/sync-vg-skills.py` to confirm what the mirror generator covers.

- **B-2: Snapshot writer drops `content` before resolver can run.** `vg-tasklist-snapshot.py:57` does `sid = str(it.get("id") or it.get("content") or "")` and writes ONLY `{"id": sid, "status": sstatus}`. Plan says "resolver maps display label → step_id at snapshot-write time" but never specifies WHERE the resolution happens. If it happens inside the helper, the helper currently sees `id=353` (numeric tid) and has no content. If it happens earlier in `vg-post-tool-use-todowrite.sh:264`, then the plan needs to also rewrite the TaskCreate-trace reconstruction (line 248–274) to use `rec.get("subject")` for resolution. Plan must pick one and state it. Recommended: do resolution **in the hook** before piping to helper, and persist both `step_id` (for restore overlay) **and** original `content` (for diagnostics) in the snapshot payload schema. — Fix: redefine snapshot schema to `{"items":[{"id": step_id, "content": original_label, "status": ...}]}` and update helper validator.

- **B-3: Resolver semantics under-specified for the *actual* snapshot patterns on disk.** The real `c1a5edc3` snapshot contains FIVE distinct label families for the same 8 underlying steps:
  1. `"↳ 0 Parse And Validate"` — Title Case, dot-decimal numbering
  2. `"↳ 3.5 CrossAI Sweep"` — half-step + camel acronym
  3. `"↳ test-spec 0_parse_and_validate"` — command-prefixed snake_case
  4. `"↳ test-spec 4_codegen — Spawn vg-test-codegen full subagent pass"` — step_id + em-dash + free text
  5. Group rows `"Test-Spec 7.16 Steps"` / `"Other Workflow Steps — test-spec 7.16"` — neither matches contract group `workflow_other`.

  Plan's algorithm `lowercase + collapse ws + strip ↳ + replace -/_ with space` maps:
  - `"↳ 3.5 CrossAI Sweep"` → `"3.5 crossai sweep"` → slugified `3_5_crossai_sweep` ≠ contract `3_crossai_sweep`. **MISS.**
  - `"↳ test-spec 0_parse_and_validate"` → `"test spec 0 parse and validate"` ≠ contract `0_parse_and_validate`. **MISS** unless the resolver does substring/suffix matching, which the plan doesn't promise.

  The resolver must (a) strip a leading command-prefix (`test-spec `, `build `, ...) heuristically; (b) collapse `3.5 → 3_5` AND attempt `3.5 → 3`; (c) do substring match against contract step_ids as a fallback before slug-fallback. Plan says none of this. — Fix: spec the resolver as a **layered** matcher (exact → strip-command-prefix → strip-decimal → substring → slug), and add fixture tests using these five literal labels.

- **B-4: Slugify collision with same step shadowing.** Two rows in the same snapshot — `"↳ 3 Validate Deep Specs"` (line 20) and `"↳ test-spec 3_validate_deep_specs"` (line 56) — both legitimately resolve to contract `3_validate_deep_specs`. That's a **valid** collision, not a shadowing bug. But two rows like `"↳ 3 Validate Deep Specs"` (status=completed) and `"↳ 3 Validate Deep Specs — retry"` (status=in_progress) could BOTH resolve to `3_validate_deep_specs` with conflicting statuses, and plan's "log + fallback to first match" silently picks the wrong one. — Fix: when collision detected, conflict-resolution must prefer `in_progress > completed > pending` (active state wins) so user's current focus isn't overwritten by a stale completed echo. Add a test for status-conflict precedence.

- **B-5: Plan's 1-hour merge staleness lets stale state poison a fresh run.** Contract for `c1a5edc3` was created `17:46`; snapshot last touched `18:32` (46 min). If user runs `/vg:test-spec 7.16` again at `18:40`, the merge picks up the c1a5edc3 contract and the AI's last-known TodoWrite state — INCLUDING the orphan rows `"↳ test-spec 4_codegen — Spawn vg-test-codegen full subagent pass"` that aren't in the new contract. Plan doesn't say what `_write_contract` merge does with orphan snapshot items. If it preserves them, the new contract has phantom steps; if it drops them, in-progress work disappears silently. — Fix: spec orphan handling explicitly — drop with WARN telemetry; if any orphan was `in_progress` block the merge with a `vg:override-resolve` prompt instead of silent drop.

- **B-6: B71b every-prompt restore injection has real perf + context cost.** Plan budgets 5-min freshness + 60s rate limit, but `additionalContext` from restore is a markdown table of N rows (c1a5edc3 → 19+ rows × ~80 chars = ~1500 chars per inject). On a chat-heavy session with one trigger every 5 min for 2 hours, that's ~24 injections — repeated context bloat. Worse, simple Y/N replies to AskUserQuestion would also trigger it. — Fix: gate B71b on (a) snapshot ID-overlap < 50% (the actual broken case) OR (b) `last_restore_at` > 30 min — not just mtime. Skip when prompt length < 10 chars (Y/N reply heuristic). Add VG_TASKLIST_REPROJECT_DISABLE escape hatch.

## MAJORS

- **M-1: `--allow-empty` is the wrong API.** Plan adds a CLI flag JUST for tests. Cleaner: tests construct fixtures via `_write_snapshot()` directly (it's importable) and skip the CLI path. Production code stays test-flag-free.

- **M-2: B71e rc=1 + `|| true` is purely cosmetic.** `vg-post-tool-use-todowrite.sh:235` already wraps in `|| true`. Changing the snapshot exit code to 1 only fires the new stderr log; the hook still exits 0 either way. If the intent is just diagnostics, use rc=0 with a structured stderr line; if the intent is to fail the hook on empty, remove the `|| true`. Pick one.

- **M-3: B71d telemetry storm risk.** Per-restore emission for 5 active mismatched legacy phases = 5 events per restore = O(N×prompts) over a debug session. Throttle: emit at most once per (run_id, day) — store last-emit timestamp in a sidecar file.

- **M-4: B71c merge needs a step-rename adapter.** Filter-steps.py output evolves across VGFlow versions. A step renamed `step5_fix_loop` → `5_fix_loop` would treat the existing snapshot's `step5_fix_loop=completed` as an orphan and re-show it as pending. Add a versioned step-id-alias table in the resolver, or compute name-edit-distance as a tiebreaker.

- **M-5: Race between PostToolUse snapshot-write and SessionStart restore-read.** Plan doesn't audit this. SessionStart is `resume|compact` event — Claude Code reliably fires it on session boot before any tool call, so PostToolUse can't run mid-restore in normal flow. But UserPromptSubmit + PostToolUse can interleave with B71b's restore call on the same prompt. Use os.replace (already done by `_write_snapshot`) + read-snapshot-as-bytes-then-parse pattern in restore-mode to avoid partial reads. Already correct; just call it out and add a regression test.

- **M-6: Restore reordering already exists; plan re-implements implicitly.** `emit-tasklist.py:_restore_mode` line 890 already calls `reorder_projection_by_status`. Plan's "active focus first" requirement is already met — but only AFTER overlay works. State this clearly so the plan doesn't accidentally double-reorder or skip it.

## MINORS

- **m-1:** Plan says "30+ tests" but lists exactly 30. B70 shipped 38. ID-mismatch fix is similar surface area + 5 label families × 3 statuses × 2 contract patterns = at least ~30 fixture-table cases alone. Bump to 40+.

- **m-2:** Plan test #29 — Vietnamese diacritics — is a placeholder; the real snapshot has no Vietnamese content. Replace with "test-spec command-prefix stripping" (the actual on-disk pattern).

- **m-3:** Plan does not state whether `.tasklist-id-map.json` is added to `.gitignore`. It must be — it's a per-run cache.

- **m-4:** Plan never specifies what `_restore_mode` does when overlay rate is ≥50% but < 100%. Partial-overlay is the LIKELY post-fix common case (resolver does its best). The 50% telemetry trigger is a cliff, not a curve.

- **m-5:** Plan does not list a rollback signal. Add `VG_TASKLIST_RESOLVER_DISABLE=1` to bypass resolver and use raw IDs (today's behavior) in case B71a misfires in prod.

## Coverage gaps

- No test for `vg-post-tool-use-todowrite.sh:264` snapshot-payload schema change (the `content` field must now flow through).
- No test for resolver perf — plan claims < 10ms but never asserts. Add `pytest.mark.benchmark` or a wall-clock < 50ms cap (contract read + 20-row resolution).
- No regression test for the `.taskcreate-trace.jsonl` legacy format on B71a hot upgrade — old traces have raw tids; the resolver must still produce a sensible snapshot when run against a pre-B71 trace.
- No test for `.todowrite-snapshot.json` schema migration when reading a pre-B71 snapshot (only `id`, no `content`) — restore-mode must fall back to id-only matching gracefully.
- Symptom tests #24-26 are too coarse; need to explicitly use the c1a5edc3 fixture and assert that the 5 label families ALL resolve.
- No test for the orphan-snapshot-item case (snapshot has IDs that don't exist in contract). This is the c1a5edc3 reality (snapshot 19 items vs contract 9).

## Risk assessment

**Overall risk:** MEDIUM-HIGH. The plan correctly localizes the root cause but treats the resolver as a one-pager, when the actual on-disk data shows at least 5 stylistic label families that need a layered matcher. Combined with the mirror-parity miss (B-1), shipping B71a as-described would either fail CI immediately or, worse, ship a partial fix that only addresses the cleanest snapshot pattern while leaving the messier patterns (which is the bulk of legacy runs) broken silently.

**Key concerns ranked:**
1. **B-1 mirror-parity** — would block merge or break codex sync on day one.
2. **B-2 snapshot-writer hand-off** — without `content` flowing through, the resolver has nothing to resolve at restore-time, and B71a's value drops to ~30% of cases.
3. **B-3 layered matcher spec** — without strip-command-prefix and substring fallback, c1a5edc3's second cluster (10/19 items) stays broken.
4. **B-6 context bloat from B71b** — could regress AI behavior on chat-heavy phases before B71a even ships value.
5. **B-4/B-5 silent shadowing/orphan poison** — failure modes are silent and only surface in user complaints, exactly the class of bug we're trying to eliminate.

**Recommendation:** revise PLAN.md sections B71a, B71c, B71f. Re-spec the resolver as a layered matcher with explicit fixture tests. Fix mirror claim. Add orphan-handling and status-conflict-precedence rules. Bump test count to 40+. Then proceed.
