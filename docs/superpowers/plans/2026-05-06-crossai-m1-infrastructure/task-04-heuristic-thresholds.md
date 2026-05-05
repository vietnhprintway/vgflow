# Task 04: Add heuristic thresholds parser + `Thresholds` dataclass

**Goal:** Parse `crossai.heuristic_thresholds` block from `vg.config.md` and expose it as a typed `Thresholds` dataclass. Used by M2 to decide "phase nhỏ" vs "phase lớn"; M1 only ships the parser + accessor (gating logic deferred to M2).

**Files:**
- Modify: `scripts/lib/crossai_config.py`
- Mirror: `.claude/scripts/lib/crossai_config.py`
- Test: `scripts/tests/test_crossai_config_resolve.py` (extend)

---

- [ ] **Step 1: Append failing tests**

Append to `scripts/tests/test_crossai_config_resolve.py`:

```python


# ---- Task 04 tests ----


def test_thresholds_default_values(tmp_path):
    """No `crossai.heuristic_thresholds` block → return library defaults
    (3/2/5)."""
    from crossai_config import resolve_thresholds
    _seed_config(tmp_path)
    th = resolve_thresholds(tmp_path)
    assert th.min_endpoints == 3
    assert th.min_critical_goals == 2
    assert th.min_plan_tasks == 5


def test_thresholds_custom_values(tmp_path):
    """Custom thresholds in vg.config.md override defaults."""
    from crossai_config import resolve_thresholds
    custom = _SAMPLE_CONFIG + """\

crossai:
  heuristic_thresholds:
    min_endpoints: 7
    min_critical_goals: 4
    min_plan_tasks: 12
"""
    _seed_config(tmp_path, content=custom)
    th = resolve_thresholds(tmp_path)
    assert th.min_endpoints == 7
    assert th.min_critical_goals == 4
    assert th.min_plan_tasks == 12


def test_thresholds_partial_override(tmp_path):
    """Only one field overridden — others fall back to defaults."""
    from crossai_config import resolve_thresholds
    custom = _SAMPLE_CONFIG + """\

crossai:
  heuristic_thresholds:
    min_endpoints: 10
"""
    _seed_config(tmp_path, content=custom)
    th = resolve_thresholds(tmp_path)
    assert th.min_endpoints == 10
    assert th.min_critical_goals == 2  # default
    assert th.min_plan_tasks == 5  # default


def test_thresholds_no_config_file(tmp_path):
    """No vg.config.md → return all defaults (no error)."""
    from crossai_config import resolve_thresholds
    th = resolve_thresholds(tmp_path)
    assert th.min_endpoints == 3
    assert th.min_critical_goals == 2
    assert th.min_plan_tasks == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
python3 -m pytest scripts/tests/test_crossai_config_resolve.py::test_thresholds_default_values \
                  scripts/tests/test_crossai_config_resolve.py::test_thresholds_custom_values \
                  scripts/tests/test_crossai_config_resolve.py::test_thresholds_partial_override \
                  scripts/tests/test_crossai_config_resolve.py::test_thresholds_no_config_file \
                  -v
```

Expected: 4 failures (`AttributeError: module 'crossai_config' has no attribute 'resolve_thresholds'`).

- [ ] **Step 3: Implement `Thresholds` + parser in `scripts/lib/crossai_config.py`**

Append to `scripts/lib/crossai_config.py`:

```python


# ── Heuristic thresholds (M1 Task 04) ──────────────────────────────────


_DEFAULT_MIN_ENDPOINTS = 3
_DEFAULT_MIN_CRITICAL_GOALS = 2
_DEFAULT_MIN_PLAN_TASKS = 5


@dataclass
class Thresholds:
    """Heuristic thresholds for `crossai.policy: auto` mode.

    A phase counts as "small" (suggest skip) when ALL three counts are at
    or below their threshold (AND logic, per Q23 of the M1 design).

    Default values per spec: 3 endpoints, 2 critical goals, 5 plan tasks.
    Operator may override in vg.config.md `crossai.heuristic_thresholds:`.
    """
    min_endpoints: int = _DEFAULT_MIN_ENDPOINTS
    min_critical_goals: int = _DEFAULT_MIN_CRITICAL_GOALS
    min_plan_tasks: int = _DEFAULT_MIN_PLAN_TASKS


def _parse_heuristic_thresholds(config_text: str) -> dict[str, int]:
    """Extract `crossai.heuristic_thresholds` block.

    Format:
        crossai:
          heuristic_thresholds:
            min_endpoints: 3
            min_critical_goals: 2
            min_plan_tasks: 5
    """
    out: dict[str, int] = {}
    in_crossai = False
    in_thresholds = False
    for line in config_text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "crossai:" and indent == 0:
            in_crossai = True
            continue
        if in_crossai:
            if line and not line[0].isspace() and ":" in line:
                # next top-level key
                in_crossai = False
                in_thresholds = False
                continue
            if stripped == "heuristic_thresholds:" and indent == 2:
                in_thresholds = True
                continue
            if in_thresholds and indent == 4 and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key in ("min_endpoints", "min_critical_goals",
                          "min_plan_tasks"):
                    try:
                        out[key] = int(val)
                    except ValueError:
                        pass  # keep default
            elif in_thresholds and indent < 4 and stripped:
                in_thresholds = False
    return out


def resolve_thresholds(repo_root: Path) -> Thresholds:
    """Read vg.config.md and return Thresholds with operator overrides
    layered on top of library defaults.

    Missing config file or missing block → all defaults (no error)."""
    repo_root = Path(repo_root).resolve()
    cfg = _find_config(repo_root)
    if cfg is None:
        return Thresholds()
    text = cfg.read_text(encoding="utf-8", errors="replace")
    overrides = _parse_heuristic_thresholds(text)
    return Thresholds(
        min_endpoints=overrides.get("min_endpoints", _DEFAULT_MIN_ENDPOINTS),
        min_critical_goals=overrides.get(
            "min_critical_goals", _DEFAULT_MIN_CRITICAL_GOALS,
        ),
        min_plan_tasks=overrides.get(
            "min_plan_tasks", _DEFAULT_MIN_PLAN_TASKS,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
python3 -m pytest scripts/tests/test_crossai_config_resolve.py -v
```

Expected: all tests pass (Task 02 + 03 + 04 = 16 total).

- [ ] **Step 5: Sync mirror + commit**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
cp scripts/lib/crossai_config.py .claude/scripts/lib/crossai_config.py
git add scripts/lib/crossai_config.py \
        .claude/scripts/lib/crossai_config.py \
        scripts/tests/test_crossai_config_resolve.py
git commit -m "feat(crossai-config): heuristic thresholds parser

M1 Task 04 — Thresholds dataclass + resolve_thresholds(repo_root) reading
vg.config.md crossai.heuristic_thresholds block. Defaults 3/2/5 (endpoints/
critical goals/plan tasks) per spec Q23. Used by M2 gating to decide
'phase nhỏ' for auto-skip mode; M1 only ships the parser.

Tests: 4 new (defaults, full override, partial override, no config file).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
