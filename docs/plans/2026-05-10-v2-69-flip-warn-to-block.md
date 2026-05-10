# v2.69.0 — Flip B1+B4+C2 advisory gates to blocking

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Tighten 3 advisory gates introduced in v2.66.0-v2.68.0 to hard-blocking. Each flip ships with `--skip-{name}` escape hatch + override-debt logging. Add lifecycle telemetry counters for verdict distribution.

**Architecture:** B1 (per-task spec reviewer, v2.66.0) + B4 (in-build final reviewer, v2.66.1) + C2 (QA-Checker meta-agent, v2.68.0) each flip from `severity: warn` to hard contract entry. Each gets parser flag + override-debt logging matching v2.65.0 deepscan / v2.66.0 lenient-prereqs / v2.59.x skip-pre-test precedents. Telemetry events emit `{gate}.verdict_distribution` counters for future tuning.

**Tech Stack:** Markdown (commands), Python 3 (tests + telemetry hook), Bash (parser).

---

## Context

v2.66.0 B1 + v2.66.1 B4 + v2.68.0 C2 all shipped with severity=warn. Plan for v2.69.0 (per CHANGELOG): flip to block "after telemetry calibration." Real telemetry samples don't exist yet (gates only landed in last 2 releases). Decision: flip with safe defaults (escape hatches) + retroactively collect telemetry for future tuning.

**Targets located:**
- B1: `commands/vg/build.md:103-104` (already in must_touch_markers as severity=warn)
- B4: `commands/vg/_shared/build/close.md:125-166` (marker doc only; NOT in build.md frontmatter — must add entry)
- C2: `commands/vg/review.md:6234-6252` (Phase 3d.5; marker NOT in review.md frontmatter — must add entry)
- Flag parse pattern: `commands/vg/review.md:600-628` (case loop precedent)
- Override debt: `scripts/validators/override-debt-balance.py` + `log_override_debt()` helper

VERSION baseline: 2.68.0. Bump to 2.69.0.

---

## Task 1 (B1): Flip + escape hatch

**Files:**
- Modify: `commands/vg/build.md:103-104` (remove `severity: warn` from `5_1_spec_compliance_review` entry)
- Modify: `commands/vg/build.md` argument-hint (add `[--skip-spec-review]`)
- Modify: `commands/vg/build.md` `forbidden_without_override:` list (add `--skip-spec-review`)
- Modify: `commands/vg/_shared/build/preflight.md` parse loop (add `--skip-spec-review` case + log_override_debt)
- Modify: `commands/vg/_shared/build/post-execution-overview.md:1041-1067` (skip spawn when SKIP_SPEC_REVIEW=1)
- Mirror all
- Test: `tests/test_v2_69_b1_flip.py` (NEW)

**Step 1: Failing test**

```python
"""v2.69.0 T1 — B1 spec-reviewer flip warn→block."""
import re
from pathlib import Path
import yaml


def test_b1_marker_no_longer_warn():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    assert m, "frontmatter not found"
    fm = yaml.safe_load(m.group(1))
    
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    spec_marker = next(
        (m for m in markers if isinstance(m, dict) and m.get("name") == "5_1_spec_compliance_review"),
        None
    )
    # After flip: should be string (hard) OR dict without severity:warn
    assert spec_marker is None or spec_marker.get("severity") != "warn", \
        f"5_1_spec_compliance_review still severity=warn (v2.69.0 must flip): {spec_marker}"


def test_b1_marker_in_required_unless_flag_form():
    """After flip: marker should be required_unless_flag --skip-spec-review (not severity:warn)."""
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    
    # Either string-form (hard required) OR dict with required_unless_flag
    spec_entry = next(
        (m for m in markers if (isinstance(m, str) and "5_1_spec_compliance_review" in m) or
         (isinstance(m, dict) and m.get("name") == "5_1_spec_compliance_review")),
        None
    )
    assert spec_entry is not None, "marker missing entirely"


def test_skip_spec_review_flag_documented():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    assert "--skip-spec-review" in body, "v2.69.0 must add --skip-spec-review escape hatch"


def test_skip_spec_review_in_forbidden_without_override():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    m = re.search(r"forbidden_without_override:.*?(?=\n[a-z]|\Z)", body, re.DOTALL)
    assert m and "--skip-spec-review" in m.group(0), \
        "--skip-spec-review must be in forbidden_without_override (debt-register tracked)"


def test_preflight_parses_skip_spec_review_flag():
    body = Path("commands/vg/_shared/build/preflight.md").read_text(encoding="utf-8")
    assert "--skip-spec-review" in body, "preflight parse loop must handle --skip-spec-review"
    # Should set SKIP_SPEC_REVIEW=1 + export
    assert re.search(r"SKIP_SPEC_REVIEW", body), "must set SKIP_SPEC_REVIEW env var"


def test_post_execution_skips_spec_reviewer_when_flag_set():
    body = Path("commands/vg/_shared/build/post-execution-overview.md").read_text(encoding="utf-8")
    # STEP 5.1 region must check SKIP_SPEC_REVIEW
    step5_1 = re.search(r"STEP 5\.1.*?(?=STEP 5\.|STEP 6|\Z)", body, re.DOTALL)
    assert step5_1, "STEP 5.1 section not found"
    assert "SKIP_SPEC_REVIEW" in step5_1.group(0), \
        "STEP 5.1 must short-circuit when SKIP_SPEC_REVIEW=1"
```

**Step 2: FAIL**

**Step 3: Implement**

Edit `commands/vg/build.md` line 103-104 — change from:
```yaml
- name: "5_1_spec_compliance_review"
  severity: "warn"
```
To:
```yaml
- name: "5_1_spec_compliance_review"
  required_unless_flag: "--skip-spec-review"
```

Add `--skip-spec-review` to:
- argument-hint (existing line)
- `forbidden_without_override:` list

Add to `commands/vg/_shared/build/preflight.md` parse loop:
```bash
--skip-spec-review)
  SKIP_SPEC_REVIEW=1
  type -t log_override_debt >/dev/null 2>&1 && \
    log_override_debt "skip-spec-review" "${PHASE_NUMBER:-unknown}" "build.spec_review" "${PHASE_DIR:-.}"
  ;;
```
+ export SKIP_SPEC_REVIEW

Edit `commands/vg/_shared/build/post-execution-overview.md:1041-1067` (STEP 5.1) — wrap spawn loop:
```bash
if [ "${SKIP_SPEC_REVIEW:-0}" = "1" ]; then
  echo "▸ STEP 5.1: --skip-spec-review set, skipping per-task spec compliance review (debt-tracked)" >&2
  # Still touch marker so contract validator sees it
  mkdir -p "${PHASE_DIR}/.step-markers"
  touch "${PHASE_DIR}/.step-markers/5_1_spec_compliance_review.done"
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step build 5_1_spec_compliance_review 2>/dev/null || true
else
  # ... existing per-task spawn loop ...
fi
```

**Step 4-5:** Mirror, test, commit.

```bash
git commit -m "feat(build): B1 spec-reviewer flip warn→block + --skip-spec-review escape (v2.69.0)"
```

---

## Task 2 (B4): Add marker to frontmatter + flip + escape

**Files:**
- Modify: `commands/vg/build.md` `must_touch_markers` (ADD `7_1_5_final_review` entry — wasn't there before)
- Modify: `commands/vg/build.md` argument-hint (add `[--skip-final-review]`)
- Modify: `commands/vg/build.md` `forbidden_without_override:` (add `--skip-final-review`)
- Modify: `commands/vg/_shared/build/preflight.md` parse loop (add `--skip-final-review`)
- Modify: `commands/vg/_shared/build/close.md:125-162` (skip spawn when flag set)
- Mirror all
- Test: `tests/test_v2_69_b4_flip.py` (NEW)

**Step 1: Failing test**

```python
"""v2.69.0 T2 — B4 final-reviewer flip + add to frontmatter."""
import re, yaml
from pathlib import Path


def test_b4_marker_in_frontmatter():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    
    final_entry = next(
        (m for m in markers if (isinstance(m, str) and "7_1_5_final_review" in m) or
         (isinstance(m, dict) and m.get("name") == "7_1_5_final_review")),
        None
    )
    assert final_entry is not None, "v2.69.0 must add 7_1_5_final_review to must_touch_markers"


def test_b4_marker_required_unless_flag():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    final_entry = next(
        (m for m in markers if isinstance(m, dict) and m.get("name") == "7_1_5_final_review"),
        None
    )
    if final_entry is None:
        # accept string-form (hard required, no escape) — also valid
        return
    assert final_entry.get("severity") != "warn", "7_1_5_final_review must NOT be warn"


def test_skip_final_review_flag():
    body = Path("commands/vg/build.md").read_text(encoding="utf-8")
    assert "--skip-final-review" in body
    
    # Must be in forbidden_without_override
    m = re.search(r"forbidden_without_override:.*?(?=\n[a-z]|\Z)", body, re.DOTALL)
    assert m and "--skip-final-review" in m.group(0)


def test_close_md_short_circuits_when_skipped():
    body = Path("commands/vg/_shared/build/close.md").read_text(encoding="utf-8")
    step7_1_5 = re.search(r"7\.1\.5.*?(?=7\.2|STEP 7\.2|\Z)", body, re.DOTALL)
    assert step7_1_5
    assert "SKIP_FINAL_REVIEW" in step7_1_5.group(0)
```

**Step 2: FAIL**

**Step 3: Implement**

ADD to `commands/vg/build.md` `must_touch_markers` (after `7_postmortem_sanity` or similar terminal entry):
```yaml
- name: "7_1_5_final_review"
  required_unless_flag: "--skip-final-review"
```

Add `--skip-final-review` to argument-hint + forbidden_without_override.

Add to preflight.md parse loop:
```bash
--skip-final-review)
  SKIP_FINAL_REVIEW=1
  type -t log_override_debt >/dev/null 2>&1 && \
    log_override_debt "skip-final-review" "${PHASE_NUMBER:-unknown}" "build.final_review" "${PHASE_DIR:-.}"
  ;;
```

Edit `commands/vg/_shared/build/close.md:125-162` STEP 7.1.5:
```bash
if [ "${SKIP_FINAL_REVIEW:-0}" = "1" ]; then
  echo "▸ STEP 7.1.5: --skip-final-review set (debt-tracked); skipping cumulative review" >&2
  mkdir -p "${PHASE_DIR}/.step-markers"
  touch "${PHASE_DIR}/.step-markers/7_1_5_final_review.done"
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step build 7_1_5_final_review 2>/dev/null || true
else
  # existing spawn block ...
fi
```

**Step 4-5:** Mirror, test, commit.

```bash
git commit -m "feat(build): B4 final-reviewer add-to-frontmatter + flip + --skip-final-review (v2.69.0)"
```

---

## Task 3 (C2): Add marker to frontmatter + flip + escape

**Files:**
- Modify: `commands/vg/review.md` `must_touch_markers` (ADD `phase3d_5_qa_checker` entry)
- Modify: `commands/vg/review.md` argument-hint (add `[--skip-qa-check]`)
- Modify: `commands/vg/review.md` `forbidden_without_override:` (add `--skip-qa-check`)
- Modify: `commands/vg/review.md` parse loop (around line 600-628 — add case)
- Modify: `commands/vg/review.md:6234-6252` Phase 3d.5 (skip spawn when flag set)
- Mirror
- Test: `tests/test_v2_69_c2_flip.py` (NEW)

**Step 1: Failing test**

```python
"""v2.69.0 T3 — C2 QA-Checker flip + add to frontmatter."""
import re, yaml
from pathlib import Path


def test_c2_marker_in_frontmatter():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    
    qa_entry = next(
        (m for m in markers if (isinstance(m, str) and "phase3d_5_qa_checker" in m) or
         (isinstance(m, dict) and m.get("name") == "phase3d_5_qa_checker")),
        None
    )
    assert qa_entry is not None, "v2.69.0 must add phase3d_5_qa_checker to must_touch_markers"


def test_c2_marker_required_unless_flag():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", body, re.DOTALL)
    fm = yaml.safe_load(m.group(1))
    markers = fm.get("runtime_contract", {}).get("must_touch_markers", [])
    qa_entry = next(
        (m for m in markers if isinstance(m, dict) and m.get("name") == "phase3d_5_qa_checker"),
        None
    )
    if qa_entry is None:
        return
    assert qa_entry.get("severity") != "warn"


def test_skip_qa_check_flag():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    assert "--skip-qa-check" in body


def test_review_parse_loop_handles_skip_qa_check():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    # Find parse loop region
    parse_region = re.search(r"for tok in.*?esac.*?done", body, re.DOTALL)
    assert parse_region
    assert "--skip-qa-check" in parse_region.group(0)


def test_phase3d_5_short_circuits_when_skipped():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    p3d5 = re.search(r"3d\.5.*?(?=3e|## |\Z)", body, re.DOTALL)
    assert p3d5
    assert "SKIP_QA_CHECK" in p3d5.group(0)
```

**Step 2: FAIL**

**Step 3: Implement**

ADD to `commands/vg/review.md` frontmatter `must_touch_markers`:
```yaml
- name: "phase3d_5_qa_checker"
  required_unless_flag: "--skip-qa-check"
```

Add `--skip-qa-check` to argument-hint + forbidden_without_override.

Edit parse loop (around line 600-628):
```bash
--skip-qa-check)
  SKIP_QA_CHECK=1
  type -t log_override_debt >/dev/null 2>&1 && \
    log_override_debt "skip-qa-check" "${PHASE_NUMBER:-unknown}" "review.qa_check" "${PHASE_DIR:-.}"
  ;;
```
+ export SKIP_QA_CHECK

Edit Phase 3d.5 region — wrap spawn:
```bash
if [ "${SKIP_QA_CHECK:-0}" = "1" ]; then
  echo "▸ Phase 3d.5: --skip-qa-check set (debt-tracked); skipping QA-Checker meta-verification" >&2
  mkdir -p "${PHASE_DIR}/.step-markers"
  touch "${PHASE_DIR}/.step-markers/phase3d_5_qa_checker.done"
  "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step review phase3d_5_qa_checker 2>/dev/null || true
else
  # existing Agent spawn ...
fi
```

**Step 4-5:** Mirror, test, commit.

```bash
git commit -m "feat(review): C2 QA-Checker flip + add-to-frontmatter + --skip-qa-check (v2.69.0)"
```

---

## Task 4: Verdict telemetry counters

**Files:**
- Modify: `.claude/agents/vg-build-spec-reviewer/SKILL.md` (emit `b1.verdict` event with PASS/FAIL count)
- Modify: `.claude/agents/vg-build-final-reviewer/SKILL.md` (emit `b4.verdict`)
- Modify: `.claude/agents/vg-review-qa-checker/SKILL.md` (emit `c2.verdict`)
- Test: `tests/test_v2_69_verdict_telemetry.py` (NEW)

**Step 1: Failing test**

```python
"""v2.69.0 T4 — Verdict telemetry counters."""
from pathlib import Path
import re


def test_spec_reviewer_emits_verdict_telemetry():
    body = Path(".claude/agents/vg-build-spec-reviewer/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"b1\.verdict|spec_review\.verdict|emit-event.*verdict", body, re.IGNORECASE), \
        "B1 SKILL.md must instruct verdict telemetry emission"


def test_final_reviewer_emits_verdict_telemetry():
    body = Path(".claude/agents/vg-build-final-reviewer/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"b4\.verdict|final_review\.verdict|emit-event.*verdict", body, re.IGNORECASE)


def test_qa_checker_emits_verdict_telemetry():
    body = Path(".claude/agents/vg-review-qa-checker/SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"c2\.verdict|qa_check\.verdict|emit-event.*verdict", body, re.IGNORECASE)
```

**Step 2: FAIL**

**Step 3: Implement** — append to each agent SKILL.md a "Telemetry emission" section:

```markdown
## Telemetry emission (v2.69.0)

After computing verdict, emit telemetry event for distribution tracking:

\`\`\`bash
${PYTHON_BIN:-python3} .claude/scripts/vg-orchestrator emit-event \
  "{gate_id}.verdict" --actor "{actor}" --outcome "${VERDICT}" \
  --metadata "{\"phase\":\"${PHASE_NUMBER}\",\"verdict\":\"${VERDICT}\",\"confidence\":\"${CONFIDENCE:-medium}\"}"
\`\`\`

Where `{gate_id}` per agent: `b1.verdict` (spec-reviewer), `b4.verdict` (final-reviewer), `c2.verdict` (qa-checker). Operators query events.db to see PASS/PARTIAL/FAIL distribution + tune escape-hatch usage.
```

**Step 4-5:** Test, commit (no mirror — `.claude/agents/` is canonical-only).

```bash
git commit -m "feat(agents): v2.69.0 verdict telemetry counters for B1/B4/C2"
```

---

## Task 5: VERSION + CHANGELOG + tag + push

**Files:** VERSION (2.68.0→2.69.0) + package.json + CHANGELOG (prepend v2.69.0).

**CHANGELOG entry:**

```markdown
## v2.69.0 — Flip B1+B4+C2 advisory gates to blocking (2026-05-10)

### Behavioral changes (3 gates flip warn→block)
- **B1 (v2.66.0):** `5_1_spec_compliance_review` per-task spec reviewer marker now `required_unless_flag: "--skip-spec-review"` (was `severity: warn`). Build BLOCKs when reviewer FAILs and flag absent.
- **B4 (v2.66.1):** `7_1_5_final_review` cumulative reviewer marker added to build.md `must_touch_markers` (was documented only) with `required_unless_flag: "--skip-final-review"`. Build BLOCKs when reviewer FAILs and flag absent.
- **C2 (v2.68.0):** `phase3d_5_qa_checker` QA-Checker meta-agent marker added to review.md `must_touch_markers` with `required_unless_flag: "--skip-qa-check"`. Review BLOCKs when QA-Checker FAILs and flag absent.

### Escape hatches (each pairs with --override-reason)
- **`--skip-spec-review`** (build): Skips B1 per-task spec compliance review. Logs override-debt entry via `log_override_debt`. Marker still touched to satisfy contract validator.
- **`--skip-final-review`** (build): Skips B4 cumulative review. Same debt-logging.
- **`--skip-qa-check`** (review): Skips C2 QA-Checker meta-verification. Same debt-logging.
- All 3 flags added to `forbidden_without_override:` list — must pair with `--override-reason=<text>` per debt-register protocol.

### Telemetry
Each gate now emits `{b1,b4,c2}.verdict` event after verdict computation with metadata `{phase, verdict, confidence}`. Operators query events.db for PASS/PARTIAL/FAIL distribution + escape-hatch usage rate. Future tuning data-driven.

### Test coverage
**18+ new tests across 4 suites.** All pass.

### Migration
- **BREAKING:** Phases that hit B1/B4/C2 FAIL verdicts will now block instead of advise. To preserve v2.68.x behavior temporarily: pass appropriate `--skip-{gate}` flag + `--override-reason=<text>`.
- Default escape-hatch usage tracks via override-debt events — operators see exactly which gates are routinely skipped (signal for actual fix vs systemic exemption).

## v2.68.0 — C-tier strict review research adoptions (2026-05-10)
```

Steps:
1. Bump VERSION + package.json
2. Prepend CHANGELOG
3. Commit: `release: v2.69.0 — flip B1+B4+C2 warn→block + escape hatches`
4. Tag `v2.69.0`
5. Push origin main + tag
6. `gh release create v2.69.0`

---

## Verification

- `git log --oneline | head -8` shows 5 commits (4 tasks + release)
- `cat VERSION` = `2.69.0`
- 18+ new tests pass
- All v2.65.0-v2.68.0 tests still pass

---

## Execution mode

Subagent-driven development. Bundle batches:
- **Batch A:** T1 (B1 flip — already-in-frontmatter case, simplest)
- **Batch B:** T2 + T3 (B4 + C2 — both add-to-frontmatter, similar pattern)
- **Batch C:** T4 (telemetry — 3 SKILL.md edits, no mirror)
- **Release:** Task 5

Each task = own commit.
