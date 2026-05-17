# TaskList ID Resolution

VGFlow's TaskList subsystem reconciles three ID spaces that historically
drifted and silently dropped user progress on session resume/compact. This
doc explains the v2 snapshot schema, the layered resolver, legacy
rehydration, and troubleshooting.

Status: stable as of v4.63.2 (B71a/B71b/B71c/B71d/B71f shipped).
Out of scope: B71e (cosmetic empty-snapshot exit code).

---

## Three ID spaces

| Layer | ID source | Example | Owner |
|---|---|---|---|
| **Contract step_id** | `filter-steps.py` snake_case canonical names | `0_parse_and_validate`, `step5_fix_loop`, `workflow_other` | `emit-tasklist.py:_write_contract` |
| **Snapshot id** (v1 pre-B71a) | AI's TodoWrite content / TaskCreate `task_id` | `353`, `"↳ 0 Parse And Validate"`, `"↳ test-spec 4_codegen — Spawn"` | AI free-form |
| **Snapshot id** (v2 post-B71a) | Resolved to contract step_id, content preserved | `id="0_parse_and_validate"`, `content="↳ 0 Parse And Validate"`, `match_class="normalized"` | `vg-post-tool-use-todowrite.sh` |

The original bug: contract step_id ≠ snapshot id → 0% overlap on
`emit-tasklist.py:_restore_mode` overlay → all items fell back to "pending"
→ on resume the TodoWrite UI appeared "reset", masking the user's actual
in-progress and completed work.

---

## Snapshot schema v2

Location: `.vg/runs/{run_id}/.todowrite-snapshot.json`

```json
{
  "schema_version": 2,
  "items": [
    {
      "id": "0_parse_and_validate",
      "content": "↳ 0 Parse And Validate",
      "status": "completed",
      "match_class": "normalized"
    },
    {
      "id": "<unresolved>:abc123ef",
      "content": "Garbage label that didn't resolve",
      "status": "in_progress",
      "match_class": "unresolved"
    }
  ],
  "id_map_provenance": {
    "contract_path": ".vg/runs/{run_id}/tasklist-contract.json",
    "contract_hash": "sha256:a3f4b21c8d52",
    "snapshot_hash": "sha256:e7c9d33a4910",
    "resolved_at": "2026-05-17T15:30:00Z"
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | `2` for post-B71a. Absent or `<2` = legacy v1 → triggers rehydration. |
| `items[].id` | str | Resolved contract step_id, OR `<unresolved>:<8-char-hash>` if no match. |
| `items[].content` | str | Original AI display label. Preserved for diagnostics + restore-time re-resolution. |
| `items[].status` | str | One of `pending`, `in_progress`, `completed`. |
| `items[].match_class` | str | One of `exact`, `normalized`, `strip-cmd`, `strip-decimal`, `substring`, `slug`, `unresolved`. |
| `id_map_provenance.contract_hash` | str | sha256:12-char prefix. For change-detection in B71b digest. |
| `id_map_provenance.snapshot_hash` | str | sha256:16-char prefix. For dedup. |

**v1 backward compat:** `vg-tasklist-snapshot.py` auto-upgrades v1 payload
(no `schema_version`, no `content`, no `match_class`) to v2 with
`content=id` and `match_class="exact"`. Read path
(`emit-tasklist.py:_restore_mode`) detects v1 via missing `schema_version`
and triggers legacy rehydration when overlap < 50%.

---

## Resolver pipeline

Module: `scripts/tasklist_id_resolver.py` (mirrored to `.claude/scripts/`).

Pure stdlib. `resolve(label, contract_items, kind_hint=None) -> (step_id, match_class)`.

Layered matcher, deterministic precedence:

| Layer | Strategy | Example |
|---|---|---|
| 1 | **exact** | `label == contract.step_id` literally. `"step5_fix_loop"` → `"step5_fix_loop"`. |
| 2 | **normalized** | NFKD + lowercase + strip `↳ ` + collapse whitespace + `_`/`-` → space. `"↳ 0 Parse And Validate"` → `"0 parse and validate"` matches `normalized("0_parse_and_validate")`. |
| 3 | **strip-cmd** | After normalize, strip leading command prefix (`test-spec `, `build `, `scope `, ...). `"↳ test-spec 0_parse_and_validate"` → strip `test-spec ` → matches. |
| 4 | **strip-decimal** | `3.5 X` → also attempt `3 X`. `"↳ 3.5 CrossAI Sweep"` → `"3 crossai sweep"` matches `3_crossai_sweep`. |
| 5 | **substring** | Contract `step_id` appears as substring of normalized label. `"↳ test-spec 4_codegen — Spawn vg-test-codegen full subagent pass"` → contains `4_codegen`. |
| 6 | **slug** | Slugify label (drop non-alnum, snake_case) → token-equal to step_id. Final fallback before unresolved. |
| 7 | **unresolved** | `<unresolved>:` + 8-char sha256 hash. Deterministic. Will not shadow real step_ids. |

**Tie-breaks (when multiple layers yield candidates):**
1. Prefer `kind_hint` match if provided.
2. Prefer `kind=step` over `kind=group`.
3. Smaller Levenshtein distance from label-slug to step_id.
4. Still ambiguous → fail-closed (return unresolved).

**Status-precedence:** when multiple labels resolve to same step_id with
different statuses, `status_precedence(*statuses)` returns the highest:
`in_progress > completed > pending`. Active focus wins.

**Alias migration:** `STEP_ID_ALIASES: dict[str, list[str]]` versioned
table maps current canonical step_id → list of historical aliases. Used
by `emit-tasklist.py:_write_contract` merge logic when `filter-steps.py`
output renames a step across versions.

---

## Hook flow (snapshot write path)

```
AI TodoWrite call
       ↓
PostToolUse: vg-post-tool-use-todowrite.sh
       ↓
       ├── Read .vg/runs/{run_id}/tasklist-contract.json → contract_items[]
       ├── Load scripts/tasklist_id_resolver.py (canonical, then .claude/ mirror)
       ├── For each todo:
       │   ├── If todo.id matches a contract step_id → exact (skip resolver)
       │   ├── Else: resolver.resolve(todo.content, contract_items)
       │   └── Build {id: step_id, content: label, status, match_class}
       ├── Status-precedence dedup (same step_id from multiple labels)
       └── Pipe v2 payload to vg-tasklist-snapshot.py --write --run-id
              ↓
       vg-tasklist-snapshot.py
              ↓
       Validate schema, append provenance hash, atomic write tmp+replace
              ↓
       .vg/runs/{run_id}/.todowrite-snapshot.json
```

`.taskcreate-trace.jsonl` (TaskCreate/TaskUpdate path) stays raw with
backend `task_id` — preserves TaskUpdate join semantics. Resolution only
happens at the snapshot-write layer.

---

## Hook flow (restore path)

```
SessionStart:resume|compact → vg-session-start.sh
       ↓
       ├── Read .vg/active-runs/{session_id}.json → run_id
       └── Invoke emit-tasklist.py --restore-mode --run-id $RUN_ID
              ↓
       emit-tasklist.py:_restore_mode(run_id)
              ↓
       ├── Read .vg/runs/{run_id}/tasklist-contract.json → items[]
       ├── Read .vg/runs/{run_id}/.todowrite-snapshot.json → snapshot_overrides
       ├── Compute overlap_pct between snapshot keys and contract step_ids
       ├── If schema < 2 AND overlap < 50% → legacy rehydration:
       │   ├── Read .vg/runs/{run_id}/.taskcreate-trace.jsonl
       │   ├── Build {task_id → subject} from create actions
       │   ├── Run subjects through resolver
       │   ├── Build {step_id → status} (status-precedence on collision)
       │   └── Merge into snapshot_overrides
       ├── If overlap STILL < 50% → stderr [WARN] tasklist ID schema mismatch
       ├── For each contract item: status = snapshot_overrides.get(id) or "pending"
       ├── reorder_projection_by_status (in_progress surfaces in each group)
       └── Emit markdown table to stdout → vg-session-start appends to additionalContext
```

---

## Re-projection on non-slash prompts (B71b)

Symptom user reported: "khi prompt không phải lệnh, tasklist cũng không
được cập nhật".

`vg-user-prompt-submit.sh` non-slash branch now emits a 1-line digest into
the existing `<vg-flow-context>` stderr block:

```
[VG-TASKLIST] phase=7.16 cmd=vg:test-spec | 3 in_progress / 8 pending / 7 completed | overlap=86% | contract=a3f4b21c | snapshot=e7c9d33a | reason=snapshot-changed
```

Triggers (any one):
- `contract_hash` changed since last emit
- `snapshot_hash` changed since last emit
- `overlap_pct < 50%`
- `now - last_emit_ts > 1800s` (30 min)

Suppressed when:
- `len(prompt) < 10` (Y/N reply heuristic)
- `now - last_emit_ts < 60s` (rate limit)
- `VG_TASKLIST_REPROJECT_DISABLE=1` (escape hatch)
- Slash command prompt (the slash branch owns full projection)

Rate-limit state: `.vg/runs/{run_id}/.last-digest-emit.json` —
`{emit_ts, contract_hash, snap_hash}`.

---

## Contract merge on slash command rerun (B71c)

Symptom user reported: "khi chạy lại prompt lệnh, tasklist không cập nhật
đúng".

When `emit-tasklist.py:_write_contract` runs and an existing contract for
same `(command, phase)` is present:

| Old step state | New contract action |
|---|---|
| Common ID, snapshot status = X | Preserve X in new contract |
| Renamed via STEP_ID_ALIASES | Migrate status to canonical name + status_precedence |
| Removed step, snapshot status = completed | Drop + `[WARN]` stderr |
| Removed step, snapshot status = pending | Drop silently |
| Removed step, snapshot status = in_progress | Write `.vg/runs/{run_id}/.merge-orphan-blocker.json` + `[WARN]`. Caller slash preflight can prompt `/vg:override-resolve` |
| Added step (in new only) | Default pending |
| Different (command, phase) | No merge, fresh rewrite |

Records `merged_from_existing_at` + `merged_status_count` in the new
contract for audit.

---

## Troubleshooting

### Symptom: TodoWrite UI shows all-pending after resume

1. Check `.vg/runs/{run_id}/.todowrite-snapshot.json` exists.
2. If exists, check `schema_version`. Missing/`<2` → v1 legacy; need
   `.taskcreate-trace.jsonl` for rehydration.
3. Check overlap percentage manually:
   ```python
   contract = json.load(open(".vg/runs/{run_id}/tasklist-contract.json"))
   snap = json.load(open(".vg/runs/{run_id}/.todowrite-snapshot.json"))
   c_ids = {it["id"] for it in contract["projection_items"]}
   s_ids = {it["id"] for it in snap["items"]}
   print(f"overlap: {len(c_ids & s_ids)}/{len(c_ids)}")
   ```
4. If 0% overlap → run resolver dry-run:
   ```python
   from scripts.tasklist_id_resolver import resolve
   for it in snap["items"]:
       sid, mc = resolve(it["id"], contract["projection_items"])
       print(f"{it['id']!r} → {sid} ({mc})")
   ```
5. If many `unresolved` → AI is emitting labels that don't match any
   contract step. Check `STEP_ID_ALIASES` or extend resolver layers.

### Symptom: digest spamming chat

Set `VG_TASKLIST_REPROJECT_DISABLE=1` in shell env. Then file a bug — the
trigger logic should prevent this.

### Symptom: merge blocked by in_progress orphan

Read `.vg/runs/{run_id}/.merge-orphan-blocker.json`. The `in_progress_orphans`
list shows step_ids that were active in the previous contract but absent
in the new one. Resolve via `/vg:override-resolve` (or delete the marker
to force-continue).

---

## Cross-references

- B71a/B71d implementation: `commit d0dd692` (v4.63.0).
- B71a hotfix: `commit 58291a0` (v4.63.1).
- B71b+B71c: `commit 4fbf00b` (v4.63.2).
- Codex audit artifacts: `dev-phases/B71-tasklist-reliability/`.
- Resolver tests: `tests/test_batch71a_resolver.py` (32 tests).
- Snapshot v2 tests: `tests/test_batch71a_snapshot_v2_and_restore.py` (14 tests).
- Digest tests: `tests/test_batch71b_digest.py` (10 tests).
- Merge tests: `tests/test_batch71c_contract_merge.py` (8 tests).
- RTB fixture replay: `tests/test_batch71f_rtb_fixture_replay.py` (9 tests).
