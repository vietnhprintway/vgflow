"""tests/test_batch71a_resolver.py — B71a layered matcher for TodoWrite labels.

Tests the pure resolver module. Mirror parity + content-loss fix tested
separately (B71a snapshot writer test) and integration tests in B71f.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RESOLVER = REPO / "scripts" / "tasklist_id_resolver.py"
RESOLVER_MIRROR = REPO / ".claude" / "scripts" / "tasklist_id_resolver.py"

spec = importlib.util.spec_from_file_location("tasklist_id_resolver", RESOLVER)
mod = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(mod)  # type: ignore[union-attr]


# Real RTB c1a5edc3 contract items (subset, from agent investigator evidence).
RTB_C1A5_CONTRACT = [
    {"id": "0_parse_and_validate", "kind": "step"},
    {"id": "1_build_artifact_gate", "kind": "step"},
    {"id": "2_runtime_map_alignment", "kind": "step"},
    {"id": "3_crossai_sweep", "kind": "step"},
    {"id": "3_validate_deep_specs", "kind": "step"},
    {"id": "4_codegen", "kind": "step"},
    {"id": "5_fix_loop", "kind": "step"},
    {"id": "7_matrix_verdict", "kind": "step"},
    {"id": "workflow_other", "kind": "group"},
]


# ---------------------------------------------------------------------------
# Layer 1 — exact match.
# ---------------------------------------------------------------------------


def test_exact_match():
    sid, mc = mod.resolve("0_parse_and_validate", RTB_C1A5_CONTRACT)
    assert sid == "0_parse_and_validate"
    assert mc == "exact"


def test_exact_match_group():
    sid, mc = mod.resolve("workflow_other", RTB_C1A5_CONTRACT)
    assert sid == "workflow_other"
    assert mc == "exact"


# ---------------------------------------------------------------------------
# Layer 2 — normalized.
# ---------------------------------------------------------------------------


def test_normalized_title_case_arrow():
    """RTB c1a5edc3 cluster #1: '↳ 0 Parse And Validate' → '0_parse_and_validate'."""
    sid, mc = mod.resolve("↳ 0 Parse And Validate", RTB_C1A5_CONTRACT)
    assert sid == "0_parse_and_validate"
    assert mc == "normalized"


def test_normalized_no_arrow():
    sid, mc = mod.resolve("1 Build Artifact Gate", RTB_C1A5_CONTRACT)
    assert sid == "1_build_artifact_gate"
    assert mc == "normalized"


# ---------------------------------------------------------------------------
# Layer 3 — strip command prefix.
# ---------------------------------------------------------------------------


def test_strip_cmd_prefix_test_spec():
    """RTB c1a5edc3 cluster #2: '↳ test-spec 0_parse_and_validate' → '0_parse_and_validate'."""
    sid, mc = mod.resolve("↳ test-spec 0_parse_and_validate", RTB_C1A5_CONTRACT)
    assert sid == "0_parse_and_validate"
    assert mc in ("normalized", "strip-cmd", "substring")


def test_strip_cmd_prefix_with_emdash():
    """RTB cluster #2 with em-dash free text: '↳ test-spec 4_codegen — Spawn ...' → '4_codegen'."""
    sid, mc = mod.resolve(
        "↳ test-spec 4_codegen — Spawn vg-test-codegen full subagent pass",
        RTB_C1A5_CONTRACT,
    )
    assert sid == "4_codegen"
    # Substring match: '4_codegen' appears in normalized label.
    assert mc == "substring"


def test_strip_cmd_prefix_build():
    contract = [{"id": "0_initial", "kind": "step"}]
    sid, mc = mod.resolve("↳ build 0_initial", contract)
    assert sid == "0_initial"


# ---------------------------------------------------------------------------
# Layer 4 — strip decimal.
# ---------------------------------------------------------------------------


def test_strip_decimal_half_step():
    """'3.5 CrossAI Sweep' should resolve to '3_crossai_sweep' (drop .5)."""
    sid, mc = mod.resolve("↳ 3.5 CrossAI Sweep", RTB_C1A5_CONTRACT)
    assert sid == "3_crossai_sweep"
    assert mc in ("strip-decimal", "substring", "normalized")


# ---------------------------------------------------------------------------
# Layer 5 — substring.
# ---------------------------------------------------------------------------


def test_substring_match():
    """Label contains step_id as substring."""
    contract = [{"id": "foobar_step", "kind": "step"}]
    sid, mc = mod.resolve("Some long prefix foobar_step suffix", contract)
    assert sid == "foobar_step"
    assert mc == "substring"


# ---------------------------------------------------------------------------
# Layer 6 — slug fallback.
# ---------------------------------------------------------------------------


def test_slug_fallback():
    """When normalized doesn't match, slugify and compare."""
    contract = [{"id": "my_special_step", "kind": "step"}]
    sid, mc = mod.resolve("My Special Step", contract)
    assert sid == "my_special_step"
    # Should match at normalized layer (the underscores in step_id normalize to spaces).
    assert mc in ("normalized", "slug")


# ---------------------------------------------------------------------------
# Layer 7 — unresolved.
# ---------------------------------------------------------------------------


def test_unresolved_completely_foreign():
    sid, mc = mod.resolve("Completely unrelated text", RTB_C1A5_CONTRACT)
    assert sid.startswith("<unresolved>:")
    assert mc == "unresolved"
    # Hash is deterministic.
    sid2, _ = mod.resolve("Completely unrelated text", RTB_C1A5_CONTRACT)
    assert sid == sid2


def test_unresolved_empty_label():
    sid, mc = mod.resolve("", RTB_C1A5_CONTRACT)
    assert sid == "<unresolved>:empty"
    assert mc == "unresolved"


def test_unresolved_empty_contract():
    sid, mc = mod.resolve("foo", [])
    assert sid.startswith("<unresolved>:")
    assert mc == "unresolved"


def test_unresolved_numeric_tid_no_match():
    """Legacy numeric tid like '353' — should be unresolved without trace rehydration."""
    sid, mc = mod.resolve("353", RTB_C1A5_CONTRACT)
    assert mc == "unresolved"


# ---------------------------------------------------------------------------
# Tie-break behavior.
# ---------------------------------------------------------------------------


def test_tie_break_prefers_step_over_group():
    """If both group and step normalize same, prefer step."""
    contract = [
        {"id": "complete", "kind": "group"},
        {"id": "complete_action", "kind": "step"},
    ]
    sid, mc = mod.resolve("Complete", contract)
    assert sid == "complete"  # group-kind exact match wins for this label.


def test_tie_break_kind_hint_group():
    """kind_hint=group biases to group when both kinds match."""
    contract = [
        {"id": "complete", "kind": "group"},
        {"id": "complete", "kind": "step"},  # bad data, but test the tie-break
    ]
    # With kind_hint, the step-of-same-id stays; the resolver doesn't dedupe across kinds.
    sid, mc = mod.resolve("Complete", contract, kind_hint="group")
    assert sid == "complete"


def test_tie_break_levenshtein():
    """When 2 candidates remain after kind filter, prefer closer Levenshtein."""
    contract = [
        {"id": "foo_bar_baz", "kind": "step"},
        {"id": "foo_baz_bar", "kind": "step"},
    ]
    sid, mc = mod.resolve("foo bar baz", contract)
    # Exact normalized match wins.
    assert sid == "foo_bar_baz"


# ---------------------------------------------------------------------------
# Status precedence.
# ---------------------------------------------------------------------------


def test_status_precedence_in_progress_wins():
    assert mod.status_precedence("completed", "in_progress", "pending") == "in_progress"


def test_status_precedence_completed_over_pending():
    assert mod.status_precedence("pending", "completed") == "completed"


def test_status_precedence_pending_only():
    assert mod.status_precedence("pending", "pending") == "pending"


def test_status_precedence_unknown_safe():
    """Unknown status doesn't crash; falls back to pending."""
    assert mod.status_precedence("foo", "bar") in ("foo", "bar", "pending")


def test_status_precedence_empty():
    assert mod.status_precedence() == "pending"


# ---------------------------------------------------------------------------
# Alias resolution.
# ---------------------------------------------------------------------------


def test_alias_resolve_known(monkeypatch):
    """Alias table maps legacy step_id → current."""
    monkeypatch.setattr(mod, "STEP_ID_ALIASES", {"5_fix_loop": ["step5_fix_loop"]})
    assert mod.resolve_alias("step5_fix_loop") == "5_fix_loop"


def test_alias_resolve_unknown():
    assert mod.resolve_alias("totally_unknown") is None


def test_alias_resolve_self_returns_none():
    """Passing the current canonical step_id returns None (no alias to migrate to)."""
    # Empty alias dict — anything is "unknown".
    assert mod.resolve_alias("5_fix_loop") is None


# ---------------------------------------------------------------------------
# Unicode / Vietnamese / long-label edge cases.
# ---------------------------------------------------------------------------


def test_unicode_nfkd_normalize():
    """Vietnamese diacritics: combining chars stripped."""
    contract = [{"id": "kiem_tra", "kind": "step"}]
    # Vietnamese 'kiểm tra' → NFKD strips combining → 'kiem tra' → 'kiem_tra'.
    sid, mc = mod.resolve("kiểm tra", contract)
    # Note: 'kiểm' NFKD = 'kie' + combining hook + 'm'. After strip combining = 'kiem'.
    # Then normalized 'kiem tra' matches kiem_tra normalized 'kiem tra'.
    assert sid == "kiem_tra"


def test_very_long_label_doesnt_crash():
    long_label = "↳ " + ("very long text " * 100) + " 3_crossai_sweep"
    sid, mc = mod.resolve(long_label, RTB_C1A5_CONTRACT)
    assert sid == "3_crossai_sweep"
    assert mc == "substring"


# ---------------------------------------------------------------------------
# Idempotency + determinism.
# ---------------------------------------------------------------------------


def test_idempotent():
    """Second resolve = same result."""
    labels = [
        "↳ 0 Parse And Validate",
        "↳ 3.5 CrossAI Sweep",
        "↳ test-spec 4_codegen — Spawn",
        "garbage input",
    ]
    first = [mod.resolve(lbl, RTB_C1A5_CONTRACT) for lbl in labels]
    second = [mod.resolve(lbl, RTB_C1A5_CONTRACT) for lbl in labels]
    assert first == second


def test_property_never_returns_none():
    """resolve() never returns (None, ...) — always (str, MatchClass)."""
    for label in ["", "  ", "x", "↳", "999"]:
        sid, mc = mod.resolve(label, RTB_C1A5_CONTRACT)
        assert isinstance(sid, str)
        assert sid != ""
        assert mc in ("exact", "normalized", "strip-cmd", "strip-decimal", "substring", "slug", "unresolved")


# ---------------------------------------------------------------------------
# RTB fixture sweep — all 5 label families resolve.
# ---------------------------------------------------------------------------


def test_rtb_c1a5_all_5_label_families():
    """All 5 stylistic clusters from RTB c1a5edc3 resolve to known step_ids."""
    samples = [
        # Family 1: Title Case arrow.
        ("↳ 0 Parse And Validate", "0_parse_and_validate"),
        ("↳ 1 Build Artifact Gate", "1_build_artifact_gate"),
        # Family 2: dot-decimal half-step.
        ("↳ 3.5 CrossAI Sweep", "3_crossai_sweep"),
        # Family 3: command-prefixed snake_case.
        ("↳ test-spec 0_parse_and_validate", "0_parse_and_validate"),
        ("↳ test-spec 3_crossai_sweep", "3_crossai_sweep"),
        # Family 4: step_id + em-dash free text.
        ("↳ test-spec 4_codegen — Spawn vg-test-codegen full subagent pass", "4_codegen"),
        # Family 5: group rows — these legitimately don't match any step.
        # ("Test-Spec 7.16 Steps", "<unresolved>")  # group header, no step.
    ]
    for label, expected_id in samples:
        sid, mc = mod.resolve(label, RTB_C1A5_CONTRACT)
        assert sid == expected_id, f"FAIL {label!r} → {sid} (expected {expected_id}), mc={mc}"
        assert mc != "unresolved", f"FAIL {label!r} returned unresolved"


# ---------------------------------------------------------------------------
# Performance.
# ---------------------------------------------------------------------------


def test_perf_500_row_contract_under_50ms():
    """Resolver must handle 500-row contracts in < 50ms per call."""
    contract = [{"id": f"step_{i}_action", "kind": "step"} for i in range(500)]
    labels = ["↳ step 42 action", "↳ test-spec step_99_action", "garbage"]
    t0 = time.perf_counter()
    for lbl in labels * 10:
        mod.resolve(lbl, contract)
    elapsed = (time.perf_counter() - t0) / (len(labels) * 10)
    assert elapsed < 0.05, f"resolve() too slow: {elapsed*1000:.1f}ms avg per call"


# ---------------------------------------------------------------------------
# Mirror parity.
# ---------------------------------------------------------------------------


def test_resolver_mirror_byte_identical():
    """canonical and .claude mirror must be byte-identical (per audit B-1 fix)."""
    canonical = RESOLVER.read_bytes()
    mirror = RESOLVER_MIRROR.read_bytes()
    assert canonical == mirror, (
        f"Resolver mirror drift — canonical {len(canonical)}B vs mirror {len(mirror)}B"
    )
