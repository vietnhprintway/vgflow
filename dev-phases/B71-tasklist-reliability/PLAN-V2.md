# Plan v2: B71 — TaskList reliability (audit-revised)

## Audit summary

**Verdict:** Both Codex + Agent audits returned FAIL on PLAN.md v1.
- Codex: 7 BLOCKERs / 10 MAJORS / 5 MINORS
- Agent: 6 BLOCKERs / 6 MAJORS / 5 MINORS
- 9 unique BLOCKERs after dedup. Plan v2 below addresses ALL.

## Root causes (unchanged, confirmed by both audits)

RC#1 — Contract step_id ≠ snapshot id (0% overlap, 2/2 RTB runs verified).
RC#2 — Non-slash user prompts never trigger re-projection.
RC#3 — 6 silent bypass paths in snapshot/restore pipeline.

## Critical audit fixes integrated

| # | Audit BLOCKER | Plan v2 fix |
|---|---|---|
| 1 | scripts/ IS mirrored (both audits) | NEW: ship `scripts/tasklist_id_resolver.py` + `.claude/scripts/tasklist_id_resolver.py` byte-identical. Mirror parity test asserts both. |
| 2 | Snapshot drops `content` (both) | Migrate `.todowrite-snapshot.json` schema v1→v2: `{id, content, status}`. v2-aware reader; v1 fallback for legacy. |
| 3 | Legacy numeric snapshots unrecoverable (Codex B-1/B-5) | NEW: rehydration step — when snapshot v1 has only numeric IDs, read `.taskcreate-trace.jsonl` for original `subject` content + resolve. |
| 4 | Resolver semantics for 5 label families (Agent B-3) | Layered matcher with deterministic precedence: exact → strip-cmd-prefix → strip-decimal → substring → slug. Return `(step_id, match_class)` where match_class ∈ {exact, normalized, substring, slug, unresolved}. |
| 5 | Collision unsafe (both) | Status-precedence on collision: `in_progress > completed > pending`. Group-vs-step disambig via `kind` field. Ambiguous = fail-closed (unresolved). |
| 6 | TaskCreate trace schema boundary (Codex B-3) | Keep `.taskcreate-trace.jsonl` UNCHANGED with raw `task_id`. Resolution happens only at snapshot-write layer. TaskUpdate joins still work on raw IDs. |
| 7 | Contract merge orphan/rename (both) | Explicit semantics. New `filter-steps.py` output = canonical. Common IDs merge with preserved status. Removed IDs dropped + WARN telemetry. In-progress orphan → BLOCK merge with `vg:override-resolve` prompt. Alias table (versioned) for known renames. |
| 8 | B71b context bloat (both) | Replace full table inject with COMPACT digest: 1-line summary (`tasklist: 8 in_prog / 12 pending / 5 done — overlap mismatch: yes`). Hash-dedupe per (contract_hash, snapshot_hash). Skip on prompt < 10 chars OR post-AskUserQuestion within 60s. Triggers: overlap < 50% OR last_restore > 30min OR contract_hash changed. |
| 9 | Empty-snapshot rc=1 cosmetic (Codex B-7) | DEFERRED — moved to B72 backlog. Plan v2 only changes stderr line format (richer diagnostic) without altering rc. No `--allow-empty` flag. |

## Architecture (revised)

### Snapshot schema v2

```json
{
  "schema_version": 2,
  "items": [
    {"id": "0_parse_and_validate", "content": "↳ 0 Parse And Validate", "status": "completed", "match_class": "normalized"},
    {"id": "<unresolved>:bg.spec-codegen", "content": "↳ Spawn vg-test-codegen", "status": "in_progress", "match_class": "unresolved"}
  ],
  "id_map_provenance": {
    "contract_path": ".vg/runs/{run_id}/tasklist-contract.json",
    "contract_hash": "sha256:...",
    "resolved_at": "ISO8601"
  }
}
```

`<unresolved>:` prefix on `id` keeps unresolved items addressable (no shadowing of real step_ids) without dropping them.

### Resolver pipeline (B71a layered matcher)

Input: `(raw_label, contract_items[])` → Output: `(step_id, match_class)`.

1. **exact** — `raw_label` matches contract `step_id` literally.
2. **strip-cmd-prefix** — strip leading `↳ `, then strip command prefix (`test-spec `, `build `, `scope `, `review `, `accept `).
3. **strip-decimal** — `3.5 X` → also attempt `3_X` (drop decimal sub-step).
4. **substring** — contract `step_id` is substring of normalized label.
5. **slug** — slugify label, compare to contract step_id.
6. **unresolved** — return `<unresolved>:hash(label)` + `match_class=unresolved`.

If multiple matches, prefer `kind=step > group`; tie-break by Levenshtein distance to step_id (smaller wins). If still ambiguous → unresolved.

### Legacy snapshot rehydration

When loading v1 snapshot (no schema_version, no content):
- Read sibling `.taskcreate-trace.jsonl`.
- Build `{task_id → subject}` map from `action=create` entries.
- For each snapshot item with numeric `id`, look up subject in map.
- Run subject through resolver → get step_id + match_class.
- Write v2 snapshot in-place (one-time migration, log + telemetry `tasklist.snapshot_migrated_v1_v2`).

### Compact restore digest (B71b)

Replace the multi-row markdown table with a 1-line digest:

```
[VG-TASKLIST] phase=7.16 cmd=test-spec | 3 in_progress / 8 pending / 7 completed | overlap=86% | contract=a3f4b21 | snapshot=e7c9d33 | last_restored=12m_ago
```

When AI needs full state, it can grep `.vg/runs/$RUN_ID/tasklist-contract.json` directly. Full markdown still emitted on `SessionStart:resume|compact` (one-shot).

### Trigger conditions (B71b)

Re-project on UserPromptSubmit non-slash WHEN ALL:
- Active run alive.
- `prompt_length >= 10` chars (skip Y/N).
- No `PostToolUse:AskUserQuestion` event in last 60s.
- AND ANY:
  - `overlap_pct < 50%` (broken case)
  - `(now - last_restore_at) > 30min`
  - `contract_hash` changed since last restore.

Rate-limit: max 1 restore per 60s globally regardless. `VG_TASKLIST_REPROJECT_DISABLE=1` escape hatch.

## Sub-batches

### B71a — Resolver + snapshot writer (snapshot schema v2)

**Create:**
- `scripts/tasklist_id_resolver.py` + `.claude/scripts/tasklist_id_resolver.py` (byte-identical).
- Pure functions: `resolve(label, contract_items, kind=None) -> (step_id, match_class)`. Stdlib only.
- `MatchClass = Literal['exact','normalized','substring','slug','unresolved']`.

**Modify:**
- `scripts/hooks/vg-post-tool-use-todowrite.sh` (+ mirror): pipe full content (not just id) to snapshot helper. Resolve via `tasklist_id_resolver.py` BEFORE pipe.
- `scripts/hooks/vg-tasklist-snapshot.py` (+ mirror): accept v2 schema with `content` + `match_class`. Read sibling contract to validate `step_id` references when match_class != unresolved.
- `scripts/emit-tasklist.py:_restore_mode` (+ mirror): v2 reader. For v1 snapshots, invoke rehydration via trace lookup. Resolver imported as module (not subprocess pipe per audit M-7).

**Test:** `tests/test_batch71a_resolver.py` — 22 tests:
- exact, strip-prefix, strip-decimal, substring, slug, unresolved match each.
- 5 label families from RTB c1a5edc3 fixture.
- Collision precedence: in_progress > completed.
- Group vs step disambig.
- Vietnamese / Unicode normalization (NFD/NFC).
- Empty label, very long label (>1KB).
- Idempotent (resolve twice = same result).
- Property test: resolver never returns None.
- Schema v1 → v2 migration round-trip.
- Legacy numeric rehydration via trace (RTB 10faabdb fixture).
- Resolver perf < 50ms for 500-row contract (subprocess.run capture timing).
- Resolver mirror byte-parity.

### B71b — UserPromptSubmit compact digest re-projection

**Modify:**
- `scripts/hooks/vg-user-prompt-submit.sh` (+ mirror): non-slash branch — compute digest, append to existing flow-context stderr line (no markdown table).
- Trigger conditions per architecture section.
- `VG_TASKLIST_REPROJECT_DISABLE` env override.

**Test:** `tests/test_batch71b_user_prompt_digest.py` — 12 tests:
- Active run alive + stale snapshot → digest emitted.
- Y/N prompt (< 10 chars) → no digest.
- Post-AskUserQuestion within 60s → no digest.
- contract_hash unchanged + recent restore → no digest.
- `VG_TASKLIST_REPROJECT_DISABLE=1` → no digest.
- Slash command → no digest (slash preflight owns).
- Digest format matches spec (1-line, all fields).
- Rate-limit: 2 prompts in 30s → only 1 digest.
- Hash dedup correctness.
- Stderr-only emission (no stdout pollution).
- Hook mirror parity.

### B71c — Contract merge with explicit orphan/rename handling

**Modify:**
- `scripts/emit-tasklist.py:_write_contract` (+ mirror): merge semantics per audit fix #7.
- Add `STEP_ID_ALIASES` versioned dict in `scripts/tasklist_id_resolver.py` — maps known renames `step5_fix_loop ↔ 5_fix_loop`.
- In-progress orphan detection: emit telemetry `tasklist.merge_blocked_inprogress_orphan` + write `.vg/runs/{run_id}/.merge-orphan-blocker.json`. Caller (slash command preflight) reads and prompts user.

**Test:** `tests/test_batch71c_contract_merge.py` — 10 tests:
- Common IDs merge preserved status.
- Removed step + status=completed → drop + WARN.
- Removed step + status=pending → drop silently.
- Removed step + status=in_progress → BLOCK merge.
- Added step → pending.
- Rename via alias table → migrate status.
- Rename without alias → treat as removed+added.
- Profile flip → fresh rewrite.
- Phase change → fresh rewrite.
- Group status recomputed from child statuses.

### B71d — Restore overlap validator + telemetry dedupe

**Modify:**
- `scripts/emit-tasklist.py:_restore_mode` (+ mirror):
  - After overlay, compute `overlap_pct`.
  - If < 50%, emit `tasklist.id_schema_mismatch` once per `(run_id, contract_hash)` (sidecar `.vg/runs/{run_id}/.restore-telemetry.json`).
  - Print stderr warning with run_id for diagnostic.
  - Trigger legacy rehydration if snapshot is v1.

**Test:** `tests/test_batch71d_restore_validator.py` — 8 tests:
- 0% overlap → warn + telemetry.
- 50% exact → no warn.
- 80% overlap → no warn.
- v1 snapshot triggers rehydration.
- Telemetry dedupe: same hash twice → emit once.
- Telemetry deduplicates with explicit `--run-id`.
- Partial overlap (40%) emits exact percent in warning.
- Mirror parity.

### B71f — Behavioral coverage + integration

**Create:** `tests/test_batch71f_integration.py` — 12 tests covering:
- RTB c1a5edc3 fixture: snapshot v1 → migrate → resolve all 5 label families.
- RTB 10faabdb fixture: numeric snapshot → trace rehydration → resolve.
- End-to-end resume: contract + snapshot → restore → assert in_progress/pending all visible.
- Non-command prompt: 3 stale prompts → 1 digest emission (rate limit).
- Slash command rerun: existing contract → merge preserves user progress.
- Orphan in-progress → BLOCK with override-resolve directive.
- Concurrent PostToolUse + UserPromptSubmit race (file locking).
- Hook chain end-to-end with synthetic phase fixture.
- Stop hook unchanged (no regression).
- Adapter lock unchanged (no regression).
- Empty TodoWrite payload (edge case) → no snapshot clobber.
- All 4 phases (build/review/test-spec/test) project correctly.

### B71g — Documentation + migration notes

**Create:** `docs/architecture/tasklist-id-resolution.md` — explains snapshot schema v2, resolver pipeline, legacy migration, troubleshooting.

**Modify:** `commands/vg/_shared/lib/tasklist-projection-instruction.md` (+ mirror): note that snapshot now persists `content` + step_id; AI should still pass `id` field with step_id when possible to avoid resolver overhead.

## Phase 0 replay (POST)

After all B71 sub-batches land, re-spawn codex + Agent. Both must verdict PASS or PASS-WITH-NOTES. Address any new BLOCKERs in v4.63.1 hotfix.

## Test budget total

22 (B71a) + 12 (B71b) + 10 (B71c) + 8 (B71d) + 12 (B71f) + mirror parity (~5) = **~65 tests** (vs v1 plan's 30, vs B70's 38).

## Critical files

- `scripts/tasklist_id_resolver.py` + `.claude/scripts/tasklist_id_resolver.py` (NEW, both)
- `scripts/hooks/vg-post-tool-use-todowrite.sh` + mirror (B71a)
- `scripts/hooks/vg-tasklist-snapshot.py` + mirror (B71a v2 schema)
- `scripts/emit-tasklist.py` + `.claude/scripts/emit-tasklist.py` (B71a v2 reader + B71c merge + B71d telemetry)
- `scripts/hooks/vg-user-prompt-submit.sh` + mirror (B71b digest)
- `commands/vg/_shared/lib/tasklist-projection-instruction.md` + mirror (B71g)
- `docs/architecture/tasklist-id-resolution.md` (NEW, no mirror)

## Risks + mitigations

1. **Legacy snapshot trace missing** — `.taskcreate-trace.jsonl` may have been gc'd. Rehydration falls back to numeric `<unresolved>` IDs. Telemetry alerts user to manually re-emit TodoWrite.
2. **Resolver perf on 500+ row contracts** — benchmark assertion < 50ms via `time.perf_counter()`. Cache contract reads.
3. **Mirror parity drift** — auto-regenerated by `generate-codex-skills.sh`. Pre-push hook (existing) catches.
4. **Schema v1 readers in production** — emit-tasklist.py is the only reader; v1 fallback path tested.
5. **STEP_ID_ALIASES drift** — versioned dict in resolver module. Updates require explicit PR.
6. **B71b digest spam in chat-heavy phases** — rate-limit 1/60s + content dedup catches it.

## Verification

- Phase 0: inspect CODEX-AUDIT.md + AGENT-AUDIT.md.
- Per batch: pytest individual file, ALL GREEN.
- Mirror: `bash scripts/generate-codex-skills.sh --force && python scripts/verify-codex-mirror-equivalence.py`.
- E2E fixtures: copy real RTB run data to `tests/fixtures/rtb-snapshots/` (already at fixtures dir per investigator).
- CI: tag v4.63.0 → wait both workflows GREEN.
- Replay codex+Agent audit → must PASS or PASS-WITH-NOTES.
