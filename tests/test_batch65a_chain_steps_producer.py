"""tests/test_batch65a_chain_steps_producer.py — B65a (codex BLOCKERs #2 + #5).

Codex audit (dev-phases/test-flow-hardening/CODEX-AUDIT.md) flagged:

BLOCKER #2: chain_steps lost in pipeline. enrich-test-goals creates
            feature_chain goals with chain_steps[], but render_markdown
            doesn't emit them; generate-lifecycle-specs doesn't parse them;
            _goal_spec doesn't output them. Codegen consumer changes
            (B65c) impossible without producer chain.

BLOCKER #5: enrich emits S1-S4 (4 steps) for cross_view goals, but
            B62 validator requires ≥8 (MIN_CHAIN_STEPS). Producer-validator
            mismatch.

Fix:
  - enrich-test-goals.py render_markdown emits goal_class + enables[] +
    chain_steps (with step_id, description, target_view_class,
    expected_state, downstream_effects[])
  - enrich cross_view goal generator emits S1-S8 (was S1-S4)
  - generate-lifecycle-specs.py _parse_chain_steps() + _parse_enables()
    extract from TEST-GOAL frontmatter (inline + YAML block forms)
  - _goal_spec() persists chain_steps + enables + goal_class in
    LIFECYCLE-SPECS.json output

Coverage:
  1. enrich render_markdown emits goal_class for feature_chain stubs
  2. enrich render emits chain_steps YAML block
  3. enrich render emits enables[]
  4. enrich cross_view goal has 8 chain_steps (was 4)
  5. enrich chain_steps S1-S8 traverses out of source view family
  6. enrich chain_steps has ≥2 steps with downstream_effects
  7. generate-lifecycle parse_chain_steps inline downstream_effects []
  8. generate-lifecycle parse_chain_steps YAML block downstream_effects
  9. generate-lifecycle parse_enables inline form
  10. generate-lifecycle parse_enables YAML block form
  11. _goal_spec output contains chain_steps when present in goal
  12. _goal_spec output contains enables when present
  13. _goal_spec output contains goal_class
  14. Back-compat: goal without chain_steps → empty list (not crash)
  15. Mirror parity (.claude/ in sync)
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENRICH = REPO / "scripts" / "enrich-test-goals.py"
ENRICH_MIRROR = REPO / ".claude" / "scripts" / "enrich-test-goals.py"
LIFECYCLE = REPO / "scripts" / "generate-lifecycle-specs.py"
LIFECYCLE_MIRROR = REPO / ".claude" / "scripts" / "generate-lifecycle-specs.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _make_cross_view_scan() -> dict:
    return {
        "view": "/sites",
        "cross_view_propagation_observations": [{
            "source_view": "/sites",
            "target_view": "/dashboard",
            "target_view_class": "dashboard_summary",
            "action": "create",
            "entity_canonical_id": "site:create",
            "observed_in_target": "yes",
            "observed_count_delta": 1,
        }],
    }


def test_enrich_render_emits_goal_class(tmp_path):
    """B65a #2: render_markdown must include goal_class field."""
    mod = _load(ENRICH, "enrich_b65a_1")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    assert chain_stubs, "expected feature_chain stub from cross_view"
    rendered = mod.render_markdown(chain_stubs, 0, 1, 3)
    assert "goal_class: feature_chain" in rendered


def test_enrich_render_emits_chain_steps_yaml_block(tmp_path):
    mod = _load(ENRICH, "enrich_b65a_2")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    rendered = mod.render_markdown(chain_stubs, 0, 1, 3)
    assert "chain_steps:" in rendered
    assert "step_id: S1" in rendered
    assert "step_id: S8" in rendered
    assert "target_view_class:" in rendered
    assert "expected_state:" in rendered
    assert "downstream_effects:" in rendered


def test_enrich_render_emits_enables():
    mod = _load(ENRICH, "enrich_b65a_3")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    rendered = mod.render_markdown(chain_stubs, 0, 1, 3)
    assert "enables:" in rendered


def test_enrich_cross_view_goal_has_8_chain_steps():
    """B65a #5: cross_view goal MUST have ≥8 chain_steps per B62 validator."""
    mod = _load(ENRICH, "enrich_b65a_4")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    assert chain_stubs
    g = chain_stubs[0]
    assert len(g["chain_steps"]) >= 8, f"expected ≥8 steps, got {len(g['chain_steps'])}"
    step_ids = [s["step_id"] for s in g["chain_steps"]]
    assert step_ids == ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]


def test_enrich_chain_steps_traverses_out_of_source_family():
    """B62 anti-cheat: at least 1 step target_view_class NOT in source family."""
    mod = _load(ENRICH, "enrich_b65a_5")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    g = chain_stubs[0]
    source_family = {"source_view", "source_view_modal", "source_view_form"}
    target_classes = [s["target_view_class"] for s in g["chain_steps"]]
    out_of_family = [tc for tc in target_classes if tc not in source_family]
    assert out_of_family, f"chain stays in source family: {target_classes}"


def test_enrich_chain_steps_has_2plus_downstream_effects():
    """B62 anti-cheat: at least 2 steps with non-empty downstream_effects."""
    mod = _load(ENRICH, "enrich_b65a_6")
    stubs = mod.classify_elements("/sites", _make_cross_view_scan(), {}, [])
    chain_stubs = [s for s in stubs if s.get("goal_class") == "feature_chain"]
    g = chain_stubs[0]
    with_effects = [s for s in g["chain_steps"] if s.get("downstream_effects")]
    assert len(with_effects) >= 2


def test_lifecycle_parse_chain_steps_inline_empty_effects():
    mod = _load(LIFECYCLE, "lc_b65a_7")
    text = """## G-01 Foo
goal_class: feature_chain
chain_steps:
  - step_id: S1
    description: "do thing"
    target_view_class: source_view
    expected_state: ready
    downstream_effects: []
"""
    steps = mod._parse_chain_steps(text)
    assert len(steps) == 1
    assert steps[0]["step_id"] == "S1"
    assert steps[0]["target_view_class"] == "source_view"
    assert steps[0]["downstream_effects"] == []


def test_lifecycle_parse_chain_steps_yaml_block_effects():
    mod = _load(LIFECYCLE, "lc_b65a_8")
    text = """## G-01 Foo
chain_steps:
  - step_id: S1
    target_view_class: dashboard_summary
    expected_state: visible
    downstream_effects:
      - "row +1"
      - "audit log entry"
  - step_id: S2
    target_view_class: audit_log
    expected_state: archived
    downstream_effects: []
"""
    steps = mod._parse_chain_steps(text)
    assert len(steps) == 2
    assert steps[0]["downstream_effects"] == ["row +1", "audit log entry"]
    assert steps[1]["downstream_effects"] == []


def test_lifecycle_parse_enables_inline():
    mod = _load(LIFECYCLE, "lc_b65a_9")
    text = "## G-01\nenables: [G-04, G-07]\n"
    assert mod._parse_enables(text) == ["G-04", "G-07"]


def test_lifecycle_parse_enables_yaml_block():
    mod = _load(LIFECYCLE, "lc_b65a_10")
    text = """## G-01
enables:
  - G-04
  - G-07
"""
    assert mod._parse_enables(text) == ["G-04", "G-07"]


def test_goal_spec_persists_chain_steps():
    mod = _load(LIFECYCLE, "lc_b65a_11")
    goal = {
        "id": "G-01",
        "title": "Foo",
        "goal_class": "feature_chain",
        "chain_steps": [
            {"step_id": "S1", "target_view_class": "source_view",
             "expected_state": "ready", "downstream_effects": []}
        ],
        "enables": ["G-02"],
    }
    spec = mod._goal_spec(goal, [], {})
    assert spec["chain_steps"] == goal["chain_steps"]


def test_goal_spec_persists_enables():
    mod = _load(LIFECYCLE, "lc_b65a_12")
    goal = {
        "id": "G-01", "title": "Foo", "goal_class": "feature_chain",
        "enables": ["G-04", "G-07"], "chain_steps": [],
    }
    spec = mod._goal_spec(goal, [], {})
    assert spec["enables"] == ["G-04", "G-07"]


def test_goal_spec_persists_goal_class():
    mod = _load(LIFECYCLE, "lc_b65a_13")
    goal = {"id": "G-01", "title": "Foo", "goal_class": "feature_chain",
            "chain_steps": [], "enables": []}
    spec = mod._goal_spec(goal, [], {})
    assert spec["goal_class"] == "feature_chain"


def test_back_compat_goal_without_chain_steps():
    """Legacy goal (no chain_steps field) → empty list, no crash."""
    mod = _load(LIFECYCLE, "lc_b65a_14")
    goal = {"id": "G-01", "title": "Foo", "goal_type": "mutation"}
    spec = mod._goal_spec(goal, [], {})
    assert spec.get("chain_steps") == []
    assert spec.get("enables") == []


def test_mirror_in_sync():
    assert ENRICH.read_text(encoding="utf-8") == ENRICH_MIRROR.read_text(encoding="utf-8")
    assert LIFECYCLE.read_text(encoding="utf-8") == LIFECYCLE_MIRROR.read_text(encoding="utf-8")
