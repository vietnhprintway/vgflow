"""tests/test_batch57_seed_chain_integration.py — Batch 57.

End-to-end smoke test for the seed contract chain (Batches 36-56).
Builds a synthetic phase with realistic inputs, runs every generator
+ validator in the chain, asserts artifacts wire correctly.

Catches inter-layer contract drift that no single batch test sees:
  - LIFECYCLE-SPECS.json schema must round-trip through derive →
    VARIANTS.json schema must round-trip through codegen →
    SEED-RECIPE.md schema must match generate-seed-helper-stub parser →
    helper.ts case branches must match validator regex
  - variant_id format SAME everywhere (no naming drift between
    generate-seed-recipes / derive / helper-stub / validators)
  - observed_state from scans[] propagates from generate-seed-recipes
    into SEED-RECIPE.md without lossy serialization

Layout exercises ALL kinds present in KIND_TO_RECIPE:
  - edge_cases: boundary, empty_string, unicode_special,
    filter_combination, pagination_edge, large_payload
  - negative_specs: unauthorized_401, forbidden_403, validation_422,
    not_found_404, rate_limit_429
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
VALIDATORS = SCRIPTS / "validators"

DERIVE = SCRIPTS / "derive-edge-cases-from-lifecycle.py"
GEN_SEED = SCRIPTS / "generate-seed-recipes.py"
GEN_HELPER = SCRIPTS / "generate-seed-helper-stub.py"

VAL_VARIANTS = VALIDATORS / "verify-variants-json.py"
VAL_SEED = VALIDATORS / "verify-seed-recipe-coverage.py"
VAL_HELPER = VALIDATORS / "verify-seed-helper-stub.py"


def _build_synthetic_phase(tmp_path: Path, phase: str = "99") -> Path:
    """Build a phase dir with LIFECYCLE + scan files exercising all kinds."""
    phase_dir = tmp_path / "phases" / phase
    phase_dir.mkdir(parents=True)

    lifecycle = {
        "goals": {
            "G-01": {
                "title": "Manage sites",
                "edge_cases": [
                    {"kind": "boundary", "label": "min", "input_hint": "0"},
                    {"kind": "empty_string", "label": "empty optional"},
                    {"kind": "unicode_special", "label": "emoji"},
                    {"kind": "filter_combination", "label": "status+owner"},
                    {"kind": "pagination_edge", "label": "page 2 boundary"},
                    {"kind": "large_payload", "label": "max name length"},
                ],
                "negative_specs": [
                    {"kind": "unauthorized_401", "expected_status": 401},
                    {"kind": "forbidden_403", "expected_status": 403},
                    {"kind": "validation_422", "expected_status": 422},
                    {"kind": "not_found_404", "expected_status": 404},
                    {"kind": "rate_limit_429", "expected_status": 429},
                ],
            },
            "G-02": {
                "title": "Read users",
                "edge_cases": [
                    {"kind": "pagination_edge", "label": "boundary"},
                ],
                "negative_specs": [
                    {"kind": "unauthorized_401", "expected_status": 401},
                ],
            },
        }
    }
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(
        json.dumps(lifecycle, indent=2), encoding="utf-8"
    )

    # Scan exercising filter/pagination/state observations (Batch 40-43, 54)
    (phase_dir / "scan-sites.json").write_text(json.dumps({
        "view": "/sites",
        "filters": [
            {"name": "Status", "kind": "select",
             "options": ["all", "active", "archived"], "near_table_ref": "e20"},
            {"name": "Owner", "kind": "combobox", "options": None,
             "near_table_ref": "e20"},
        ],
        "sort_headers": [
            {"column": "Name", "clicked": True, "resulting_order": "asc"}
        ],
        "pagination": {"present": True, "total_pages": 7,
                       "current_page": 1, "page_size": 25},
        "tables": [{"ref": "e20", "row_count": 168}],
        "search": [{"placeholder": "Search sites...",
                    "debounce_ms_observed": 300}],
        "state_observations": {
            "empty_state": {"observed": True,
                            "trigger": "search 'zzzzzz'",
                            "message_text": "No sites found"},
            "error_state_4xx": {"observed": True,
                                "expected_status": 404,
                                "actual_status": 404,
                                "trigger": "/sites/99999999-fake-id-probe"},
        },
    }), encoding="utf-8")

    return phase_dir


def _run(script: Path, phase: str, phase_dir: Path, *extra: str):
    return subprocess.run(
        ["python", str(script), "--phase", phase, "--phase-dir", str(phase_dir),
         *extra],
        capture_output=True, text=True,
    )


def test_chain_end_to_end_no_drift(tmp_path):
    """Run the entire B36-56 chain on a synthetic phase. No errors anywhere."""
    phase_dir = _build_synthetic_phase(tmp_path, "99")

    # 1. derive EDGE-CASES + VARIANTS.json (Batch 48+56)
    r = _run(DERIVE, "99", phase_dir, "--force")
    assert r.returncode == 0, f"derive failed: {r.stdout}\n{r.stderr}"
    variants_path = phase_dir / "EDGE-CASES" / "VARIANTS.json"
    assert variants_path.is_file()

    # 2. validate VARIANTS.json (Batch 56)
    r = _run(VAL_VARIANTS, "99", phase_dir, "--strict")
    assert r.returncode == 0, f"verify-variants failed: {r.stdout}\n{r.stderr}"

    # 3. generate SEED-RECIPE.md (Batch 51+54)
    r = _run(GEN_SEED, "99", phase_dir, "--force")
    assert r.returncode == 0, f"generate-seed-recipes failed: {r.stdout}\n{r.stderr}"
    assert (phase_dir / "SEED-RECIPE.md").is_file()

    # 4. validate seed recipe coverage (Batch 51)
    r = _run(VAL_SEED, "99", phase_dir, "--strict", "--allow-placeholders")
    assert r.returncode == 0, f"verify-seed-recipe failed: {r.stdout}\n{r.stderr}"

    # 5. generate seed helper stub (Batch 55)
    r = _run(GEN_HELPER, "99", phase_dir, "--force")
    assert r.returncode == 0, f"generate-seed-helper-stub failed: {r.stdout}\n{r.stderr}"
    helper_path = phase_dir / "tests" / "_helpers" / "seed-recipes.ts"
    assert helper_path.is_file()

    # 6. validate helper stub (Batch 55)
    r = _run(VAL_HELPER, "99", phase_dir, "--strict")
    assert r.returncode == 0, f"verify-seed-helper failed: {r.stdout}\n{r.stderr}"


def test_variant_id_format_uniform_across_layers(tmp_path):
    """variant_id must be identical in VARIANTS.json, SEED-RECIPE.md, helper.ts."""
    phase_dir = _build_synthetic_phase(tmp_path, "98")
    _run(DERIVE, "98", phase_dir, "--force")
    _run(GEN_SEED, "98", phase_dir, "--force")
    _run(GEN_HELPER, "98", phase_dir, "--force")

    variants_doc = json.loads(
        (phase_dir / "EDGE-CASES" / "VARIANTS.json").read_text(encoding="utf-8")
    )
    variant_ids_json = {v["variant_id"] for vs in variants_doc["goals"].values() for v in vs}

    recipe_body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    helper_body = (phase_dir / "tests" / "_helpers" / "seed-recipes.ts").read_text(encoding="utf-8")

    # Every variant in JSON must appear in BOTH recipe + helper
    for vid in variant_ids_json:
        assert f"variant_id: {vid}" in recipe_body, f"{vid} missing in SEED-RECIPE.md"
        assert f"case '{vid}'" in helper_body, f"{vid} missing in helper.ts"


def test_observed_state_propagates_filter_combination(tmp_path):
    """filter_combination recipe must include observed_state.real_filters."""
    phase_dir = _build_synthetic_phase(tmp_path, "97")
    _run(GEN_SEED, "97", phase_dir, "--force")
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    # Find filter_combination variant block
    idx = body.find("kind: filter_combination")
    assert idx > 0
    snippet = body[idx:idx + 1500]
    assert "observed_state" in snippet
    assert "real_filters" in snippet
    assert "Status" in snippet  # real filter name from scan
    assert "Owner" in snippet


def test_observed_state_propagates_pagination_edge(tmp_path):
    phase_dir = _build_synthetic_phase(tmp_path, "96")
    _run(GEN_SEED, "96", phase_dir, "--force")
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    idx = body.find("kind: pagination_edge")
    snippet = body[idx:idx + 1500]
    assert "real_pagination" in snippet
    assert "168" in snippet  # row_count from scan


def test_observed_state_propagates_not_found_404(tmp_path):
    phase_dir = _build_synthetic_phase(tmp_path, "95")
    _run(GEN_SEED, "95", phase_dir, "--force")
    body = (phase_dir / "SEED-RECIPE.md").read_text(encoding="utf-8")
    idx = body.find("kind: not_found_404")
    snippet = body[idx:idx + 1500]
    assert "error_state_4xx" in snippet
    assert "fake-id-probe" in snippet


def test_helper_stub_has_throw_for_every_seed_variant(tmp_path):
    """Every variant case in runSeedRecipe must throw (loud-failure contract)."""
    phase_dir = _build_synthetic_phase(tmp_path, "94")
    _run(DERIVE, "94", phase_dir, "--force")
    _run(GEN_SEED, "94", phase_dir, "--force")
    _run(GEN_HELPER, "94", phase_dir, "--force")
    body = (phase_dir / "tests" / "_helpers" / "seed-recipes.ts").read_text(encoding="utf-8")

    # Count cases and throws. Each seed_action case must throw; cleanup case must return.
    seed_section = body.split("export async function cleanup")[0]
    case_count = seed_section.count("case '")
    throw_count = seed_section.count("throw new Error")
    # +1 for default branch's throw
    assert throw_count >= case_count


def test_negative_specs_idempotent_rules_propagate(tmp_path):
    """rate_limit_429 has idempotent=false in VARIANTS.json + cleanup comment."""
    phase_dir = _build_synthetic_phase(tmp_path, "93")
    _run(DERIVE, "93", phase_dir, "--force")
    variants_doc = json.loads(
        (phase_dir / "EDGE-CASES" / "VARIANTS.json").read_text(encoding="utf-8")
    )
    by_id: dict[str, dict] = {}
    for gid, vs in variants_doc["goals"].items():
        for v in vs:
            by_id[v["variant_id"]] = v
    # G-01-n5 is rate_limit_429 (5th negative spec). Should be non-idempotent.
    n5 = by_id.get("G-01-n5")
    assert n5 is not None
    assert n5["kind"] == "rate_limit_429"
    assert n5["idempotent"] is False
    # Others should be idempotent
    n1 = by_id.get("G-01-n1")
    assert n1 is not None and n1["idempotent"] is True


def test_chain_back_compat_minimal_phase(tmp_path):
    """Phase with only edge_cases (no scans, no negative_specs) still passes chain."""
    phase_dir = tmp_path / "phases" / "92"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps({
        "goals": {"G-01": {"edge_cases": [{"kind": "boundary"}]}}
    }), encoding="utf-8")

    assert _run(DERIVE, "92", phase_dir, "--force").returncode == 0
    assert _run(VAL_VARIANTS, "92", phase_dir, "--strict").returncode == 0
    assert _run(GEN_SEED, "92", phase_dir, "--force").returncode == 0
    assert _run(VAL_SEED, "92", phase_dir, "--strict", "--allow-placeholders").returncode == 0
    assert _run(GEN_HELPER, "92", phase_dir, "--force").returncode == 0
    assert _run(VAL_HELPER, "92", phase_dir, "--strict").returncode == 0


def test_chain_detects_lifecycle_drift(tmp_path):
    """If LIFECYCLE adds a variant after VARIANTS.json generated, validator catches."""
    phase_dir = _build_synthetic_phase(tmp_path, "91")
    _run(DERIVE, "91", phase_dir, "--force")
    # Add new variant to LIFECYCLE WITHOUT re-deriving
    lifecycle = json.loads((phase_dir / "LIFECYCLE-SPECS.json").read_text(encoding="utf-8"))
    lifecycle["goals"]["G-03"] = {
        "title": "New goal",
        "edge_cases": [{"kind": "boundary"}],
    }
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(json.dumps(lifecycle), encoding="utf-8")
    # Validator should now FAIL strict (drift)
    r = _run(VAL_VARIANTS, "91", phase_dir, "--strict")
    assert r.returncode != 0
    assert "G-03-b1" in (r.stderr + r.stdout)
