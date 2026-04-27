# Phase 16 — Task Fidelity Lock — SPECS

**Version:** v1 (lock 2026-04-27)
**Total decisions:** 6 (D-01..D-06)
**Source:** `DECISIONS.md` (this folder)
**Critical reality check:** PLAN.md hiện dùng heading format (`## Task 4: ...`), KHÔNG `<task id="4">` XML. SPECS adjusted để support cả 2 format trong transition.

---

## Existing infra audit (CRITICAL — đọc trước SPECS body)

| Component | Current state | P16 action |
|---|---|---|
| `scripts/pre-executor-check.py` (473 lines) | `extract_task_section(phase_dir, task_num, plan_file)` reads PLAN with regex `^#{2,3}\s+Task\s+0?{N}\b[:\s\-—]` (heading-based). Caps at 2000 lines per task. | EXTEND — add SHA256 hashing + .meta.json sidecar AFTER extraction; do NOT change extraction regex (backward compat). |
| `scripts/vg_completeness_check.py` (250 lines) | Has Check A (endpoint coverage) / B (design ref) / C (specs coverage) / D (orphan detection). | EXTEND — add Check E (body line cap) + Check F (cross-AI prose drift). |
| `commands/vg/_shared/crossai-invoke.md` | Existing skill body for cross-AI peer review. | EXTEND — add output contract section (D-05). |
| `commands/vg/build.md` step 8c | Phase 15 T11.2 already persists prompt to `.build/wave-N/executor-prompts/<task>.md`. | EXTEND — also persist `.meta.json` sidecar (D-01); add validator wire (D-06). |
| Current PLAN.md task block format | `## Task N: title` heading + free-form markdown body. NO YAML frontmatter convention exists. | NEW format `<task id="N">` with optional YAML frontmatter; gate with feature flag; backward-compat path mandatory. |

**Critical implication:** D-02 structured task schema is a NEW convention, not a fix to existing. Must:
1. Accept BOTH formats during transition (heading-based legacy + frontmatter new).
2. Validator emits WARN (not BLOCK) when heading-based detected for ≥1 release cycle.
3. Gate the new format adoption via vg.config flag `task_schema: legacy | structured | both` (default: `both`).

---

## D-01 — Task body SHA256 + `.meta.json` sidecar persist

### Input contract
- Task block extracted by `extract_task_section()` (existing function in `pre-executor-check.py`).
- For heading-based PLAN: block = lines from `## Task N:` heading to next `## Task M:` (or `## Wave M:`) or EOF.
- For new XML-tagged PLAN (D-02): block = `<task id="N">...</task>` content.

### Hashing function (canonical)
```python
def task_block_sha256(text: str) -> tuple[str, int, int]:
    """Whitespace-normalized SHA256.

    Normalization steps (deterministic, both formats):
      1. Strip trailing whitespace each line.
      2. Collapse runs of 2+ blank lines into single blank line.
      3. Strip leading + trailing blank lines.
      4. Encode UTF-8 NFC.
    Returns: (hex_digest, line_count_normalized, byte_count_normalized).
    """
    import hashlib, re, unicodedata
    lines = [ln.rstrip() for ln in text.splitlines()]
    normalized = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip('\n')
    normalized_nfc = unicodedata.normalize('NFC', normalized)
    blob = normalized_nfc.encode('utf-8')
    return (
        hashlib.sha256(blob).hexdigest(),
        len(normalized.splitlines()),
        len(blob),
    )
```

### Output contract
Persist alongside existing prompt body (Phase 15 T11.2 path):
```
${PHASE_DIR}/.build/wave-${N}/executor-prompts/${TASK_NUM}.md         # body
${PHASE_DIR}/.build/wave-${N}/executor-prompts/${TASK_NUM}.meta.json  # NEW
```

`.meta.json` shape:
```json
{
  "task_id": 3,
  "task_id_str": "T-3",
  "phase": "7.14.3",
  "wave": "wave-2",
  "source_path": "PLAN.md",
  "source_format": "heading|xml",
  "source_block_sha256": "abc123...",
  "source_block_line_count": 187,
  "source_block_byte_count": 8421,
  "extracted_at": "2026-04-27T10:00:00Z",
  "vg_version": "2.11.0",
  "extractor": "pre-executor-check.py:extract_task_section"
}
```

### Acceptance
- Run `/vg:build` on Phase 15 fixture; for each spawned task assert:
  - `<task>.md` exists
  - `<task>.meta.json` exists with all 9 keys
  - `source_block_sha256` recomputable from PLAN: re-extract → re-hash → matches.

`[T-1.1 implements; T-5.1 acceptance verifies]`

---

## D-02 — Structured task schema (XML wrapper + optional YAML frontmatter)

### Input contract — new PLAN task block format
```xml
<task id="3">
---
acceptance:
  - "POST /api/sites returns 201 + site.id"
  - "Validator allows 'example.com' rejects 'not a url'"
edge_cases:
  - "Domain with subdomain levels > 4 → reject"
  - "Concurrent POST same domain → 409"
decision_refs: ["P7.14.3.D-04", "P7.14.3.D-05"]
design_refs: ["sites-list.modal-add"]
body_max_lines: 200
---

# Description (markdown body)

Plain markdown body, ≤ body_max_lines.

<file-path>apps/web/src/sites/SitesList.tsx</file-path>
<contract-refs>POST /api/sites</contract-refs>
</task>
```

### Backward compat — both formats coexist
- `extract_task_section()` extended:
  ```python
  def extract_task_section(phase_dir, task_num, plan_file=None) -> dict:
      """Returns {body, format, frontmatter} where:
        - body: str (markdown body without frontmatter or XML tags)
        - format: 'xml' | 'heading'
        - frontmatter: dict | None (parsed YAML or None for heading format)
      """
  ```
- Detection priority:
  1. If PLAN contains `<task id="N">...</task>` for the requested N → use XML
  2. Else fallback to heading regex `^#{2,3}\s+Task\s+0?{N}\b` (existing behavior)

### Validator: `verify-task-schema.py`
- Scans PLAN.md for task blocks; classifies as xml/heading/mixed.
- Modes (vg.config.task_schema):
  - `legacy` (default in v2.11) → PASS heading; PASS xml; WARN mixed.
  - `structured` (opt-in) → BLOCK heading; PASS xml only.
  - `both` (default after v2.13 sunset) → WARN heading; PASS xml.
- When XML format used, frontmatter `acceptance:` (≥1 entry) is REQUIRED → BLOCK if absent.

### Acceptance
- Heading PLAN + `task_schema: legacy` → PASS
- XML PLAN with full frontmatter → PASS
- XML PLAN without `acceptance:` → BLOCK
- Mixed PLAN (some tasks XML, some heading) → WARN with per-task breakdown

`[T-2.1 implements parser extension; T-2.2 implements validator; T-5.1 verifies]`

---

## D-03 — PLAN body line BLOCK gate (Check E in vg_completeness_check.py)

### Input contract
- Per-task body line count (from D-02 extractor — `body` field length).
- Cap resolution:
  ```
  if task.frontmatter.body_max_lines:
      cap = task.frontmatter.body_max_lines
  elif phase.context.frontmatter.cross_ai_enriched == True:
      cap = 600
  else:
      cap = 250
  ```

### Validator: extend `vg_completeness_check.py` Check E
```python
def check_e_task_body_length(plan_files, context_md, args) -> list[Evidence]:
    """Check E (Phase 16 D-03): task body ≤ 250 lines (default), 600 if
    phase has cross_ai_enriched: true in CONTEXT frontmatter, or
    overridden per-task via body_max_lines frontmatter key.
    """
    enriched = _read_context_frontmatter_bool(context_md, 'cross_ai_enriched')
    default_cap = 600 if enriched else 250
    issues = []
    for plan in plan_files:
        for task in extract_all_tasks(plan):
            cap = task.frontmatter.get('body_max_lines') or default_cap
            actual = task.body.count('\n') + 1
            if actual > cap:
                issues.append(Evidence(
                    type='count_above_threshold',
                    message=f"Task {task.id} body {actual} lines > cap {cap}",
                    file=str(plan),
                    expected=cap,
                    actual=actual,
                    fix_hint=(
                        "Split task into smaller subtasks OR move prose to "
                        "<decision-refs> in CONTEXT.md (P16 D-05) OR override "
                        "via body_max_lines frontmatter."
                    ),
                ))
    return issues
```

### Override path
- CLI flag `--allow-long-task` propagates from `/vg:scope` and `/vg:blueprint` invocations.
- Logs override-debt as `kind=long-task`.

### Acceptance
- 280-line task body, default phase → BLOCK.
- Same task in `cross_ai_enriched: true` phase → PASS (under 600 cap).
- Same task with `body_max_lines: 350` frontmatter → PASS.
- 700-line task in enriched phase → BLOCK.

`[T-3.1 implements Check E; T-5.1 verifies]`

---

## D-04 — R4 budget conditional caps in pre-executor-check.py

### Input contract
- `pre-executor-check.py` reads `${PHASE_DIR}/CONTEXT.md` frontmatter for `cross_ai_enriched` flag.
- Returns CONTEXT_JSON with budget metadata field:
  ```json
  {
    "task_context": "...",
    "budget_mode": "default|enriched",
    "applied_caps": {"task_context": 300, "contract_context": 500, ...}
  }
  ```

### Cap table
| block | default | enriched |
|---|---|---|
| `task_context` | 300 | 600 |
| `contract_context` | 500 | 800 |
| `goals_context` | 200 | 400 |
| `sibling_context` | 400 | 400 (unchanged) |
| `downstream_callers` | 400 | 400 (unchanged) |
| `design_context` | 200 | 400 |
| `ui_map_subtree` | 80 | 200 |
| **TOTAL HARD MAX** | 2500 | 4000 |

### build.md integration
Phase 15 build.md step 8c R4 enforcement block reads `BUDGETS = {...}` literal — must be replaced with reading `applied_caps` from CONTEXT_JSON instead, so caps adapt without editing skill body.

### Logging
- `pre-executor-check.py` stderr: `ℹ R4 budget: enriched-mode caps applied (cross_ai_enriched=true) → task=600, contract=800, total_max=4000`
- build.md R4 check echoes the applied caps in the success line.

### Acceptance
- Same PLAN, 2 builds: enriched=false → cap 300 logged; enriched=true → cap 600 logged.
- Enriched phase task body 500 lines → no truncation, no R4 BLOCK.
- Enriched phase total prompt 3500 lines → PASS (under 4000); same prompt in default mode → BLOCK at 2500.

`[T-3.2 implements; T-5.1 verifies]`

---

## D-05 — Cross-AI enrichment contract

### Update `commands/vg/_shared/crossai-invoke.md`
Add new section "## Output contract for PLAN/CONTEXT enrichment (P16 D-05)":

```markdown
When cross-AI peer (Codex / Gemini) enriches PLAN.md or CONTEXT.md,
output MUST follow these rules:

1. **DO NOT inline prose blocks > 30 lines into a `<task>` body.**
   Long prose grows R4 budget pressure and gets truncated at the
   executor stage. Instead:
   a. Append a new decision block to CONTEXT.md (e.g., `### P{phase}.D-99: <title>`)
   b. Reference it from the task via `<context-refs>P{phase}.D-99</context-refs>`

2. **Edge cases → frontmatter `edge_cases:` array**, not body bullets:
   ```yaml
   edge_cases:
     - "New edge case discovered by cross-AI"
   ```

3. **Decision rationale → CONTEXT.md decision body**, not task body comment.

4. **Format flag**: cross-AI invoker MUST set `cross_ai_enriched: true`
   in CONTEXT.md frontmatter when enrichment changes any task body.
```

### Validator: `verify-crossai-output.py`
- Triggered by `/vg:scope --crossai` and `/vg:blueprint --crossai` AFTER cross-AI applies changes.
- Logic:
  1. `git diff HEAD~1 -- PLAN.md CONTEXT.md` → captures the enrichment diff.
  2. Per task in PLAN diff: count added body lines (`+` lines inside `<task>` body, excluding frontmatter changes).
  3. If any task body grew > 30 lines AND no corresponding `<context-refs>` ID added → BLOCK.
  4. If `cross_ai_enriched` flag missing in CONTEXT.md frontmatter → WARN.

### Acceptance
- Cross-AI run adds 50 prose lines to task body → BLOCK.
- Cross-AI run adds 50 lines but also adds 3 IDs to `<context-refs>` + content to CONTEXT.md → PASS.
- Cross-AI run only adds frontmatter `edge_cases:` array entries → PASS (no body growth).

`[T-4.1 updates skill body; T-4.2 implements validator; T-5.1 verifies]`

---

## D-06 — `verify-task-fidelity.py` — post-spawn 3-way hash audit

### Input contract
For each `(wave, task)` tuple under `${PHASE_DIR}/.build/wave-*/executor-prompts/`:
- `.meta.json` (D-01 sidecar) — expected hash + line_count
- `.md` (Phase 15 T11.2 prompt body) — what executor actually received
- PLAN.md task block re-extracted at validation time — current source of truth

### 3-way comparison
```python
def audit_task_fidelity(meta_path, prompt_path, plan_path) -> dict:
    meta = json.loads(meta_path.read_text())
    prompt_text = prompt_path.read_text()
    plan_block = extract_task_section(plan_path.parent, meta['task_id'])

    # Re-hash PLAN block
    plan_sha, plan_lines, _ = task_block_sha256(plan_block['body'])

    # Compare 1: PLAN now vs meta.json snapshot at spawn time
    # (catches: PLAN modified between spawn and audit — should not happen normally)
    plan_drift = (plan_sha != meta['source_block_sha256'])

    # Compare 2: prompt body line_count vs meta.json
    # (catches: orchestrator paraphrased / truncated body)
    prompt_lines = prompt_text.count('\n') + 1
    body_shortfall_pct = max(0, (meta['source_block_line_count'] - prompt_lines)) / meta['source_block_line_count']

    return {
        'plan_drift': plan_drift,
        'prompt_lines': prompt_lines,
        'expected_lines': meta['source_block_line_count'],
        'shortfall_pct': body_shortfall_pct,
        'block': plan_drift or body_shortfall_pct > 0.10,  # >10% missing
    }
```

### Tolerance
- Body shortfall ≤ 10% → PASS (whitespace + prompt-shell overhead).
- Body shortfall 10-30% → WARN.
- Body shortfall > 30% → BLOCK with full evidence.
- PLAN drift always WARN (PLAN should not change mid-build but it's recoverable).

### Wiring
Append to build.md step 8d (after Phase 15 D-12a injection audit, line ~1985):

```bash
TF_VAL="${REPO_ROOT}/.claude/scripts/validators/verify-task-fidelity.py"
WAVE_PROMPT_DIR="${PHASE_DIR}/.build/wave-${N}/executor-prompts"
if [ -x "$TF_VAL" ] && [ -d "$WAVE_PROMPT_DIR" ]; then
  ${PYTHON_BIN} "$TF_VAL" --phase "${PHASE_NUMBER}" \
      --prompts-dir "$WAVE_PROMPT_DIR" \
      > "${VG_TMP:-${PHASE_DIR}/.vg-tmp}/task-fidelity-w${N}.json" 2>&1 || true
  TFV=$(${PYTHON_BIN} -c "import json,sys; print(json.load(open(sys.argv[1])).get('verdict','SKIP'))" \
       "${VG_TMP:-${PHASE_DIR}/.vg-tmp}/task-fidelity-w${N}.json" 2>/dev/null)
  case "$TFV" in
    PASS|WARN) echo "✓ D-06 task fidelity audit: $TFV" ;;
    BLOCK)
      echo "⛔ D-06 task fidelity audit: BLOCK — orchestrator may have paraphrased/truncated task body" >&2
      echo "   See ${VG_TMP}/task-fidelity-w${N}.json for per-task shortfall breakdown" >&2
      if [[ ! "$ARGUMENTS" =~ --skip-task-fidelity-audit ]]; then exit 1; fi
      ;;
    *) echo "ℹ D-06 task fidelity audit: $TFV" ;;
  esac
fi
```

### Acceptance
- Test fixture: prompt body = task body verbatim → PASS (0% shortfall).
- Test fixture: prompt body = task body with 30% lines removed → BLOCK.
- Test fixture: prompt body = task body paraphrased same length, different content → BLOCK (hash mismatch when re-extracted).
- Test fixture: PLAN.md modified between spawn and audit → WARN with `plan_drift: true`.

`[T-4.3 implements; T-5.1 verifies]`

---

## Cross-decision dependencies

```
D-01 SHA256 + meta.json
   │ provides hash for D-06 audit
   ▼
D-02 task schema (xml + frontmatter)  ←─── D-03 body cap reads frontmatter body_max_lines
   │ provides parsing path
   ▼
D-04 R4 conditional cap (uses CONTEXT cross_ai_enriched flag)
   │
   └─── D-05 cross-AI contract enforces flag + structured edits
                                      │
                                      ▼
D-06 task-fidelity audit reads D-01 meta.json
```

- D-01 + D-02 must ship in same wave (extractor knows about both formats).
- D-03 depends on D-02 (frontmatter parsing).
- D-04 + D-05 work together (both read `cross_ai_enriched` flag).
- D-06 final defense — depends on D-01.

---

## Out-of-spec follow-ups

- Auto-rewrite PLAN when D-03 BLOCK fires — Phase 18+ candidate.
- Sub-agent self-verify (sub-agent reads PLAN directly, cross-checks against received prompt) — orthogonal architecture; defer.
- Hash chain — meta.json HMAC signed by VG_HMAC_KEY so tampering detected — defer; current trust model is local dev OK.
- Task schema v2 (e.g., add `priority:`, `risk:` to frontmatter) — track Phase 19+.
