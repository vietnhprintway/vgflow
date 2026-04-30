# goal-dedupe-50-rows fixture

50 elements all sharing the same canonical key — view + selector_hash +
action_semantic + lens + resource + assertion_type — must collapse to
exactly 1 entry in `TEST-GOALS-DISCOVERED.md` with 0 overflow.

Used by `tests/test_goal_aggregation_e2e.py::test_50_rows_same_class_dedupes_to_one`.
