# Plan: B71 — TaskList reliability hardening (deep scan fix)

## Context

**User report (dogfood RTB + general):** TaskList/TodoWrite không hiệu quả:
1. TodoWrite UI ẩn task đang làm hoặc chờ làm, chỉ hiện task đã làm.
2. Khi chạy lại prompt lệnh, tasklist không cập nhật đúng.
3. Khi prompt không phải lệnh (chat thông thường), tasklist cũng không cập nhật.

User yêu cầu deep scan sâu nhất. 4 parallel cavecrew-investigator subagent đã trả về với evidence từ:
- `D:/Workspace/Messi/Code/RTB/.vg/runs/10faabdb-...`
- `D:/Workspace/Messi/Code/RTB/.vg/runs/c1a5edc3-...`

## Root causes (evidence-backed)

### RC#1 — ID schema mismatch (CRITICAL, 100% reproduced)

Contract `projection_items[].id` (from `filter-steps.py`):
```
{step5_fix_loop, step7_matrix_verdict, 0_parse_and_validate, 1_build_artifact_gate, workflow_other}
```

Snapshot `.todowrite-snapshot.json` `items[].id` (from `vg-post-tool-use-todowrite.sh`):
```
{353, 354, 355, 356, 357, 358, 359, 360}   # Run 10faabdb (numeric)
{"Test-Spec 7.16 Steps", "↳ 0 Parse And Validate", ...}   # Run c1a5edc3 (display labels)
```

**0% ID overlap on 2/2 runs.**

`emit-tasklist.py:878` overlay logic:
```python
status = snapshot_overrides.get(iid) or str(it.get("status") or "pending")
```
- `iid` = contract step ID (`step5_fix_loop`)
- `snapshot_overrides.get("step5_fix_loop")` → None
- Falls back to `it.get("status")` = "pending" (contract default at init)
- → Restore output renders ALL items as pending → AI re-emits TodoWrite → all pending
- → User's previous progress (in_progress, completed) invisible after resume

Origin: `scripts/hooks/vg-post-tool-use-todowrite.sh:264-266` snapshot writer uses `tid` (TaskCreate backend ID) without translating to contract step ID space.

### RC#2 — No re-projection trigger on user prompts (HIGH)

`scripts/hooks/vg-user-prompt-submit.sh:52-73` non-slash branch:
- Detects active run alive → injects flow-context reminder ONLY (stderr)
- **Does NOT call `emit-tasklist.py --restore-mode`**

Result: TodoWrite UI stale after chat prompt (between commands). Active run + active TodoWrite have no resync touch-point.

Slash command rerun: command's preflight `emit-tasklist` WRITES new contract (line 982 `_write_contract`), overwriting prior state, losing user's manual TodoWrite progress.

### RC#3 — 6 silent bypass paths (MEDIUM)

1. `vg-tasklist-snapshot.py:70` — empty stdin → no-op (stale persists)
2. `vg-tasklist-snapshot.py:82` — empty items[] → no-op
3. `vg-post-tool-use-todowrite.sh:19-26` — missing run_file/contract → silent exit 0
4. `vg-post-tool-use-todowrite.sh:235` — snapshot helper failure suppressed `|| true`
5. `emit-tasklist.py:858-869` — corrupt snapshot JSON → silent fallback
6. `emit-tasklist.py:878` — ID schema mismatch → 100% silent fail (no warn, no telemetry)

### Test coverage gap (Investigator C)

8 user-facing symptoms — 0 covered by existing tests. Test suite locks infrastructure (mirror parity, schema, hook existence) but NOT behavior at request/response boundaries.

---

## Approach

Single tag **v4.63.0**, 6 sub-batches, ~50 tests, ~6 files modified + 1 new helper.

### Phase 0 — Codex audit (PRE)

Spawn codex `--tier adversarial --sandbox read-only` on this plan. Output: `dev-phases/B71-tasklist-reliability/CODEX-AUDIT.md`. Address BLOCKERs before B71a.

### B71a — Snapshot writer translates display labels → contract step IDs

**Modify:** `scripts/hooks/vg-post-tool-use-todowrite.sh`
- After reading payload (line ~84), load contract from `tasklist-contract.json`.
- Build map: `{display_label_normalized → step_id}` where `display_label_normalized` = lowercase + collapse whitespace + strip `↳ ` prefix + replace `-` and `_` with space.
- For each TodoWrite/TaskCreate todo:
  - If `todo.id` (numeric or display) matches a normalized label → use the contract step_id.
  - Else fall back to slugifying the todo content (lowercase + snake_case).
- Write the resolved `step_id` (NOT raw `tid`) into `.todowrite-snapshot.json`.

**Create:** `scripts/tasklist_id_resolver.py` (Python helper, stdlib only) — pure function for label→step_id resolution. Tested in isolation.

**Persist:** `.vg/runs/{run_id}/.tasklist-id-map.json` — `{display_label_norm → step_id}` for diagnostics + idempotency.

### B71b — UserPromptSubmit re-projection trigger (non-slash)

**Modify:** `scripts/hooks/vg-user-prompt-submit.sh`
- After detecting active run alive (line ~36), check snapshot freshness:
  - If `.todowrite-snapshot.json` mtime > 5 min stale → re-emit restore.
  - Else inject "tasklist current" stub.
- Call `emit-tasklist.py --restore-mode --run-id $RUN_ID` → append output to `additionalContext`.
- Bounded to ONE re-projection per prompt (avoid spam).

**Threshold rationale:** 5-min freshness window prevents context bloat on rapid chat; long pauses (where AI memory fades) trigger restore.

### B71c — Slash command rerun: merge existing state instead of overwrite

**Modify:** `scripts/emit-tasklist.py:_write_contract`
- Before write, check if `tasklist-contract.json` already exists for same `(command, phase)` pair.
- If exists AND not stale (>1 hour) → READ existing `projection_items` statuses → merge into new contract.
- New contract retains:
  - Original `created_at`
  - `projection_items` statuses (from existing snapshot if available)
  - Adds new steps if profile/phase change emits new IDs
  - Marks `merged_from_existing_at = now()` for provenance.

### B71d — ID schema mismatch validator + telemetry

**Modify:** `scripts/emit-tasklist.py:_restore_mode`
- After building `snapshot_overrides` dict, compute overlap:
  - `overlap_pct = len(snapshot_overrides_keys ∩ contract_item_ids) / len(contract_item_ids) * 100`
- If `overlap_pct < 50%`:
  - Print warning to stderr: `⚠ tasklist ID schema mismatch — snapshot uses different ID space (overlap={pct}%). Snapshot will be ignored. Reconciling via b71a resolver.`
  - Emit telemetry: `tasklist.id_schema_mismatch` with payload `{contract_n, snapshot_n, overlap_n, overlap_pct, run_id}`.
  - Attempt secondary resolution: pipe snapshot through `tasklist_id_resolver.py` and re-overlay.

### B71e — Empty-snapshot policy change

**Modify:** `scripts/hooks/vg-tasklist-snapshot.py`
- Line 68-70: empty stdin → return 1 (was 0) + stderr log.
- Line 80-82: empty `items[]` → return 1 + stderr log + emit telemetry `tasklist.empty_snapshot_blocked`.
- Add CLI flag `--allow-empty` for legitimate clearing cases (rare; use in tests).
- Wrap caller in `vg-post-tool-use-todowrite.sh:235` to detect rc=1 and log to `.vg/.session-start-warn.log` (do NOT fail the hook — non-fatal).

### B71f — Behavioral test coverage (8 gap items)

**Create:** `tests/test_batch71_tasklist_behavior.py` — 30+ tests:

1. ID resolver: numeric `tid` → step_id when content match contract slug.
2. ID resolver: display label `"↳ 0 Parse And Validate"` → step_id `0_parse_and_validate`.
3. ID resolver: unmatched todo → slugified fallback (not None).
4. Snapshot writer: writes resolved IDs (not raw tids).
5. Snapshot persists `.tasklist-id-map.json` provenance.
6. UserPromptSubmit: non-slash with stale snapshot → calls restore-mode.
7. UserPromptSubmit: non-slash with fresh snapshot → no restore (avoid spam).
8. UserPromptSubmit: slash command → no extra restore (slash preflight owns).
9. emit-tasklist contract merge: existing contract + same (cmd, phase) → preserve statuses.
10. emit-tasklist contract merge: stale (>1h) existing → fresh rewrite.
11. emit-tasklist contract merge: command/phase change → fresh rewrite.
12. Restore-mode ID overlap validator: 0% overlap → stderr warning + telemetry emit.
13. Restore-mode ID overlap validator: 100% overlap → no warning.
14. Restore-mode ID overlap validator: 50% overlap → no warning (threshold).
15. Snapshot writer: empty stdin → rc=1 + log (was 0/silent).
16. Snapshot writer: empty items → rc=1 + telemetry (was 0/silent).
17. Snapshot writer: `--allow-empty` flag → rc=0 with empty (test use only).
18. Snapshot writer: malformed JSON → rc=2 (unchanged).
19. PostToolUse hook: snapshot rc=1 → logs warning, hook exits 0 (non-fatal).
20. Mirror parity: `scripts/tasklist_id_resolver.py` no .claude/ mirror (scripts not mirrored).
21. emit-tasklist mirror parity: canonical = `.claude/` copy.
22. Hook mirror parity: `vg-user-prompt-submit.sh` canonical = `.claude/` copy.
23. Hook mirror parity: `vg-post-tool-use-todowrite.sh` canonical = `.claude/` copy.
24. Symptom integration: TodoWrite shows only completed after restore → reproduce + assert resolved.
25. Symptom integration: non-command prompt → tasklist refreshed if stale.
26. Symptom integration: slash command rerun → in-progress preserved.
27. RTB run 10faabdb regression: snapshot+contract reconcile produces correct status.
28. RTB run c1a5edc3 regression: snapshot+contract reconcile produces correct status.
29. ID resolver: handles Vietnamese diacritics in display labels (normalize NFD).
30. ID resolver: idempotent — second run yields same map.

### Phase 0 replay — Codex audit POST

After B71f lands, re-spawn codex with v4.62.0..v4.63.0 diff + original audit. Output: `CODEX-AUDIT-REPLAY.md`.

## Critical files

- `scripts/hooks/vg-post-tool-use-todowrite.sh` (B71a snapshot writer)
- `scripts/tasklist_id_resolver.py` (NEW — B71a)
- `scripts/hooks/vg-user-prompt-submit.sh` (B71b)
- `scripts/emit-tasklist.py:_write_contract` (B71c merge)
- `scripts/emit-tasklist.py:_restore_mode` (B71d validator)
- `scripts/hooks/vg-tasklist-snapshot.py` (B71e empty policy)
- `tests/test_batch71_tasklist_behavior.py` (NEW — B71f)

## Risks + mitigations

1. **Slugify collision** — two display labels normalize to same step_id. **Mitigation:** resolver returns `(step_id, confidence)`; collision → confidence < 0.5 → log + fallback to first match. Test #29.
2. **5-min freshness threshold too aggressive** — user types many chat messages → re-projection on every. **Mitigation:** rate limit to once per 60s regardless of mtime; configurable via `VG_TASKLIST_REPROJECT_INTERVAL`.
3. **Contract merge data loss** — stale-detection threshold 1h might preserve outdated state. **Mitigation:** merge ALWAYS preserves completed statuses; pending/in_progress only when phase matches. Test #9-11.
4. **ID schema validator false positive** — telemetry spam on legitimate edge cases (e.g. test fixtures). **Mitigation:** threshold 50% lenient; telemetry only WARNs, no BLOCK.
5. **Empty-snapshot policy break existing tests** — backward incompat. **Mitigation:** B71e `--allow-empty` flag for test fixtures; existing callers patched.
6. **Performance — id_resolver called on every TodoWrite** — overhead. **Mitigation:** cache contract read; resolver < 10ms target. Test #29 perf assertion.
7. **Mirror parity** — every B71 batch ships canonical + `.claude/` copy.

## Verification

- Phase 0: inspect `dev-phases/B71-tasklist-reliability/CODEX-AUDIT.md`.
- Per batch:
  - `python -m pytest tests/test_batch71_tasklist_behavior.py -v` (30+ GREEN expected)
  - `python -m pytest tests/test_tasklist_*.py -q` (no regression on existing 47 tests)
- Mirror: `bash scripts/generate-codex-skills.sh --force && python scripts/verify-codex-mirror-equivalence.py` clean.
- E2E replay: simulate session resume on RTB run 10faabdb fixture → assert restore output shows correct in_progress + pending mix.
- CI gate: tag v4.63.0 → wait `gh run list` both release + Test workflows GREEN.

## Out of scope

- Stop hook tasklist validation hardening (separate concern, B72).
- TodoWrite UI auto-refresh on every model token (orchestrator-level, out of harness scope).
- Cross-runtime adapter migration mid-session (already gated by adapter lock).
- ID schema migration script for legacy `.todowrite-snapshot.json` files in old runs (defer to v5.x cleanup).
