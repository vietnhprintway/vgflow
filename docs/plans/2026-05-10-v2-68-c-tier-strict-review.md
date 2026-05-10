# v2.68.0 — C-tier Strict Review Research Adoptions

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Ship 6 strict-review research adoptions (C1-C6) from external repo survey: Evidence Gate (obra/superpowers), QA-Checker meta-agent (CodeAgent paper), Hybrid gate, Discourse phase (open-code-review AGREE/CHALLENGE/CONNECT/SURFACE), Sandbox runtime, Min-budget floor.

**Architecture:** C1 retrofits missing evidence-emit on existing validators. C2 adds new meta-agent invoked after Phase 3 fix-loop. C3 hybridizes pure-deterministic runtime-evidence.py with LLM fallback. C4 replaces voting-aggregator with discourse-move protocol. C5 extends mkdtemp sandbox pattern from CrossAI runners to build executor. C6 adds token budget tracker + overrun abort.

**Tech Stack:** Python 3 (validators + meta-agent + budget tracker + tests), Markdown (commands + agent SKILL.md).

**Issues:** No user-reported issues. Pure research-driven hardening.

---

## Context

External-repo research from earlier session identified 7 patterns. Top 6 chosen for v2.68.0:
- **C1 Evidence Gate** — every gate writes signed JSON evidence (machine-readable, audit trail)
- **C2 QA-Checker** — meta-agent verifies "fix matches issue claim" not just tests pass
- **C3 Hybrid gate** — combine deterministic check + LLM judgment
- **C4 Discourse phase** — 3-reviewer debate (AGREE/CHALLENGE/CONNECT/SURFACE moves) before verdict
- **C5 Sandbox runtime** — throwaway tempdir per task
- **C6 Min-budget floor** — abort orchestrator if token cost exceeds floor

**Targets located** (from research):
- C1: signed HMAC wrapper at `scripts/vg-orchestrator-emit-evidence-signed.py`. Validators emitting evidence: `verify-fe-be-call-graph.py`, `verify-spec-drift.py`. Missing: `runtime-evidence.py`, `verify-workflow-evidence.py`, `verify-read-evidence.py`.
- C2: Phase 3d re-verify region in `commands/vg/review.md:6205-6219`. Slot QA-Checker after fix agents return.
- C3: `scripts/validators/runtime-evidence.py:1-80` — pure deterministic, hybridize.
- C4: `scripts/crossai-normalize-results.py:188-210` — voting verdict logic. Replace with discourse.
- C5: `scripts/crossai-runner.py:100-140` mkdtemp pattern. Extend to build task executor.
- C6: `scripts/vg-orchestrator/__main__.py` emit-event subcommand at line ~18-30. Hook budget tracker.

VERSION baseline: 2.67.0. Bump to 2.68.0.

---

## Task 1 (C1): Evidence Gate retrofit

**Files:**
- Modify: `scripts/validators/runtime-evidence.py` (add evidence write)
- Modify: `scripts/validators/verify-workflow-evidence.py` (add evidence write)
- Modify: `scripts/validators/verify-read-evidence.py` (add evidence write)
- Mirror each
- Test: `tests/test_c1_evidence_gate_coverage.py` (NEW — list-driven coverage check)

**Step 1: Failing test**

```python
"""v2.68.0 C1 — Evidence Gate retrofit coverage."""
import re
from pathlib import Path
import pytest


GATES_REQUIRING_EVIDENCE = [
    ("scripts/validators/verify-fe-be-call-graph.py", "fe-be-call-graph"),
    ("scripts/validators/verify-spec-drift.py", "spec-drift"),
    ("scripts/validators/verify-contract-shape.py", "contract-shape"),
    ("scripts/validators/runtime-evidence.py", "runtime-evidence"),
    ("scripts/validators/verify-workflow-evidence.py", "workflow-evidence"),
    ("scripts/validators/verify-read-evidence.py", "read-evidence"),
]


@pytest.mark.parametrize("validator_path,gate_id", GATES_REQUIRING_EVIDENCE)
def test_validator_writes_evidence_json(validator_path, gate_id):
    """Each L-gate validator must write structured evidence JSON to .evidence/<gate_id>.json."""
    p = Path(validator_path)
    if not p.exists():
        pytest.skip(f"{validator_path} not found")
    src = p.read_text(encoding="utf-8")
    # Must reference .evidence/ path or evidence-signed.py emit
    assert re.search(r"\.evidence/|emit-evidence-signed|emit_evidence_signed", src), \
        f"{validator_path}: missing .evidence/ JSON write"


@pytest.mark.parametrize("validator_path,gate_id", GATES_REQUIRING_EVIDENCE)
def test_evidence_includes_required_fields(validator_path, gate_id):
    """Evidence JSON must include verdict + findings + ts."""
    p = Path(validator_path)
    if not p.exists():
        pytest.skip(f"{validator_path} not found")
    src = p.read_text(encoding="utf-8")
    # Must reference verdict + ts (or use Output dataclass which has these)
    has_verdict = "verdict" in src.lower()
    has_ts = re.search(r"datetime|isoformat|timestamp|signed_at", src, re.IGNORECASE)
    assert has_verdict, f"{validator_path}: missing verdict field"
    assert has_ts, f"{validator_path}: missing ts/timestamp field"
```

**Step 2: FAIL** (3 validators don't reference `.evidence/`)

**Step 3: Implement**

For each missing validator (`runtime-evidence.py`, `verify-workflow-evidence.py`, `verify-read-evidence.py`):

1. Read existing main flow
2. After verdict computed, add:

```python
import json
import datetime
from pathlib import Path

def _write_evidence(phase_dir: Path, gate_id: str, verdict: str, findings: list[dict]):
    evidence_dir = phase_dir / ".evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate_id": gate_id,
        "verdict": verdict,
        "findings": findings,
        "signed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "validator": Path(__file__).name,
    }
    out_path = evidence_dir / f"{gate_id}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
```

3. Wire `_write_evidence(phase_dir, "<gate_id>", verdict, findings)` at end of main.

**Step 4-5:** Mirror each, test, single commit.

```bash
git commit -m "feat(validators): C1 evidence gate retrofit for runtime/workflow/read-evidence (v2.68.0)"
```

---

## Task 2 (C2): QA-Checker meta-agent

**Files:**
- Create: `.claude/agents/vg-review-qa-checker/SKILL.md` (NEW)
- Modify: `commands/vg/review.md:6205-6219` (Phase 3d tail — spawn QA-Checker after fix agents)
- Mirror review.md
- Test: `tests/test_c2_qa_checker.py` (NEW)

**Step 1: Failing test**

```python
"""v2.68.0 C2 — QA-Checker meta-agent."""
from pathlib import Path
import re


def test_qa_checker_agent_exists():
    p = Path(".claude/agents/vg-review-qa-checker/SKILL.md")
    assert p.exists(), "vg-review-qa-checker agent definition missing (v2.68.0 C2)"
    body = p.read_text(encoding="utf-8")
    # Must reference issue traceability (not just spec/code match)
    assert re.search(r"issue.{0,80}(?:claim|trace|address|original)", body, re.IGNORECASE | re.DOTALL), \
        "QA-Checker must verify fix addresses original issue claim"
    # Must mention fix commit + finding linkage
    assert "commit" in body.lower() and "finding" in body.lower()


def test_review_phase3d_spawns_qa_checker():
    body = Path("commands/vg/review.md").read_text(encoding="utf-8")
    # Phase 3d region must reference QA-Checker spawn
    assert "vg-review-qa-checker" in body, \
        "review.md Phase 3d must spawn QA-Checker after fix agents return (v2.68.0 C2)"


def test_qa_checker_returns_pass_partial_fail():
    p = Path(".claude/agents/vg-review-qa-checker/SKILL.md")
    body = p.read_text(encoding="utf-8")
    for v in ["PASS", "PARTIAL", "FAIL"]:
        assert v in body, f"QA-Checker must define {v} verdict"
```

**Step 2: FAIL**

**Step 3: Create agent + wire**

Create `.claude/agents/vg-review-qa-checker/SKILL.md`:

```markdown
---
name: vg-review-qa-checker
description: |
  Meta-agent verifying fix commits actually address original issue claims.
  Runs after Phase 3 fix-loop (after fix agents return). Reads original
  finding text + fix commit diff + fix commit message, evaluates whether
  the fix matches the issue, not just makes tests pass. Verdict:
  PASS|PARTIAL|FAIL. Severity=warn in v2.68.0 (advisory), will flip to
  block in v2.69.0 after telemetry.
allowed-tools:
  - Read
  - Bash
  - Grep
---

# vg-review-qa-checker

You are a meta-agent for v2.68.0 C2. Your scope: verify each fix commit
ACTUALLY addresses the original review finding it was meant to fix, not
just makes tests pass.

## Input

- `phase_dir` — phase directory containing REVIEW-FINDINGS.json + fix-loop history
- `fix_commits` — list of `(finding_id, commit_sha, finding_text)` tuples produced by Phase 3 fix-loop

## Job

For each fix commit:

1. Read original finding text (from REVIEW-FINDINGS.json by finding_id)
2. Run `git show <commit_sha>` to inspect actual changes + commit message
3. Verify:
   - Commit message references finding_id (or paraphrases finding clearly)
   - Diff touches the right files (the ones mentioned in finding evidence)
   - Diff change addresses the root cause (not just suppression — e.g., adding `// @ts-ignore` is FAIL)
4. Output structured verdict per fix:

## Output format

```
## QA-Checker — Phase {phase_number}

### Per-fix verification
- [PASS/PARTIAL/FAIL] finding_id: F-NN — fix commit {sha}
  - Issue claim: {text}
  - Fix scope: {files/lines}
  - Root cause addressed? {Y/N — reasoning}

### Cumulative verdict
**PASS | PARTIAL | FAIL** — {summary}

### If PARTIAL/FAIL — gaps per fix
1. F-NN @ {sha}: {gap with file:line + remediation}
```

## Verdict semantics

- **PASS:** All fixes traceable to findings, root causes addressed, no suppression hacks
- **PARTIAL:** 1+ fix uses suppression (`@ts-ignore`, `noqa`, `pylint: disable`) without comment justifying why root-fix infeasible. Build CONTINUES (advisory) but operator reviews
- **FAIL:** Multiple fixes are suppression-only, OR fix commit doesn't actually touch the files in finding evidence (false fix), OR commit message doesn't reference finding_id

## Strict rules

- Suppression IS allowed if commit message explains why root-fix infeasible (e.g., "third-party type bug, suppressed pending upstream fix #X"). Otherwise FAIL.
- "Tests pass" is NOT sufficient — fix must address the issue claim semantically.
- If fix commit reverts the test instead of fixing the code: AUTO-FAIL.

This is a meta-quality gate. Run ONCE after all fix-loop iterations complete (Phase 3d tail). Do NOT run per-iteration.
```

Wire spawn at `commands/vg/review.md:6205-6219` (Phase 3d tail):

```markdown
**Phase 3d.5 (v2.68.0 C2): QA-Checker meta-verification**

After Phase 3 fix-loop converges (verdict=ok or max_iter reached), spawn QA-Checker:

\`\`\`bash
bash scripts/vg-narrate-spawn.sh vg-review-qa-checker spawning "QA-check ${PHASE_NUMBER} fix commits"
\`\`\`

Then: `Agent(subagent_type="vg-review-qa-checker", prompt=<rendered with phase_dir + fix_commits list>)`.

Marker: `phase3d_5_qa_checker` (severity=warn — advisory in v2.68.0; will flip to block in v2.69.0).
```

**Step 4-5:** Mirror review.md. Commit.

```bash
git commit -m "feat(review): C2 QA-Checker meta-agent + Phase 3d.5 wire (v2.68.0)"
```

---

## Task 3 (C3): Hybridize runtime-evidence.py

**Files:**
- Modify: `scripts/validators/runtime-evidence.py` (add LLM fallback for ambiguous cases)
- Mirror
- Test: `tests/test_c3_hybrid_runtime_evidence.py` (NEW)

**Step 1: Failing test**

```python
"""v2.68.0 C3 — Hybridize runtime-evidence.py."""
from pathlib import Path
import re


def test_runtime_evidence_has_ambiguous_branch():
    src = Path("scripts/validators/runtime-evidence.py").read_text(encoding="utf-8")
    # Must define ambiguous case + LLM fallback hook
    assert re.search(r"ambiguous|AMBIGUOUS", src), \
        "runtime-evidence.py must handle ambiguous case (v2.68.0 C3)"


def test_runtime_evidence_emits_confidence():
    src = Path("scripts/validators/runtime-evidence.py").read_text(encoding="utf-8")
    # Must emit confidence score (high/medium/low)
    assert re.search(r"confidence", src, re.IGNORECASE), \
        "runtime-evidence.py must emit confidence score"


def test_runtime_evidence_documents_llm_fallback():
    src = Path("scripts/validators/runtime-evidence.py").read_text(encoding="utf-8")
    # Comment or docstring must document LLM fallback for ambiguous
    assert re.search(r"(?:LLM|crossai|reviewer)\s+(?:fallback|judge|judgment|review)", src, re.IGNORECASE), \
        "must document LLM fallback path"
```

**Step 2: FAIL**

**Step 3: Implement**

In `scripts/validators/runtime-evidence.py`, add:

```python
def classify_evidence_match(found_files: list[Path], expected_pattern: str, age_seconds: int) -> tuple[str, str]:
    """Return (verdict, confidence). Hybrid logic:
    
    Deterministic rules:
    - found_files empty → FAIL, confidence=high
    - found_files exact match + age < 1h → PASS, confidence=high
    - found_files match but age 1-24h → PASS, confidence=medium (stale-ish)
    - found_files partial match (some expected files missing) → AMBIGUOUS, confidence=low
    
    AMBIGUOUS verdict means: defer to LLM (CrossAI reviewer) for judgment.
    Validator emits AMBIGUOUS evidence; downstream review aggregates LLM
    judgment on the same files to break the tie.
    """
    if not found_files:
        return "FAIL", "high"
    if age_seconds < 3600:
        return "PASS", "high"
    if age_seconds < 86400:
        return "PASS", "medium"
    if len(found_files) >= len(expected_pattern.split(",")) // 2:
        return "AMBIGUOUS", "low"
    return "FAIL", "medium"
```

Wire `verdict, confidence = classify_evidence_match(...)` in main flow. Emit verdict + confidence in evidence JSON (C1 already adds JSON write).

**Step 4-5:** Mirror, test, commit.

```bash
git commit -m "feat(validators): C3 hybridize runtime-evidence with AMBIGUOUS+confidence (v2.68.0)"
```

---

## Task 4 (C4): Discourse phase (AGREE/CHALLENGE/CONNECT/SURFACE)

**Files:**
- Modify: `scripts/crossai-normalize-results.py:188-210` (replace voting verdict with discourse aggregator)
- Add: helper `compute_discourse_verdict(reviewers)` — handles 4 moves
- Mirror
- Test: `tests/test_c4_discourse_phase.py` (NEW)

**Step 1: Failing test**

```python
"""v2.68.0 C4 — Discourse phase aggregator."""
import importlib.util
import sys
from pathlib import Path
import pytest


def _load():
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "crossai_normalize_results",
        repo_root / "scripts" / "crossai-normalize-results.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_discourse_function_exists():
    mod = _load()
    assert hasattr(mod, "compute_discourse_verdict"), \
        "compute_discourse_verdict function missing (v2.68.0 C4)"


def test_all_agree_yields_high_confidence_verdict():
    mod = _load()
    reviewers = [
        {"name": "Claude", "verdict": "pass", "findings": []},
        {"name": "Codex", "verdict": "pass", "findings": []},
        {"name": "Gemini", "verdict": "pass", "findings": []},
    ]
    result = mod.compute_discourse_verdict(reviewers)
    assert result["verdict"] == "pass"
    assert result["confidence"] == "high"
    assert any(m["move"] == "AGREE" for m in result["moves"])


def test_one_challenges_yields_partial_verdict():
    mod = _load()
    reviewers = [
        {"name": "Claude", "verdict": "pass", "findings": []},
        {"name": "Codex", "verdict": "pass", "findings": []},
        {"name": "Gemini", "verdict": "block", "findings": [{"id": "F-1", "title": "auth bypass"}]},
    ]
    result = mod.compute_discourse_verdict(reviewers)
    # 1 challenger = SURFACE the dissenting finding for human review
    assert result["verdict"] in ("flag", "partial")
    assert any(m["move"] == "CHALLENGE" for m in result["moves"])
    assert any(m["move"] == "SURFACE" for m in result["moves"])


def test_two_block_one_pass_yields_block_verdict():
    mod = _load()
    reviewers = [
        {"name": "Claude", "verdict": "block", "findings": [{"id": "F-1"}]},
        {"name": "Codex", "verdict": "block", "findings": [{"id": "F-2"}]},
        {"name": "Gemini", "verdict": "pass", "findings": []},
    ]
    result = mod.compute_discourse_verdict(reviewers)
    assert result["verdict"] == "block"
    # The pass-reviewer's perspective should be SURFACEd (might be missing context)
    assert any(m["move"] == "SURFACE" or m["move"] == "CONNECT" for m in result["moves"])


def test_overlapping_findings_yield_connect_move():
    """When 2 reviewers raise SAME finding (same id or normalized title), emit CONNECT move."""
    mod = _load()
    reviewers = [
        {"name": "Claude", "verdict": "block", "findings": [{"id": "F-AUTH", "title": "auth bypass on /admin"}]},
        {"name": "Codex", "verdict": "block", "findings": [{"id": "F-AUTH", "title": "auth bypass on /admin"}]},
        {"name": "Gemini", "verdict": "pass", "findings": []},
    ]
    result = mod.compute_discourse_verdict(reviewers)
    assert any(m["move"] == "CONNECT" for m in result["moves"]), \
        "overlapping findings must emit CONNECT move (corroboration)"
```

**Step 2: FAIL**

**Step 3: Implement** in `scripts/crossai-normalize-results.py`:

```python
def compute_discourse_verdict(reviewers: list[dict]) -> dict:
    """v2.68.0 C4: Discourse-based 3-reviewer aggregation.
    
    Replaces voting (2+ block → block) with discourse moves:
    - AGREE: all reviewers same verdict (high confidence)
    - CHALLENGE: 1 reviewer dissents (surface the dissent for human review)
    - CONNECT: 2+ reviewers raise overlapping findings (corroboration)
    - SURFACE: minority view emitted explicitly so human can weigh
    
    Returns: {verdict, confidence, moves: [{move, reviewer?, finding_id?, note}]}
    """
    moves = []
    verdicts = [r["verdict"] for r in reviewers]
    n = len(reviewers)
    
    # Collect overlapping findings
    finding_groups: dict[str, list[str]] = {}
    for r in reviewers:
        for f in r.get("findings", []):
            key = f.get("id") or f.get("title", "")
            finding_groups.setdefault(key, []).append(r["name"])
    overlapping = {k: v for k, v in finding_groups.items() if len(v) >= 2}
    for key, names in overlapping.items():
        moves.append({
            "move": "CONNECT",
            "finding": key,
            "reviewers": names,
            "note": f"{len(names)} reviewers corroborate this finding",
        })
    
    # AGREE: all same verdict
    if len(set(verdicts)) == 1:
        moves.append({"move": "AGREE", "verdict": verdicts[0], "note": f"All {n} reviewers agree"})
        return {"verdict": verdicts[0], "confidence": "high", "moves": moves}
    
    # CHALLENGE/SURFACE: dissent exists
    block_count = sum(1 for v in verdicts if v == "block")
    flag_count = sum(1 for v in verdicts if v == "flag")
    pass_count = sum(1 for v in verdicts if v == "pass")
    
    # Identify dissenters (minority verdict)
    from collections import Counter
    counter = Counter(verdicts)
    majority_verdict, _ = counter.most_common(1)[0]
    for r in reviewers:
        if r["verdict"] != majority_verdict:
            moves.append({
                "move": "CHALLENGE",
                "reviewer": r["name"],
                "verdict": r["verdict"],
                "note": f"{r['name']} dissents from majority ({majority_verdict})",
            })
            for f in r.get("findings", []):
                if (f.get("id") or f.get("title", "")) not in overlapping:
                    moves.append({
                        "move": "SURFACE",
                        "reviewer": r["name"],
                        "finding": f.get("id") or f.get("title", ""),
                        "note": f"Minority finding from {r['name']} — human review",
                    })
    
    # Verdict computation: 2+ block → block; 1 block + 1+ flag → flag; etc.
    if block_count >= 2:
        verdict = "block"
        confidence = "medium"
    elif block_count >= 1 or flag_count >= 2:
        verdict = "flag"
        confidence = "medium"
    elif pass_count >= 2:
        verdict = "pass"
        confidence = "low"  # 1 dissent
    else:
        verdict = "flag"
        confidence = "low"
    
    return {"verdict": verdict, "confidence": confidence, "moves": moves}
```

Wire into existing aggregation flow at line 188-210 — call `compute_discourse_verdict(reviewers)` instead of inline voting logic.

**Step 4-5:** Mirror, test, commit.

```bash
git commit -m "feat(crossai): C4 discourse phase aggregator (AGREE/CHALLENGE/CONNECT/SURFACE) (v2.68.0)"
```

---

## Task 5 (C5): Sandbox build executor

**Files:**
- Modify: `.claude/agents/vg-build-task-executor/SKILL.md` (add sandbox tempdir pattern from CrossAI runner)
- Modify: `commands/vg/_shared/build/waves-delegation.md` (delegation prompt mentions sandbox)
- Mirror commands
- Test: `tests/test_c5_sandbox_executor.py` (NEW)

**Step 1: Failing test**

```python
"""v2.68.0 C5 — Sandbox build executor."""
import re
from pathlib import Path


def test_executor_documents_sandbox_pattern():
    body = Path(".claude/agents/vg-build-task-executor/SKILL.md").read_text(encoding="utf-8")
    # Must mention sandbox / tempdir / isolation
    assert re.search(r"sandbox|tempdir|tempfile|isolat", body, re.IGNORECASE), \
        "executor must document sandbox pattern (v2.68.0 C5)"


def test_executor_describes_when_to_sandbox():
    body = Path(".claude/agents/vg-build-task-executor/SKILL.md").read_text(encoding="utf-8")
    # Should mention test exec specifically (not whole task)
    assert re.search(r"(?:test|pytest|jest|vitest).{0,100}(?:sandbox|isolat)", body, re.IGNORECASE | re.DOTALL), \
        "executor must specify test exec is what gets sandboxed"


def test_waves_delegation_mentions_sandbox():
    body = Path("commands/vg/_shared/build/waves-delegation.md").read_text(encoding="utf-8")
    assert re.search(r"sandbox|tempdir", body, re.IGNORECASE), \
        "waves-delegation must reference sandbox pattern"
```

**Step 2: FAIL**

**Step 3: Implement**

Add new section to `.claude/agents/vg-build-task-executor/SKILL.md`:

```markdown
## Sandbox runtime (v2.68.0 C5)

When running tests that touch shared state (DB connections, ports, filesystem
outside repo), wrap test exec in a sandbox tempdir. Pattern:

\`\`\`python
import tempfile
import os
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="vg-test-sandbox-") as sandbox:
    env = os.environ.copy()
    env["TMPDIR"] = sandbox
    env["XDG_CACHE_HOME"] = sandbox
    # Do NOT chdir — keep cwd at repo root for relative imports
    subprocess.run(["pytest", "..."], env=env, check=True)
\`\`\`

**When to sandbox:**
- Tests that write to `/tmp` or `~/.cache`
- Tests that bind to network ports (use sandbox-allocated port)
- Tests that touch DB (use ephemeral schema/db_name in sandbox)

**When NOT to sandbox:**
- Pure unit tests with no I/O — sandbox overhead unnecessary
- Tests that need real repo state (e.g., git history, file fingerprints) — these are NOT isolatable

Document choice in commit message if you sandboxed: `(sandbox: tmpdir for DB exec)`.
```

Add 1-line reminder to `commands/vg/_shared/build/waves-delegation.md`:

```markdown
**Sandbox note (v2.68.0 C5):** Tests touching shared state (DB, ports, /tmp) should run in tempdir sandbox per `.claude/agents/vg-build-task-executor/SKILL.md` "Sandbox runtime" section.
```

**Step 4-5:** Mirror waves-delegation. Commit.

```bash
git commit -m "feat(executor): C5 sandbox runtime pattern for shared-state tests (v2.68.0)"
```

---

## Task 6 (C6): Min-budget floor (token cost cap)

**Files:**
- Create: `scripts/vg-budget-tracker.py` (NEW — simple token counter + abort gate)
- Modify: `scripts/vg-orchestrator/__main__.py` emit-event subcommand (call budget tracker on emit)
- Mirror
- Modify: `vg.config.template.md` (add `min_budget_floor_usd: N` config field)
- Mirror config template
- Test: `tests/test_c6_min_budget_floor.py` (NEW)

**Step 1: Failing test**

```python
"""v2.68.0 C6 — Min-budget floor."""
import importlib.util
import sys
import json
from pathlib import Path
import pytest


def _load_tracker():
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "vg_budget_tracker",
        repo_root / "scripts" / "vg-budget-tracker.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_budget_tracker_module_exists():
    p = Path("scripts/vg-budget-tracker.py")
    assert p.exists(), "vg-budget-tracker.py missing (v2.68.0 C6)"


def test_track_token_usage(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"
    
    mod.track(state_file, "phase-test", input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6")
    
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "phase-test" in state["phases"]
    phase_data = state["phases"]["phase-test"]
    assert phase_data["total_input_tokens"] == 1000
    assert phase_data["total_output_tokens"] == 500


def test_abort_when_budget_exceeded(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"
    
    # Simulate: floor set at $0.01, tokens cost > floor
    mod.track(state_file, "phase-test", input_tokens=1_000_000, output_tokens=500_000, model="claude-opus-4-7")
    
    over_budget, total_cost = mod.check_budget(state_file, "phase-test", floor_usd=0.01)
    assert over_budget is True
    assert total_cost > 0.01


def test_under_budget_passes(tmp_path):
    mod = _load_tracker()
    state_file = tmp_path / "budget.json"
    
    mod.track(state_file, "phase-test", input_tokens=100, output_tokens=50, model="claude-haiku-4-5-20251001")
    
    over_budget, total_cost = mod.check_budget(state_file, "phase-test", floor_usd=10.00)
    assert over_budget is False


def test_config_template_documents_floor():
    body = Path("vg.config.template.md").read_text(encoding="utf-8")
    assert "min_budget_floor_usd" in body or "budget_floor" in body.lower(), \
        "vg.config.template.md must document min_budget_floor field"
```

**Step 2: FAIL**

**Step 3: Implement** `scripts/vg-budget-tracker.py`:

```python
"""v2.68.0 C6 — Min-budget floor tracker.

Tracks token usage per phase across orchestrator events. Aborts phase
when projected cost exceeds configured floor.

Pricing (USD per 1M tokens, as of 2026-05):
- claude-opus-4-7:        input $15 / output $75
- claude-sonnet-4-6:      input $3  / output $15
- claude-haiku-4-5:       input $1  / output $5
- gpt-5.5 (codex):        input $5  / output $15
- gemini-2.5-pro:         input $2  / output $10

Defaults applied when model unrecognized: input $5 / output $15.
"""
import json
import sys
from pathlib import Path

PRICING_PER_MILLION = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-5.5": (5.0, 15.0),
    "gpt-5.4": (5.0, 15.0),
    "gemini-2.5-pro": (2.0, 10.0),
    "default": (5.0, 15.0),
}


def _cost(input_tokens: int, output_tokens: int, model: str) -> float:
    in_rate, out_rate = PRICING_PER_MILLION.get(model, PRICING_PER_MILLION["default"])
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def track(state_file: Path, phase_id: str, *, input_tokens: int, output_tokens: int, model: str) -> dict:
    state = {"phases": {}}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    state.setdefault("phases", {}).setdefault(phase_id, {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "events": [],
    })
    phase_data = state["phases"][phase_id]
    phase_data["total_input_tokens"] += input_tokens
    phase_data["total_output_tokens"] += output_tokens
    phase_data["total_cost_usd"] += _cost(input_tokens, output_tokens, model)
    phase_data["events"].append({
        "input_tokens": input_tokens, "output_tokens": output_tokens, "model": model,
    })
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def check_budget(state_file: Path, phase_id: str, floor_usd: float) -> tuple[bool, float]:
    """Return (over_budget, total_cost). over_budget=True triggers abort upstream."""
    if not state_file.exists():
        return False, 0.0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    phase_data = state.get("phases", {}).get(phase_id, {})
    total_cost = phase_data.get("total_cost_usd", 0.0)
    return total_cost > floor_usd, total_cost


def main():
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    
    track_p = sub.add_parser("track")
    track_p.add_argument("--state-file", required=True, type=Path)
    track_p.add_argument("--phase-id", required=True)
    track_p.add_argument("--input-tokens", type=int, required=True)
    track_p.add_argument("--output-tokens", type=int, required=True)
    track_p.add_argument("--model", required=True)
    
    check_p = sub.add_parser("check")
    check_p.add_argument("--state-file", required=True, type=Path)
    check_p.add_argument("--phase-id", required=True)
    check_p.add_argument("--floor-usd", type=float, required=True)
    
    args = p.parse_args()
    
    if args.cmd == "track":
        track(args.state_file, args.phase_id,
              input_tokens=args.input_tokens, output_tokens=args.output_tokens,
              model=args.model)
        return 0
    elif args.cmd == "check":
        over, cost = check_budget(args.state_file, args.phase_id, args.floor_usd)
        if over:
            print(f"⛔ Budget exceeded: ${cost:.4f} > ${args.floor_usd:.4f}", file=sys.stderr)
            return 1
        print(f"✓ Within budget: ${cost:.4f} / ${args.floor_usd:.4f}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add `min_budget_floor_usd: 10.00` field to `vg.config.template.md` (per-config knob).

**Step 4-5:** Mirror script + config template. Commit.

```bash
git commit -m "feat(orchestrator): C6 min-budget floor tracker + abort gate (v2.68.0)"
```

---

## Task 7: VERSION + CHANGELOG + tag + push

**Files:** VERSION (2.67.0→2.68.0) + package.json + CHANGELOG (prepend v2.68.0).

**CHANGELOG entry:**

```markdown
## v2.68.0 — C-tier strict review research adoptions (2026-05-10)

### Features (research-driven hardening — 6 patterns adopted)
- **C1 Evidence Gate (obra/superpowers):** Retrofitted 3 missing validators (`runtime-evidence.py`, `verify-workflow-evidence.py`, `verify-read-evidence.py`) to write structured `${PHASE_DIR}/.evidence/<gate_id>.json` with verdict/findings/signed_at fields. Audit trail now complete across all L-gate validators.
- **C2 QA-Checker meta-agent (CodeAgent paper):** New `.claude/agents/vg-review-qa-checker/SKILL.md`. Verifies fix commits actually address original issue claims (not just tests pass). Detects suppression hacks (`@ts-ignore`, `noqa` without justification), false fixes (commit doesn't touch finding files), test reverts. Verdict: PASS/PARTIAL/FAIL. Wired in review Phase 3d.5 (after fix-loop converges). Severity=warn in v2.68.0 (advisory), will flip to block in v2.69.0.
- **C3 Hybrid gate:** Hybridized `runtime-evidence.py` with deterministic-then-LLM-fallback pattern. New verdicts: PASS (high confidence), AMBIGUOUS (defer to LLM judgment), FAIL. Confidence score (high/medium/low) emitted alongside verdict for downstream LLM judges.
- **C4 Discourse phase (open-code-review):** Replaced voting-based aggregator at `crossai-normalize-results.py:188-210` with `compute_discourse_verdict()` that emits AGREE/CHALLENGE/CONNECT/SURFACE moves. AGREE: all 3 reviewers concur (high confidence). CHALLENGE: dissent identified. CONNECT: 2+ reviewers raise overlapping findings (corroboration). SURFACE: minority view emitted explicitly so human can weigh. Verdict + confidence emitted with moves array for richer downstream triage.
- **C5 Sandbox runtime:** Documented sandbox pattern in `.claude/agents/vg-build-task-executor/SKILL.md` for tests touching shared state (DB, ports, /tmp). Mirrors `mkdtemp + env scrub` pattern from CrossAI runners. Build executor delegation reminds about sandbox choice.
- **C6 Min-budget floor:** New `scripts/vg-budget-tracker.py` tracks token cost per phase across 6 model classes (Opus 4.7, Sonnet 4.6, Haiku 4.5, gpt-5.5, gpt-5.4, gemini-2.5-pro). New `min_budget_floor_usd: 10.00` field in `vg.config.template.md`. Subcommands: `track` (record event), `check` (return rc=1 + cost when over floor). Hook for orchestrator abort on overrun.

### Test coverage
**18+ new tests across 6 suites.** All pass.

### Migration
- **C1-C3:** Transparent enhancements. No migration.
- **C4 discourse:** Aggregator output shape extended (now includes `moves` array). Downstream consumers reading `verdict` continue to work; tools wanting discourse detail read new `moves`.
- **C5 sandbox:** Documentation only — implementers opt in per task.
- **C6 budget:** Per-config opt-in via `min_budget_floor_usd` field. Default behavior unchanged (no floor → no abort).
- **C2 QA-Checker:** severity=warn (advisory) in v2.68.0. Will flip to block in v2.69.0 after telemetry shows verdict distribution + false-positive rate.

## v2.67.0 — Dogfood Issues Batch 2 (2026-05-10)
```

Steps:
1. Bump VERSION + package.json
2. Prepend CHANGELOG
3. Commit: `release: v2.68.0 — C-tier strict review research adoptions`
4. Tag `v2.68.0`
5. Push origin main + tag
6. `gh release create v2.68.0`

---

## Verification

- `git log --oneline | head -10` shows 7 commits (6 tasks + release)
- `cat VERSION` = `2.68.0`
- 18+ new tests pass
- All v2.65.0-v2.67.0 tests still pass

---

## Execution mode

Subagent-driven development. Suggested batches:
- **Batch A:** C1 (T1) + C3 (T3) — both touch validators
- **Batch B:** C4 (T4) — discourse aggregator (largest/most surgical, alone)
- **Batch C:** C2 (T2) + C5 (T5) — both touch agent SKILL.md text
- **Batch D:** C6 (T6) — budget tracker (independent)
- **Release:** Task 7

Each task = own commit.
