# goal-explosion-200 fixture

200 distinct behavior classes (each row has unique view + resource +
assertion_type) so canonical-key dedupe is a no-op. Tests the per-mode
cap + overflow split:

- light cap=50 → 50 main + 150 overflow
- deep cap=150 → 150 main + 50 overflow
- exhaustive cap=400 → 200 main + 0 overflow

Used by `tests/test_goal_aggregation_e2e.py`.
