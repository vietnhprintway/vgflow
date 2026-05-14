# Batch 25 — Pipeline order canonicalization (review → test-spec → test) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Canonicalize pipeline order across ALL docs + scripts. User confirmed v4.0 order: `specs → scope → blueprint → build → review → test-spec → test → accept`. Test-spec sits BETWEEN review + test (review writes RUNTIME-MAP, test-spec consumes it, test executes).

**Drift:** 17+ files reference 3 different orderings:
- 12 old 4-step (missing test-spec entirely): `build → review → test → accept`
- 5 wrong order: `build → test-spec → review → test → accept`
- 2 correct: `build → review → test-spec → test → accept`

**Working directory:** `main`.

---

## Conventions

- Mirror byte-identical to `.claude/`
- Sweep: `python -m pytest tests/ -q --tb=no -k "pipeline_order or canonical or batch_25"`
- Single Co-Authored-By trailer per commit
- Canonical string: `specs → scope → blueprint → build → review → test-spec → test → accept`

---

## Task 1: Fix phase-recon.py PIPELINE_STEPS order

**Files:**
- Modify: `.claude/scripts/phase-recon.py:45` PIPELINE_STEPS array
- Mirror canonical if exists
- Test: `tests/test_batch25_phase_recon_order.py`

**Step 1: Failing test**

```python
"""tests/test_batch25_phase_recon_order.py — Batch 25 phase-recon canonical order."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
RECON = REPO / ".claude" / "scripts" / "phase-recon.py"


def test_pipeline_steps_canonical():
    body = RECON.read_text(encoding="utf-8")
    # PIPELINE_STEPS line — canonical v4.0 order: review → test-spec → test
    import re
    m = re.search(r"PIPELINE_STEPS\s*=\s*\[([^\]]+)\]", body)
    assert m, "PIPELINE_STEPS list missing"
    steps_str = m.group(1)
    # Find positions of 'review' and 'test-spec'
    review_pos = steps_str.find('"review"')
    test_spec_pos = steps_str.find('"test-spec"')
    test_pos = re.search(r'"test"(?!-)', steps_str).start()  # 'test' not 'test-spec'
    assert review_pos > 0 and test_spec_pos > 0 and test_pos > 0
    assert review_pos < test_spec_pos < test_pos, (
        f"Canonical v4.0: review → test-spec → test. "
        f"Got review@{review_pos}, test-spec@{test_spec_pos}, test@{test_pos}"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `.claude/scripts/phase-recon.py:45`:

```python
PIPELINE_STEPS = ["specs", "scope", "blueprint", "build", "review", "test-spec", "test", "accept"]
```

Adjust any position-detection code that assumed test-spec before review (search for `test-spec` references throughout file, verify each makes sense with new order).

```bash
git commit -m "fix(recon): Batch 25 Task 1 — PIPELINE_STEPS canonical v4.0 order (review → test-spec → test)

User dogfood: '123 nơi vẫn giữ pipeline cũ. phải là test-specs nằm giữa
review và test chứ'. Confirms v4.0 canonical: review → test-spec → test.

phase-recon.py line 45 PIPELINE_STEPS list had test-spec BEFORE review.
review writes RUNTIME-MAP which test-spec consumes — order reversed in
v4.0 (post review/close.md:315 note). Recon position detection now
matches canonical.

Tests: tests/test_batch25_phase_recon_order.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Fix review.md gate semantics + pipeline string

**Files:**
- Modify: `commands/vg/review.md:447` invert gate (remove "review requires test-spec first")
- Modify: `commands/vg/review.md:453` pipeline arrow
- Mirror
- Test: `tests/test_batch25_review_gate_inverted.py`

**Step 1: Failing test**

```python
"""tests/test_batch25_review_gate_inverted.py — Batch 25 review gate semantics."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
REVIEW = REPO / "commands" / "vg" / "review.md"


def test_no_backwards_gate_text():
    body = REVIEW.read_text(encoding="utf-8")
    # Old wording (backwards in v4.0): "first full review requires /vg:test-spec"
    assert "first full review requires `/vg:test-spec`" not in body, (
        "Batch 25: remove 'review requires test-spec first' — v4.0 order is "
        "review WRITES RUNTIME-MAP, test-spec consumes it. Reversed dependency."
    )


def test_pipeline_arrow_correct():
    body = REVIEW.read_text(encoding="utf-8")
    # Pipeline arrow must be review → test-spec → test (v4.0)
    assert "build → review → test-spec → test → accept" in body or \
           "review → test-spec" in body, (
        "Batch 25: review.md pipeline arrow must show review → test-spec → test"
    )
    # Old wrong order must be gone
    assert "test-spec → **review**" not in body, (
        "Batch 25: old wrong arrow 'test-spec → review' must be removed"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/review.md:447`, replace:
```
12. **Post-build test-spec gate (v3.6.6)** — first full review requires `/vg:test-spec {phase}` artifacts ...
```
With:
```
12. **Review writes RUNTIME-MAP (v4.0)** — review produces `RUNTIME-MAP.json` + `GOAL-COVERAGE-MATRIX.md` that downstream `/vg:test-spec` consumes as lifecycle contract. Review does NOT depend on test-spec running first.
```

In `commands/vg/review.md:453`, replace:
```
Pipeline: specs → scope → blueprint → build → test-spec → **review** → test → accept
```
With:
```
Pipeline: specs → scope → blueprint → build → **review** → test-spec → test → accept
```

```bash
git commit -m "fix(review): Batch 25 Task 2 — invert review-vs-test-spec gate to v4.0 order

review.md:447 declared backwards dependency: 'first full review requires
test-spec artifacts'. v4.0 order is opposite: review writes RUNTIME-MAP
first, test-spec consumes it. Inverted gate text + fixed line 453
pipeline arrow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Fix phase.md + next.md + test-spec.md pipeline strings

**Files:**
- Modify: `commands/vg/phase.md:3, 33` (description + body)
- Modify: `commands/vg/next.md:20, 73, 84` (3 PIPELINE order lists)
- Modify: `commands/vg/test-spec.md:74` if mentions order
- Mirrors
- Test: `tests/test_batch25_other_files_canonical.py`

**Step 1: Failing test**

```python
"""tests/test_batch25_other_files_canonical.py — Batch 25 misc files canonical."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_phase_md_canonical():
    body = (REPO / "commands/vg/phase.md").read_text(encoding="utf-8")
    assert "build → review → test-spec → test → accept" in body, "phase.md must use v4.0 order"
    # Old wrong order must be gone (test-spec → review)
    assert "test-spec → review" not in body, "old wrong order 'test-spec → review' must be removed"


def test_next_md_canonical():
    body = (REPO / "commands/vg/next.md").read_text(encoding="utf-8")
    # Each occurrence of ordered step list must follow v4.0
    for m in re.finditer(r"\[['\"]specs['\"][^\]]+\]", body):
        steps_str = m.group(0)
        review_pos = steps_str.find("review")
        ts_pos = steps_str.find("test-spec")
        test_pos = re.search(r"['\"]test['\"](?!-)", steps_str).start() if re.search(r"['\"]test['\"](?!-)", steps_str) else -1
        if review_pos > 0 and ts_pos > 0 and test_pos > 0:
            assert review_pos < ts_pos < test_pos, (
                f"next.md step list wrong order: {steps_str[:200]}"
            )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/phase.md`:
- Line 3 description: `specs → scope → blueprint → build → review → test-spec → test → accept`
- Line 33 body: same canonical string

In `commands/vg/next.md` 3 occurrences (lines 20, 73, 84): replace `test-spec','review'` ordering with `review','test-spec'`.

In `commands/vg/test-spec.md:74`: align pipeline arrow.

```bash
git commit -m "fix(docs): Batch 25 Task 3 — phase.md + next.md + test-spec.md canonical order

5 occurrences across 3 files with test-spec BEFORE review (wrong v4.0).
Updated to canonical: build → review → test-spec → test → accept.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Insert test-spec into 12 old 4-step references

**Files:** 12 commands with old `build → review → test → accept`:
- amend.md, deploy.md, map.md, polish.md, prioritize.md, progress.md (4x), project.md, reapply-patches.md, roadmap.md, scope-review.md
- Mirrors
- Test: `tests/test_batch25_old_4step_upgraded.py`

**Step 1: Failing test**

```python
"""tests/test_batch25_old_4step_upgraded.py — Batch 25 old 4-step references upgraded."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_no_old_4step_remaining():
    """No command file should reference the old 4-step pipeline without test-spec."""
    bad_pattern = re.compile(r"build\s*→\s*review\s*→\s*test\s*→\s*accept")
    misses = []
    for p in (REPO / "commands" / "vg").glob("*.md"):
        body = p.read_text(encoding="utf-8")
        if bad_pattern.search(body):
            misses.append(p.name)
    assert not misses, (
        f"Batch 25: old 4-step pipeline (no test-spec) found in: {misses}. "
        f"Must insert test-spec: 'build → review → test-spec → test → accept'"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

For each of 12 files, replace `review → test → accept` with `review → test-spec → test → accept` (and same with arrow style variations: `→`, `->`, `>`).

Use sed/Edit per file. Be careful in cases where context is "skip review" (e.g. phase.md:218 already excluded the line by being scope = "Bỏ qua /vg:review" instruction — that's intentional, keep as is).

```bash
git commit -m "fix(docs): Batch 25 Task 4 — insert test-spec into 12 old 4-step pipeline references

amend, deploy, map, polish, prioritize, progress (4x), project,
reapply-patches, roadmap, scope-review.md all referenced old 4-step
order (build → review → test → accept) missing test-spec. Upgraded all
to canonical v4.0: build → review → test-spec → test → accept.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Test guard against future drift

**Files:**
- Create: `tests/test_pipeline_order_canonical.py` (single comprehensive test)
- (already created Task 1-4 specific tests but this consolidates)

**Step 1: Failing test (deliberately empty before write — test that this file exists + asserts canonical):**

The test:
```python
"""tests/test_pipeline_order_canonical.py — guard against pipeline order drift.

Canonical v4.0: specs → scope → blueprint → build → review → test-spec → test → accept
"""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

# Files exempt from canonical check (intentional drift — e.g. skip-review prose)
EXEMPT_LINES = [
    # phase.md:218 — "Bỏ qua /vg:review" prose (skip-review option, not canonical claim)
]


def test_no_4step_skip_test_spec():
    """No file in commands/vg/ should claim pipeline 'build → review → test → accept'
    (4-step missing test-spec). Use 5-step v4.0 canonical."""
    bad = re.compile(r"build\s*[→>-]+\s*review\s*[→>-]+\s*test\s*[→>-]+\s*accept(?!\s*[-→]+\s*test-spec)")
    misses = []
    for p in (REPO / "commands" / "vg").rglob("*.md"):
        try:
            body = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for ln, line in enumerate(body.splitlines(), 1):
            if bad.search(line) and "test-spec" not in line:
                # Exempt skip-review prose
                if "Bỏ qua /vg:review" in line or "skip-review" in line.lower():
                    continue
                misses.append(f"{p.relative_to(REPO)}:{ln}: {line.strip()[:120]}")
    assert not misses, (
        "Pipeline drift: old 4-step references must include test-spec:\n  " +
        "\n  ".join(misses)
    )


def test_no_wrong_order_test_spec_before_review():
    """No file should claim 'test-spec → review' or 'test-spec **→ review**' — that's
    v3.x backwards. v4.0 is 'review → test-spec'."""
    bad = re.compile(r"test-spec\s*[→>-]+\s*(?:\*\*)?review")
    misses = []
    for p in (REPO / "commands" / "vg").rglob("*.md"):
        try:
            body = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for ln, line in enumerate(body.splitlines(), 1):
            if bad.search(line):
                # Exempt scope-review or doc-history comments
                if "scope-review" in line or "v3.x" in line or "legacy" in line.lower():
                    continue
                misses.append(f"{p.relative_to(REPO)}:{ln}: {line.strip()[:120]}")
    assert not misses, (
        "Pipeline drift: 'test-spec → review' is v3.x backwards order. "
        "v4.0 canonical is 'review → test-spec':\n  " + "\n  ".join(misses)
    )


def test_phase_recon_canonical():
    """phase-recon.py PIPELINE_STEPS must have review before test-spec."""
    body = (REPO / ".claude/scripts/phase-recon.py").read_text(encoding="utf-8")
    m = re.search(r"PIPELINE_STEPS\s*=\s*\[([^\]]+)\]", body)
    assert m
    steps = m.group(1)
    review_pos = steps.find('"review"')
    ts_pos = steps.find('"test-spec"')
    assert 0 < review_pos < ts_pos, (
        f"phase-recon.py PIPELINE_STEPS must have review BEFORE test-spec. "
        f"Got: {steps}"
    )
```

**Step 2-6:** Test ships, runs against post-Tasks-1-4 state. All green.

```bash
git commit -m "test(pipeline): Batch 25 Task 5 — guard test against pipeline order drift

Single comprehensive test prevents future regression:
1. No 4-step references missing test-spec
2. No 'test-spec → review' (v3.x backwards)
3. phase-recon.py PIPELINE_STEPS has review before test-spec

Catches drift from any new doc/script that claims wrong pipeline order.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Release v4.28.0

Bump VERSION 4.27.1 → 4.28.0. CHANGELOG entry. Tag v4.28.0. Push. Re-sync ~/.vgflow. Codex mirror verify; regen if drift.

End of Batch 25. Estimated 2-3 hours.
